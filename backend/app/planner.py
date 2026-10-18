"""First-PR planner engine generating repo-grounded implementation plans."""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.fixtures_loader import load_fixture_plan
from app.github_client import GitHubClient, parse_and_validate_github_url
from app.prompts import (
    PLAN_SYSTEM_INSTRUCTION,
    PlanModelOutput,
    build_plan_prompt,
)
from app.providers.base import (
    AuthenticationError,
    InvalidModelOutputError,
    ModelProviderError,
    ModelTimeoutError,
    QuotaExceededError,
    SafetyBlockedError,
)
from app.providers.gemini import GeminiProvider
from app.schemas import (
    ContributorProfile,
    PlanNote,
    PlanResponse,
    PlanStep,
)

logger = logging.getLogger(__name__)


def create_deterministic_fallback_plan(
    issue_number: int,
    issue_title: str,
    issue_url: str,
    docs: dict,
    repo_tree: list[str],
    warning_reason: str,
    existing_warnings: Optional[list[str]] = None,
) -> PlanResponse:
    """Generate a safe, conservative deterministic implementation plan without calling the model."""
    has_setup = docs.get("has_setup_guide", False)
    has_test = docs.get("has_test_guide", False)

    setup_note = PlanNote(
        status="verified" if has_setup else "unknown",
        notes="Installation and setup guidance located in repository documentation."
        if has_setup
        else "No documented setup or environment instructions found in repository.",
    )
    test_note = PlanNote(
        status="verified" if has_test else "unknown",
        notes="Test suite runner and commands documented in repository README/CONTRIBUTING."
        if has_test
        else "No specific test runner or test instructions found in repository documentation.",
    )

    # Pick up to 2 plausible files from the real tree
    matched_files = [p for p in repo_tree if any(k in p.lower() for k in ("test", "main", "app", "doc"))][:2]

    fallback_steps = [
        PlanStep(
            title="Inspect Issue Requirements & Scope",
            detail=f"Review the issue description for #{issue_number} ('{issue_title}') and identify the expected behavior.",
            kind="verified",
            files=matched_files,
        ),
        PlanStep(
            title="Reproduce or Locate Affected Code",
            detail="Search the repository codebase for the affected functions, components, or documentation lines.",
            kind="inference",
            files=matched_files[:1],
        ),
        PlanStep(
            title="Implement Surgical Change",
            detail="Make the smallest necessary fix or documentation edit addressing the issue directly.",
            kind="inference",
            files=matched_files,
        ),
        PlanStep(
            title="Verify & Run Tests Locally",
            detail="Execute local tests or linter checks according to project guidelines before committing.",
            kind="inference",
            files=[],
        ),
        PlanStep(
            title="Prepare Conventional Pull Request",
            detail="Write a concise PR description referencing the issue number and explaining the changes.",
            kind="verified",
            files=[],
        ),
    ]

    checklist = [
        "Read the issue description thoroughly and ask questions if scope is ambiguous.",
        "Locate the relevant source files using the repository file tree.",
        "Reproduce the bug or confirm the missing documentation locally.",
        "Implement the minimal fix with clean, formatted code.",
        "Run the test suite and verify no existing tests break.",
        "Submit a draft PR with a clear summary and issue reference.",
    ]

    pr_title = f"fix: resolve #{issue_number} - {issue_title[:50]}"
    pr_desc = (
        f"## Summary of Changes\n"
        f"Addresses #{issue_number} ('{issue_title}').\n\n"
        f"## Testing Done\n"
        f"- Verified changes locally.\n\n"
        f"Fixes #{issue_number}\n"
    )

    return PlanResponse(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        summary=f"Implementation plan for #{issue_number} ('{issue_title}').",
        steps=fallback_steps,
        setup_guidance=setup_note,
        test_guidance=test_note,
        checklist=checklist,
        pr_title=pr_title,
        pr_description_draft=pr_desc,
        open_questions_for_maintainer=[
            f"Are there existing reproduction tests or specific style conventions for #{issue_number}?"
        ],
        ai_status="unavailable_or_invalid",
        warnings=list(existing_warnings or []) + ([warning_reason] if warning_reason and warning_reason not in (existing_warnings or []) else []),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


async def generate_first_pr_plan(
    repo_url: str,
    issue_number: int,
    profile: ContributorProfile,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[GeminiProvider] = None,
) -> PlanResponse:
    """
    Generate a grounded first-PR implementation plan for a verified open issue:
    1. Validate GitHub URL and verify issue is currently open.
    2. Ingest fresh documentation, issue comments, and file tree.
    3. Generate 3-7 bounded steps via Gemma 4 with grounding validation.
    4. Fall back safely to deterministic plan on quota, network, or validation errors.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        logger.info("Serving plan from offline fixture dataset (demo_mode=True)")
        return load_fixture_plan(
            repo_url=repo_url,
            issue_number=issue_number,
            profile=profile,
        )

    gh = github_client or GitHubClient()
    warnings: list[str] = []

    # 1. Fetch fresh issue details and verify it is open
    issue_data = await gh.fetch_single_issue(owner, repo_name, issue_number)
    issue_title = issue_data.get("title", f"Issue #{issue_number}")
    issue_url = issue_data.get("html_url", f"https://github.com/{owner}/{repo_name}/issues/{issue_number}")

    # 2. Fetch fresh documentation and comments
    docs = await gh.fetch_documentation(owner, repo_name)
    comments = await gh.fetch_issue_comments(owner, repo_name, issue_number, max_comments=8)

    # 3. Fetch file tree for grounding
    repo_meta = await gh.fetch_repo_metadata(owner, repo_name)
    file_paths, gh_trunc, app_trunc = await gh.fetch_file_tree(
        owner, repo_name, repo_meta.default_branch
    )
    if gh_trunc or app_trunc:
        warnings.append("Repository file tree was truncated due to size bounds.")

    valid_paths_set = set(file_paths)

    # 4. Check for Demo Mode or Missing Credentials
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key
    if should_skip_ai:
        reason = "Demo mode active. Showing deterministic plan." if (demo or settings.DEMO_MODE) else "GEMINI_API_KEY unconfigured. Showing deterministic plan."
        return create_deterministic_fallback_plan(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            docs=docs,
            repo_tree=file_paths,
            warning_reason=reason,
        )

    # 5. Build Bounded Planning Prompt
    prompt_text, is_truncated = build_plan_prompt(
        profile_data=profile.model_dump(),
        issue_data=issue_data,
        comments=comments,
        file_tree=file_paths,
        readme_excerpt=docs.get("readme_excerpt", ""),
        contributing_excerpt=docs.get("contributing_excerpt", ""),
        max_chars=settings.MAX_PROMPT_CHARS,
    )
    if is_truncated:
        warnings.append("Planning context exceeded character cap and was safely truncated.")

    provider = model_provider or GeminiProvider()
    plan_output: Optional[PlanModelOutput] = None

    # Single attempt with at most one retry strictly on InvalidModelOutputError
    for attempt in range(2):
        try:
            plan_obj, _ = await provider.generate_json(
                task_name="plan_generation",
                system_instruction=PLAN_SYSTEM_INSTRUCTION,
                user_prompt=prompt_text,
                output_schema=PlanModelOutput,
                timeout_seconds=float(settings.MODEL_TIMEOUT_SECONDS),
            )
            plan_output = plan_obj  # type: ignore
            break
        except InvalidModelOutputError as ime:
            logger.warning("Plan generation attempt %d produced invalid output: %s", attempt + 1, ime)
            if attempt == 0:
                prompt_text = (
                    f"PREVIOUS ATTEMPT FAILED VALIDATION: {str(ime)[:200]}\n"
                    f"Please output strictly schema-valid JSON matching the schema.\n\n"
                    f"{prompt_text}"
                )
            else:
                warnings.append("AI planning output invalid after retry. Falling back to deterministic plan.")
                break
        except (QuotaExceededError, AuthenticationError, SafetyBlockedError, ModelTimeoutError) as non_retryable:
            logger.warning("Non-retryable provider error during planning (%s): %s", type(non_retryable).__name__, non_retryable)
            return create_deterministic_fallback_plan(
                issue_number=issue_number,
                issue_title=issue_title,
                issue_url=issue_url,
                docs=docs,
                repo_tree=file_paths,
                warning_reason=f"AI reasoning unavailable ({type(non_retryable).__name__}). Showing deterministic plan.",
            )
        except ModelProviderError as mpe:
            logger.warning("Plan generation provider error: %s", mpe)
            return create_deterministic_fallback_plan(
                issue_number=issue_number,
                issue_title=issue_title,
                issue_url=issue_url,
                docs=docs,
                repo_tree=file_paths,
                warning_reason="AI planning provider error. Showing deterministic plan.",
            )

    if not plan_output:
        return create_deterministic_fallback_plan(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            docs=docs,
            repo_tree=file_paths,
            warning_reason="AI reasoning unavailable or invalid. Showing deterministic plan.",
            existing_warnings=warnings,
        )

    # 6. Validate and Ground Steps
    grounded_steps: list[PlanStep] = []
    dropped_paths_across_plan: list[str] = []

    for raw_step in plan_output.steps:
        step_dict = raw_step.model_dump() if hasattr(raw_step, "model_dump") else (raw_step if isinstance(raw_step, dict) else {})
        raw_files = step_dict.get("files") or []
        grounded_files = [f for f in raw_files if f in valid_paths_set]
        dropped_files = [f for f in raw_files if f not in valid_paths_set]
        if dropped_files:
            dropped_paths_across_plan.extend(dropped_files)

        kind_val = step_dict.get("kind", "inference")
        if kind_val not in ("verified", "inference"):
            kind_val = "inference"

        grounded_steps.append(
            PlanStep(
                title=str(step_dict.get("title", "Implementation Step")),
                detail=str(step_dict.get("detail", "")),
                kind=kind_val,
                files=grounded_files,
            )
        )

    if dropped_paths_across_plan:
        warnings.append(
            f"Dropped ungrounded file paths not in repo tree: {', '.join(dropped_paths_across_plan[:5])}"
        )

    # Bound steps to 3-7
    if len(grounded_steps) < 1:
        grounded_steps = [
            PlanStep(
                title="Inspect and resolve issue",
                detail=f"Review #{issue_number} and implement changes in source code.",
                kind="inference",
                files=[],
            )
        ]

    # Map setup and test notes
    setup_dict = plan_output.setup_guidance.model_dump() if hasattr(plan_output.setup_guidance, "model_dump") else (plan_output.setup_guidance if isinstance(plan_output.setup_guidance, dict) else {})
    setup_status = setup_dict.get("status", "unknown")
    if setup_status not in ("verified", "unknown", "inference"):
        setup_status = "unknown"
    setup_note = PlanNote(
        status=setup_status,
        notes=setup_dict.get("notes", "No setup instructions found in documentation."),
    )

    test_dict = plan_output.test_guidance.model_dump() if hasattr(plan_output.test_guidance, "model_dump") else (plan_output.test_guidance if isinstance(plan_output.test_guidance, dict) else {})
    test_status = test_dict.get("status", "unknown")
    if test_status not in ("verified", "unknown", "inference"):
        test_status = "unknown"
    test_note = PlanNote(
        status=test_status,
        notes=test_dict.get("notes", "No test instructions found in documentation."),
    )

    return PlanResponse(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        summary=plan_output.summary,
        steps=grounded_steps[:7],
        setup_guidance=setup_note,
        test_guidance=test_note,
        checklist=plan_output.checklist,
        pr_title=plan_output.pr_title,
        pr_description_draft=plan_output.pr_description_draft,
        open_questions_for_maintainer=plan_output.open_questions_for_maintainer,
        ai_status="complete",
        warnings=warnings,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
