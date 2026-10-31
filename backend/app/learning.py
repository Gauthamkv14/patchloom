"""Intelligent Issue Learning Engine for PatchLoom 2.0 (LEARN Pillar).

Orchestrates generation of structured, personalized Issue Learning Briefs that help
contributors understand problem context, requirements, unfamiliar technical concepts,
architecture modules, and self-assessment readiness before writing code.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Optional

from app.config import settings
from app.fixtures_loader import load_fixture_learn
from app.github_client import GitHubClient, parse_and_validate_github_url
from app.prompts import (
    LEARN_SYSTEM_INSTRUCTION,
    LearnModelOutput,
    build_learn_prompt,
    sanitize_untrusted_text,
)
from app.providers import get_provider
from app.providers.base import (
    AuthenticationError,
    InvalidModelOutputError,
    ModelProvider,
    ModelProviderError,
    ModelTimeoutError,
    QuotaExceededError,
    SafetyBlockedError,
)
from app.repo_intelligence import (
    generate_repository_intelligence,
    map_issue_to_repository_modules,
)
from app.schemas import (
    ContributorProfile,
    IntelligenceEvidence,
    IssueExplanation,
    IssueLearningBrief,
    IssueRequirement,
    LearningConcept,
    LearningObjective,
    ReadinessChecklistItem,
    RelevantInvestigationFile,
    RepositoryIntelligenceReport,
)

logger = logging.getLogger(__name__)


def create_deterministic_fallback_learning_brief(
    issue_number: int,
    issue_title: str,
    issue_url: str,
    issue_body: str,
    labels: list[str],
    profile: ContributorProfile,
    file_tree: list[str],
    docs_metadata: dict,
    intelligence_report: Optional[RepositoryIntelligenceReport],
    warning_reason: str,
    existing_warnings: Optional[list[str]] = None,
) -> IssueLearningBrief:
    """
    Generate a safe, conservative deterministic Issue Learning Brief when AI model
    inference is unavailable, in demo mode, or encountered quota/timeout errors.
    Preserves all grounded repository facts, M1 modules, and issue requirements.
    """
    observed = datetime.now(timezone.utc).isoformat()
    warnings = list(existing_warnings or [])
    if warning_reason and warning_reason not in warnings:
        warnings.append(warning_reason)

    level = profile.experience_level or "beginner"
    valid_paths_set = set(file_tree)

    # 1. Adapt explanation tone and guidance to contributor experience level
    if level == "beginner":
        adapt_note = "Adapted for beginner contributors: focuses on foundational understanding, finding files, and step-by-step verification."
    elif level == "intermediate":
        adapt_note = "Adapted for intermediate contributors: focuses on component interactions, architecture integration, and existing test patterns."
    else:
        adapt_note = "Adapted for advanced contributors: emphasizes architecture boundaries, edge cases, and maintainer review criteria."

    # 2. Extract deterministic requirements from issue body
    requirements: list[IssueRequirement] = []
    body_clean = issue_body.strip() if issue_body else ""

    if body_clean:
        # Check for bullet points or numbered lists in issue description
        bullet_matches = re.findall(r"^[\*\-\d\.]+\s+(.+)$", body_clean, re.MULTILINE)
        if bullet_matches:
            for b in bullet_matches[:4]:
                requirements.append(
                    IssueRequirement(
                        description=sanitize_untrusted_text(b[:200]),
                        source="issue_description",
                        supporting_evidence=sanitize_untrusted_text(b[:150]),
                        classification="explicit",
                        confidence="high",
                    )
                )

    if not requirements:
        # Fall back to general requirement from title and body excerpt
        requirements.append(
            IssueRequirement(
                description=f"Address reported issue: {issue_title}",
                source="issue_description",
                supporting_evidence=sanitize_untrusted_text(body_clean[:150]) or issue_title,
                classification="explicit" if body_clean else "inferred",
                confidence="medium",
            )
        )

    # 3. Incorporate M1 Repository Intelligence and Module Mapping
    relevant_modules: list[str] = []
    investigation_targets: list[RelevantInvestigationFile] = []
    related_tests_and_docs: list[str] = []

    if intelligence_report:
        # Map issue to modules deterministically
        mapping = map_issue_to_repository_modules(
            issue={"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels},
            file_tree=file_tree,
            modules=intelligence_report.modules,
            docs_text=docs_metadata.get("readme_excerpt", ""),
        )
        relevant_modules = mapping.candidate_modules

        for cand in mapping.candidate_files[:4]:
            if cand.path in valid_paths_set:
                investigation_targets.append(
                    RelevantInvestigationFile(
                        path=cand.path,
                        module_name=cand.module_name,
                        why_relevant=f"Matched via lexical overlap: {'; '.join(cand.reasons[:2])}",
                        what_to_inspect="Review definitions, error handling, and parameter assertions relevant to the issue.",
                        kind="candidate",
                        evidence=cand.evidence,
                    )
                )

        # Related tests and docs from M1 test profile
        if intelligence_report.test_profile.test_directories:
            related_tests_and_docs.extend(
                [f"{d}/ (test directory)" for d in intelligence_report.test_profile.test_directories[:2]]
            )
        if intelligence_report.documentation_profile.has_readme:
            related_tests_and_docs.append("README.md")
        if intelligence_report.documentation_profile.has_contributing:
            related_tests_and_docs.append("CONTRIBUTING.md")

    if not investigation_targets:
        # Check if any path in file tree is mentioned in issue title or body
        mentioned = [
            p for p in file_tree
            if (p in issue_body or Path(p).name in issue_body or Path(p).name in issue_title)
        ][:3]
        for p in mentioned:
            investigation_targets.append(
                RelevantInvestigationFile(
                    path=p,
                    module_name="general",
                    why_relevant="File explicitly referenced in issue title or description.",
                    what_to_inspect="Review definitions, error handling, and parameter assertions relevant to the issue.",
                    kind="candidate",
                    evidence=IntelligenceEvidence(
                        status="verified",
                        source="issue_text_mention",
                        observed_at=observed,
                        detail="Path mentioned in issue title or body.",
                    ),
                )
            )

        if not investigation_targets:
            # Fall back to top plausible files from tree
            plausible = [p for p in file_tree if any(k in p.lower() for k in ("main", "app", "router", "lib", "test"))][:2]
            for p in plausible:
                investigation_targets.append(
                    RelevantInvestigationFile(
                        path=p,
                        module_name="general",
                        why_relevant="Plausible core application file identified from repository tree structure.",
                        what_to_inspect="Check entry points, routing logic, or related unit tests.",
                        kind="candidate",
                        evidence=IntelligenceEvidence(
                            status="inference",
                            source="file_tree_heuristics",
                            observed_at=observed,
                            detail="Selected as plausible starting point for inspection.",
                        ),
                    )
                )

    # 4. Generate Core Concepts based on languages and technologies
    concepts: list[LearningConcept] = []
    tech_names = [t.name for t in (intelligence_report.technologies if intelligence_report else [])]

    if any("FastAPI" in t or "async" in t.lower() for t in tech_names) or "Python" in (intelligence_report.languages.primary if intelligence_report else ""):
        concepts.append(
            LearningConcept(
                name="Asynchronous Execution & Routing",
                explanation="How asynchronous requests and non-blocking I/O dispatch tasks within this service.",
                why_it_matters="Ensures new changes do not block event loops or misconfigure route handlers.",
                prerequisites=["Python coroutines (async/await)", "HTTP request-response lifecycle"],
                learning_order=1,
                difficulty="intermediate" if level != "advanced" else "beginner",
            )
        )
    else:
        concepts.append(
            LearningConcept(
                name="Repository Module Architecture",
                explanation="The structure and responsibilities of the repository's primary directory layout.",
                why_it_matters="Helps you locate where changes should be made and where corresponding tests reside.",
                prerequisites=["Basic Git version control", "Project build configuration"],
                learning_order=1,
                difficulty="beginner",
            )
        )

    concepts.append(
        LearningConcept(
            name="Testing & Regression Verification",
            explanation="How automated tests are structured and run across this repository.",
            why_it_matters="Verifying existing tests pass and adding new assertions proves your contribution works.",
            prerequisites=["Unit testing fundamentals"],
            learning_order=2,
            difficulty="beginner",
        )
    )

    # 5. Measurable Learning Objectives
    objectives = [
        LearningObjective(
            title="Locate the Affected Logic",
            description=f"Inspect the candidate investigation files ({', '.join(t.path for t in investigation_targets[:2])}) to identify where the behavior occurs.",
            relevance="Prevents making changes in the wrong file and grounds your understanding in real code.",
            completion_criterion="You can point to the specific lines of code or documentation defining the current behavior.",
        ),
        LearningObjective(
            title="Understand Existing Test Coverage",
            description="Locate the test file that verifies the affected component.",
            relevance="Understanding existing tests shows you how the maintainers expect the feature to function.",
            completion_criterion="You can execute the relevant test command locally and explain what it asserts.",
        ),
        LearningObjective(
            title="Clarify Ambiguities Before Editing",
            description="Formulate any unresolved questions about edge cases or expectations.",
            relevance="Saves time and prevents implementing an approach the maintainers may reject.",
            completion_criterion="You have verified that the issue's expected outcome is clear and unambiguous.",
        ),
    ]

    # 6. Readiness Checklist
    checklist = [
        ReadinessChecklistItem(
            category="problem_understanding",
            item=f"Can you explain the problem in #{issue_number} in your own words without reading the issue title?",
            guidance="Draft a 2-sentence summary of what is broken or missing.",
        ),
        ReadinessChecklistItem(
            category="expected_behavior",
            item="Is the expected outcome explicitly clear, or are there missing requirements?",
            guidance="Check if the issue specifies expected inputs, outputs, or error formats.",
        ),
        ReadinessChecklistItem(
            category="architecture_components",
            item="Have you inspected the candidate files and verified they exist in the repository?",
            guidance=f"Examine {', '.join(t.path for t in investigation_targets[:2])}.",
        ),
        ReadinessChecklistItem(
            category="technical_concepts",
            item="Do you feel comfortable with the prerequisite concepts identified for this issue?",
            guidance=f"Review '{concepts[0].name}' before modifying code.",
        ),
        ReadinessChecklistItem(
            category="testing_approach",
            item="Do you know which test runner or command to execute to verify this component?",
            guidance="Check the test instructions in repository documentation or CI workflow files.",
        ),
        ReadinessChecklistItem(
            category="remaining_uncertainties",
            item="Have you identified what questions remain for maintainers if requirements are ambiguous?",
            guidance="If anything is unclear, ask polite clarifying questions on the issue first.",
        ),
    ]

    ambiguities: list[str] = []
    if not body_clean or len(body_clean) < 60:
        ambiguities.append("Issue description is brief and may lack reproduction steps or specific error logs.")
    if not intelligence_report or not intelligence_report.documentation_profile.has_contributing:
        ambiguities.append("No dedicated CONTRIBUTING.md guide detected; maintainer preferred workflow should be confirmed.")

    explanation = IssueExplanation(
        summary=f"Overview of #{issue_number}: '{issue_title}'.",
        problem_description=sanitize_untrusted_text(body_clean[:350]) if body_clean else "No detailed problem description provided in issue body.",
        why_it_matters="Resolving this issue improves repository stability, documentation accuracy, or feature usability." if not ambiguities else None,
        expected_outcome=f"Expected resolution of #{issue_number} matching contributor expectations.",
        explicit_requirements=[r.description for r in requirements if r.classification == "explicit"],
        constraints_and_conditions=["Must adhere to existing repository code formatting and test standards."],
        ambiguities_and_unanswered_questions=ambiguities,
        experience_adaptation_note=adapt_note,
    )

    return IssueLearningBrief(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        experience_level=level,  # type: ignore
        explanation=explanation,
        requirements=requirements,
        relevant_modules=relevant_modules,
        investigation_targets=investigation_targets,
        related_tests_and_docs=related_tests_and_docs,
        concepts=concepts,
        learning_objectives=objectives,
        readiness_checklist=checklist,
        unresolved_questions=ambiguities or ["Are there specific reproduction tests or edge cases to consider?"],
        ai_status="unavailable_or_invalid",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="inference",
            source="deterministic_learning_engine_fallback",
            observed_at=observed,
            detail="Synthesized deterministic issue learning brief without external AI model calls.",
        ),
        checked_at=observed,
    )


async def generate_issue_learning_brief(
    repo_url: str,
    issue_number: int,
    profile: ContributorProfile,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[ModelProvider] = None,
) -> IssueLearningBrief:
    """
    Generate a grounded, structured Issue Learning Brief for a verified open issue:
    1. Validate GitHub URL.
    2. Check demo mode; load offline fixture brief if active.
    3. Ingest issue metadata, comments, docs, and file tree.
    4. Compute deterministic M1 Repository Intelligence.
    5. Call AI reasoning provider (Gemma 4) with grounded context & 1 retry on invalid output.
    6. Ground all model outputs (strictly dropping hallucinated file paths).
    7. Fall back safely to deterministic brief on quota, timeout, or provider failures.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # Validate requested model provider early before issuing outbound requests
    if provider_name and not (demo or settings.DEMO_MODE):
        get_provider(provider_name)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        logger.info("Serving issue learning brief from offline fixture dataset (demo_mode=True)")
        return load_fixture_learn(
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
    issue_body = issue_data.get("body", "") or ""
    labels = [
        label.get("name") if isinstance(label, dict) else str(label)
        for label in issue_data.get("labels", [])
    ]

    # 2. Fetch fresh documentation and comments
    docs = await gh.fetch_documentation(owner, repo_name)
    comments = await gh.fetch_issue_comments(owner, repo_name, issue_number, max_comments=6)

    # 3. Fetch file tree for grounding
    repo_meta = await gh.fetch_repo_metadata(owner, repo_name)
    file_paths, gh_trunc, app_trunc = await gh.fetch_file_tree(
        owner, repo_name, repo_meta.default_branch
    )
    is_truncated = gh_trunc or app_trunc
    if is_truncated:
        warnings.append("Repository file tree was truncated due to scale bounds (retained top 400 paths).")

    valid_paths_set = set(file_paths)

    # 4. Generate M1 Repository Intelligence Context
    intelligence_report: Optional[RepositoryIntelligenceReport] = None
    try:
        cand_issue_dicts = [{"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels}]
        intelligence_report = generate_repository_intelligence(
            owner=owner,
            repo_name=repo_name,
            languages=repo_meta.languages or [],
            file_tree=file_paths,
            docs_metadata=docs,
            ci_evidence=repo_meta.ci_evidence,
            candidate_issues=cand_issue_dicts,
            is_truncated=is_truncated,
        )
    except Exception as exc:
        logger.warning("Repository intelligence generation failed during learning brief: %s", exc)

    # 5. Check for Demo Mode or Missing Credentials
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key
    if should_skip_ai:
        reason = (
            "Demo/Fixture mode active. Showing deterministic learning brief."
            if (demo or settings.DEMO_MODE)
            else "GEMINI_API_KEY is not configured. Showing deterministic learning brief."
        )
        return create_deterministic_fallback_learning_brief(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            issue_body=issue_body,
            labels=labels,
            profile=profile,
            file_tree=file_paths,
            docs_metadata=docs,
            intelligence_report=intelligence_report,
            warning_reason=reason,
            existing_warnings=warnings,
        )

    # 6. Assemble Bounded Prompt
    provider = model_provider or get_provider(provider_name)

    repo_intel_dict = None
    if intelligence_report:
        repo_intel_dict = {
            "primary_language": intelligence_report.languages.primary,
            "project_type": intelligence_report.project_type,
            "technologies": [t.name for t in intelligence_report.technologies[:6]],
            "modules": [m.name for m in intelligence_report.modules[:6]],
            "test_frameworks": intelligence_report.test_profile.frameworks,
            "likely_test_commands": intelligence_report.test_profile.likely_commands,
        }

    prompt_text, is_prompt_truncated = build_learn_prompt(
        profile_data=profile.model_dump(),
        issue_data={"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels},
        comments=comments,
        file_tree=file_paths,
        readme_excerpt=docs.get("readme_excerpt", ""),
        contributing_excerpt=docs.get("contributing_excerpt", ""),
        repo_intelligence=repo_intel_dict,
        max_chars=settings.MAX_PROMPT_CHARS,
    )
    if is_prompt_truncated:
        warnings.append("Learning brief prompt context exceeded character bounds and was safely truncated.")

    # 7. Call Model Provider with at most 1 retry strictly on InvalidModelOutputError
    learn_response: Optional[LearnModelOutput] = None
    actual_model_used = settings.GEMMA_MODEL
    observed = datetime.now(timezone.utc).isoformat()

    for attempt in range(2):
        try:
            model_obj, actual_model_used = await provider.generate_json(
                task_name="learn_analysis",
                system_instruction=LEARN_SYSTEM_INSTRUCTION,
                user_prompt=prompt_text,
                output_schema=LearnModelOutput,
                timeout_seconds=float(settings.MODEL_TIMEOUT_SECONDS),
            )
            learn_response = model_obj  # type: ignore
            break
        except InvalidModelOutputError as ime:
            logger.warning("Issue learning brief attempt %d produced invalid model output: %s", attempt + 1, ime)
            if attempt == 0:
                prompt_text = (
                    f"PREVIOUS ATTEMPT FAILED SCHEMA VALIDATION: {str(ime)[:200]}\n"
                    f"Please output strictly schema-valid JSON conforming to LearnModelOutput.\n\n"
                    f"{prompt_text}"
                )
            else:
                warnings.append("AI learning output invalid after retry. Falling back to deterministic learning brief.")
                break
        except (QuotaExceededError, AuthenticationError, SafetyBlockedError, ModelTimeoutError) as non_retryable:
            logger.warning("Non-retryable provider error (%s): %s", type(non_retryable).__name__, non_retryable)
            warnings.append(f"AI learning analysis unavailable ({type(non_retryable).__name__}). Falling back to deterministic learning brief.")
            break
        except ModelProviderError as mpe:
            logger.warning("Provider error on learning brief attempt %d: %s", attempt + 1, mpe)
            warnings.append("AI learning analysis encountered an error. Falling back to deterministic learning brief.")
            break

    # If AI inference failed, return deterministic fallback
    if not learn_response:
        return create_deterministic_fallback_learning_brief(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            issue_body=issue_body,
            labels=labels,
            profile=profile,
            file_tree=file_paths,
            docs_metadata=docs,
            intelligence_report=intelligence_report,
            warning_reason="Showing deterministic learning brief with M1 intelligence.",
            existing_warnings=warnings,
        )

    # 8. Ground File Targets and Assemble Complete Response
    grounded_investigation_targets: list[RelevantInvestigationFile] = []
    dropped_paths: list[str] = []

    for target in learn_response.investigation_targets:
        if target.path in valid_paths_set:
            grounded_investigation_targets.append(
                RelevantInvestigationFile(
                    path=target.path,
                    module_name=target.module_name,
                    why_relevant=target.why_relevant,
                    what_to_inspect=target.what_to_inspect,
                    kind="detected" if target.kind == "detected" else "candidate",
                    evidence=IntelligenceEvidence(
                        status="inference",
                        source="gemma_grounded_investigation_mapping",
                        observed_at=observed,
                        detail=f"Target path verified in repository tree ({target.path}).",
                    ),
                )
            )
        else:
            dropped_paths.append(target.path)

    if dropped_paths:
        warnings.append(f"Dropped ungrounded candidate paths not in repo tree: {', '.join(dropped_paths)}")

    # If all model targets were ungrounded, fall back to M1 module mapping targets
    if not grounded_investigation_targets and intelligence_report:
        mapping = map_issue_to_repository_modules(
            issue={"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels},
            file_tree=file_paths,
            modules=intelligence_report.modules,
        )
        for cand in mapping.candidate_files[:3]:
            if cand.path in valid_paths_set:
                grounded_investigation_targets.append(
                    RelevantInvestigationFile(
                        path=cand.path,
                        module_name=cand.module_name,
                        why_relevant=f"Fallback M1 lexical target: {'; '.join(cand.reasons[:2])}",
                        what_to_inspect="Inspect component definitions and error checks.",
                        kind="candidate",
                        evidence=cand.evidence,
                    )
                )

    # Convert model requirements to schema requirements
    structured_requirements: list[IssueRequirement] = [
        IssueRequirement(
            description=req.description,
            source=req.source,
            supporting_evidence=req.supporting_evidence,
            classification="explicit" if req.classification.lower() == "explicit" else "inferred",
            confidence="high" if req.confidence.lower() == "high" else ("low" if req.confidence.lower() == "low" else "medium"),
        )
        for req in learn_response.requirements
    ]

    # Convert model concepts to schema concepts
    structured_concepts: list[LearningConcept] = [
        LearningConcept(
            name=c.name,
            explanation=c.explanation,
            why_it_matters=c.why_it_matters,
            prerequisites=c.prerequisites,
            learning_order=max(1, min(10, c.learning_order)),
            difficulty="advanced" if c.difficulty.lower() == "advanced" else ("intermediate" if c.difficulty.lower() == "intermediate" else "beginner"),
        )
        for c in learn_response.concepts
    ]

    # Convert model objectives to schema objectives
    structured_objectives: list[LearningObjective] = [
        LearningObjective(
            title=obj.title,
            description=obj.description,
            relevance=obj.relevance,
            completion_criterion=obj.completion_criterion,
        )
        for obj in learn_response.learning_objectives
    ]

    # Convert model checklist to schema checklist
    valid_categories = {
        "problem_understanding",
        "expected_behavior",
        "architecture_components",
        "technical_concepts",
        "testing_approach",
        "remaining_uncertainties",
    }
    structured_checklist: list[ReadinessChecklistItem] = [
        ReadinessChecklistItem(
            category=item.category if item.category in valid_categories else "problem_understanding",  # type: ignore
            item=item.item,
            guidance=item.guidance,
        )
        for item in learn_response.readiness_checklist
    ]

    explanation = IssueExplanation(
        summary=learn_response.explanation.summary,
        problem_description=learn_response.explanation.problem_description,
        why_it_matters=learn_response.explanation.why_it_matters,
        expected_outcome=learn_response.explanation.expected_outcome,
        explicit_requirements=learn_response.explanation.explicit_requirements,
        constraints_and_conditions=learn_response.explanation.constraints_and_conditions,
        ambiguities_and_unanswered_questions=learn_response.explanation.ambiguities_and_unanswered_questions,
        experience_adaptation_note=learn_response.explanation.experience_adaptation_note,
    )

    return IssueLearningBrief(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        experience_level=profile.experience_level,
        explanation=explanation,
        requirements=structured_requirements,
        relevant_modules=learn_response.relevant_modules,
        investigation_targets=grounded_investigation_targets,
        related_tests_and_docs=learn_response.related_tests_and_docs,
        concepts=structured_concepts,
        learning_objectives=structured_objectives,
        readiness_checklist=structured_checklist,
        unresolved_questions=learn_response.unresolved_questions,
        ai_status="complete",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="inference",
            source="gemma_issue_learning_engine",
            observed_at=observed,
            detail=f"Synthesized personalized Issue Learning Brief using {actual_model_used}.",
        ),
        checked_at=observed,
    )
