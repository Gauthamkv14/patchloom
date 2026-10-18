"""Repository analysis and candidate fit ranking orchestration."""

import logging
from typing import Optional
from app.config import settings
from app.fixtures_loader import load_fixture_analysis
from app.github_client import GitHubClient, parse_and_validate_github_url
from app.prompts import (
    FIT_SYSTEM_INSTRUCTION,
    BatchedFitResponse,
    build_fit_prompt,
)
from app.providers.gemini import GeminiProvider
from app.providers.base import (
    AuthenticationError,
    InvalidModelOutputError,
    ModelProviderError,
    ModelTimeoutError,
    QuotaExceededError,
    SafetyBlockedError,
)
from app.schemas import (
    AnalyzeResponse,
    CandidateIssue,
    ContributorProfile,
    RepoMetadata,
)
from app.signals import filter_and_rank_candidates

logger = logging.getLogger(__name__)


async def analyze_repository(
    repo_url: str,
    profile: ContributorProfile,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[GeminiProvider] = None,
) -> AnalyzeResponse:
    """
    Execute full repository analysis:
    1. Validate GitHub URL.
    2. Ingest public repository metadata, documentation, file tree, and open issues.
    3. Compute deterministic viability signals and pre-filter up to 12 candidates.
    4. Execute batched Gemma 4 fit reasoning (or deterministic fallback if demo/unavailable).
    5. Validate and ground all model outputs (dropping hallucinated file paths).
    6. Compute composite final score (0.60 * fit + 0.40 * viability) and rank.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        logger.info("Serving analysis from offline fixture dataset (demo_mode=True)")
        return load_fixture_analysis(
            repo_url=repo_url,
            profile=profile,
            provider_name=provider_name,
        )

    gh = github_client or GitHubClient()
    warnings: list[str] = []

    # 1. Fetch Repository Metadata
    repo_meta: RepoMetadata = await gh.fetch_repo_metadata(owner, repo_name)

    # 2. Fetch Documentation & File Tree
    docs = await gh.fetch_documentation(owner, repo_name)
    repo_meta.has_readme = docs.get("has_readme", False)
    repo_meta.has_contributing = docs.get("has_contributing", False)

    file_paths, gh_trunc, app_trunc = await gh.fetch_file_tree(
        owner, repo_name, repo_meta.default_branch
    )
    repo_meta.tree_truncated = gh_trunc or app_trunc
    if repo_meta.tree_truncated:
        warnings.append("Repository file tree was truncated due to scale bounds (retained top 400 paths).")

    # 3. Fetch Open Issues & Compute Deterministic Signals
    raw_issues = await gh.fetch_open_issues(owner, repo_name, max_pages=2)
    candidates: list[CandidateIssue] = filter_and_rank_candidates(
        raw_issues=raw_issues,
        docs_metadata=docs,
        max_candidates=settings.MAX_CANDIDATES,
    )

    if not candidates:
        warnings.append("No viable open candidate issues found matching initial criteria.")
        return AnalyzeResponse(
            repo=repo_meta,
            provider=provider_name or settings.MODEL_PROVIDER,
            actual_model=settings.GEMMA_MODEL,
            ai_status="unavailable_or_invalid",
            issues=[],
            warnings=warnings,
        )

    # 4. Check for Demo Mode or Missing Credentials
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key

    if should_skip_ai:
        if not settings.has_gemini_key and not (demo or settings.DEMO_MODE):
            warnings.append("GEMINI_API_KEY is not configured. Showing deterministic viability ranking only.")
        elif demo or settings.DEMO_MODE:
            warnings.append("Demo/Fixture mode active. Showing deterministic signals.")

        for c in candidates:
            c.final_score = float(c.viability_score)

        return AnalyzeResponse(
            repo=repo_meta,
            provider=provider_name or settings.MODEL_PROVIDER,
            actual_model=settings.GEMMA_MODEL,
            ai_status="unavailable_or_invalid",
            issues=candidates,
            warnings=warnings,
        )

    # 5. Execute Batched AI Fit Assessment
    provider = model_provider or GeminiProvider()
    valid_paths_set = set(file_paths)

    # Map candidate issue dicts for prompt builder
    cand_dicts = [
        {
            "number": c.number,
            "title": c.title,
            "body": next((i.get("body", "") for i in raw_issues if i.get("number") == c.number), ""),
            "labels": c.labels,
        }
        for c in candidates
    ]

    prompt_text, is_truncated = build_fit_prompt(
        profile_data=profile.model_dump(),
        candidate_issues=cand_dicts,
        file_tree=file_paths,
        readme_excerpt=docs.get("readme_excerpt", ""),
        max_chars=settings.MAX_PROMPT_CHARS,
    )
    if is_truncated:
        warnings.append("Prompt context exceeded character bounds and was safely truncated.")

    fit_response: Optional[BatchedFitResponse] = None
    actual_model_used = settings.GEMMA_MODEL
    ai_status = "unavailable_or_invalid"

    # Single attempt with at most one retry strictly on InvalidModelOutputError (malformed output)
    # Never retry on QuotaExceededError, AuthenticationError, ModelTimeoutError, or SafetyBlockedError
    for attempt in range(2):
        try:
            fit_obj, actual_model_used = await provider.generate_json(
                task_name="fit_analysis",
                system_instruction=FIT_SYSTEM_INSTRUCTION,
                user_prompt=prompt_text,
                output_schema=BatchedFitResponse,
                timeout_seconds=float(settings.MODEL_TIMEOUT_SECONDS),
            )
            fit_response = fit_obj  # type: ignore
            ai_status = "complete"
            break
        except InvalidModelOutputError as ime:
            logger.warning("Fit assessment attempt %d produced invalid model output: %s", attempt + 1, ime)
            if attempt == 0:
                # Add compact retry instruction
                prompt_text = (
                    f"PREVIOUS ATTEMPT FAILED VALIDATION: {str(ime)[:200]}\n"
                    f"Please output strictly schema-valid JSON matching the schema.\n\n"
                    f"{prompt_text}"
                )
            else:
                warnings.append("AI reasoning output invalid after retry. Falling back to deterministic viability.")
                break
        except (QuotaExceededError, AuthenticationError, SafetyBlockedError, ModelTimeoutError) as non_retryable:
            logger.warning("Non-retryable provider error (%s): %s", type(non_retryable).__name__, non_retryable)
            warnings.append(f"AI reasoning unavailable ({type(non_retryable).__name__}). Falling back to deterministic viability scores.")
            break
        except ModelProviderError as mpe:
            logger.warning("Provider error on attempt %d: %s", attempt + 1, mpe)
            warnings.append("AI reasoning encountered an error. Falling back to deterministic viability scores.")
            break

    # 6. Apply Fit Results & Ground File Paths
    if fit_response and fit_response.assessments:
        assessments_by_num = {a.issue_number: a for a in fit_response.assessments}

        for c in candidates:
            fit = assessments_by_num.get(c.number)
            if fit:
                c.fit_score = fit.fit_score
                # Final composite score: 0.60 fit + 0.40 viability
                c.final_score = round((0.60 * fit.fit_score) + (0.40 * c.viability_score), 1)
                c.matching_skills = fit.matching_skills
                c.skill_gaps = fit.skill_gaps
                c.estimated_hours = fit.estimated_hours
                c.reason = fit.reason
                c.risks = list(fit.risks)
                c.inferences = list(fit.inferences)

                # Grounding: strictly retain only paths present in the repository tree
                grounded_files = [f for f in fit.likely_files if f in valid_paths_set]
                dropped_files = [f for f in fit.likely_files if f not in valid_paths_set]
                c.likely_files = grounded_files
                if dropped_files:
                    c.risks.append(f"Dropped ungrounded file paths not in repo tree: {', '.join(dropped_files)}")
            else:
                c.final_score = float(c.viability_score)
    else:
        # Fallback to deterministic scoring
        for c in candidates:
            c.final_score = float(c.viability_score)

    # 7. Final Sorting by final_score descending
    candidates.sort(key=lambda x: (x.final_score if x.final_score is not None else -1), reverse=True)

    return AnalyzeResponse(
        repo=repo_meta,
        provider=provider_name or settings.MODEL_PROVIDER,
        actual_model=actual_model_used,
        ai_status=ai_status,  # type: ignore
        issues=candidates,
        warnings=warnings,
    )
