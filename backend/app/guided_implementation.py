"""Guided Implementation Engine for PatchLoom 2.0 (LEARN & BUILD Pillar).

Orchestrates structured implementation roadmaps, progressive hint reveals,
code exploration targets, multi-approach evaluations, and optional educational
patch suggestions tailored to contributor experience.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Optional

from app.config import settings
from app.fixtures_loader import load_fixture_guided_implementation
from app.github_client import GitHubClient, parse_and_validate_github_url
from app.learning import generate_issue_learning_brief
from app.prompts import (
    GUIDED_IMPLEMENTATION_SYSTEM_INSTRUCTION,
    GuidedImplementationModelOutput,
    build_guided_implementation_prompt,
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
    CodeExplorationTarget,
    ContributorProfile,
    GuidedImplementationPlan,
    ImplementationApproach,
    ImplementationStep,
    IntelligenceEvidence,
    IssueLearningBrief,
    PatchSuggestion,
    ProgressiveHint,
    RepositoryIntelligenceReport,
    StepCheckpoint,
)

logger = logging.getLogger(__name__)


def create_deterministic_fallback_guided_plan(
    issue_number: int,
    issue_title: str,
    issue_url: str,
    issue_body: str,
    labels: list[str],
    profile: ContributorProfile,
    file_tree: list[str],
    docs_metadata: dict,
    intelligence_report: Optional[RepositoryIntelligenceReport],
    learning_brief: Optional[IssueLearningBrief],
    warning_reason: str,
    existing_warnings: Optional[list[str]] = None,
) -> GuidedImplementationPlan:
    """
    Generate an evidence-grounded deterministic Guided Implementation Plan when AI model
    inference is unavailable, in demo mode, or encountered quota/timeout errors.
    Preserves M1 modules, M2 requirements, and repository tree grounding.
    """
    observed = datetime.now(timezone.utc).isoformat()
    warnings = list(existing_warnings or [])
    if warning_reason and warning_reason not in warnings:
        warnings.append(warning_reason)

    level = profile.experience_level or "beginner"
    valid_paths_set = set(file_tree)

    # 1. Identify primary candidate files
    primary_files: list[str] = []
    if learning_brief and learning_brief.investigation_targets:
        primary_files = [t.path for t in learning_brief.investigation_targets if t.path in valid_paths_set][:3]

    if not primary_files and intelligence_report:
        mapping = map_issue_to_repository_modules(
            issue={"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels},
            file_tree=file_tree,
            modules=intelligence_report.modules,
            docs_text=docs_metadata.get("readme_excerpt", ""),
        )
        primary_files = [c.path for c in mapping.candidate_files if c.path in valid_paths_set][:3]

    if not primary_files:
        mentioned = [
            p for p in file_tree
            if (p in issue_body or Path(p).name in issue_body or Path(p).name in issue_title)
        ][:3]
        primary_files = mentioned or [p for p in file_tree if any(k in p.lower() for k in ("main", "doc", "app", "test"))][:2]

    target_file = primary_files[0] if primary_files else (file_tree[0] if file_tree else "README.md")
    secondary_file = primary_files[1] if len(primary_files) > 1 else target_file

    # Test directories and files
    test_dirs = intelligence_report.test_profile.test_directories if intelligence_report else []
    test_files = [p for p in file_tree if any(k in p.lower() for k in ("test", "spec"))][:2]
    test_ref = test_files[0] if test_files else (f"{test_dirs[0]}/" if test_dirs else "tests/")

    # 2. Build Code Exploration Targets
    exploration_targets: list[CodeExplorationTarget] = []
    for f in primary_files[:3]:
        exploration_targets.append(
            CodeExplorationTarget(
                path=f,
                module_name="docs" if f.startswith("docs") else ("tests" if "test" in f else "core"),
                why_relevant="Target identified via issue keywords, explicit mention, or module mapping.",
                target_symbols=["Relevant class, function, or section definition"],
                behavior_to_observe="Observe argument defaults, error handling conditions, and docstrings.",
                suggested_search_terms=[issue_title.split()[0].lower(), "timeout" if "timeout" in issue_title.lower() else "def "],
                evidence=IntelligenceEvidence(
                    status="verified" if f in file_tree else "inference",
                    source="repository_file_tree_grounding",
                    observed_at=observed,
                    detail=f"Target path {f} verified in repository tree.",
                ),
            )
        )

    # 3. Build Ordered Implementation Steps with Progressive Hints & Checkpoints
    steps: list[ImplementationStep] = [
        ImplementationStep(
            id="step-1",
            order=1,
            title="Inspect Existing Code & Scope the Change",
            objective=f"Examine '{target_file}' to locate where current behavior or documentation is defined.",
            why_it_matters="Prevents making changes in the wrong module and ensures you understand current logic before editing.",
            files=[target_file],
            what_to_inspect=f"Review declarations, function signatures, or subsections in {target_file}.",
            expected_outcome=f"Clear identification of the exact lines or functions in {target_file} that need adjustment.",
            dependencies=[],
            completion_criteria=f"You can point to the exact lines in {target_file} responsible for the behavior.",
            hints=[
                ProgressiveHint(
                    level=1,
                    title="Where to Start Looking",
                    content=f"Open '{target_file}' in your editor and search for terms matching the issue description.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=2,
                    title="Inspecting Parameter & Return Types",
                    content="Check existing parameter defaults, docstrings, and cross-references to surrounding modules.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=3,
                    title="Edge Case & Boundary Checks",
                    content="Look for how invalid values, timeouts, or None states are handled in this component.",
                    kind="conceptual_guidance",
                ),
            ],
            checkpoint=StepCheckpoint(
                question=f"Can you explain what {target_file} currently does before your change?",
                verification_guidance="Draft a 1-sentence description of the current behavior.",
            ),
            patch_suggestion=None,
        ),
        ImplementationStep(
            id="step-2",
            order=2,
            title="Identify and Run Relevant Tests",
            objective=f"Locate the test file ({test_ref}) that covers this component and execute it locally.",
            why_it_matters="Running existing tests validates your local development environment and establishes a baseline.",
            files=[test_ref] if test_ref in valid_paths_set else [],
            what_to_inspect=f"Check existing test assertions and fixtures in {test_ref}.",
            expected_outcome="Existing test suite passes cleanly on your local machine before modifying code.",
            dependencies=["step-1"],
            completion_criteria="You have executed the relevant test command and observed all existing tests passing.",
            hints=[
                ProgressiveHint(
                    level=1,
                    title="Finding the Right Test File",
                    content=f"Look under test directories for tests that import {Path(target_file).stem}.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=2,
                    title="Running the Focused Test Command",
                    content=f"Run the repository test command targeting {test_ref} directly rather than the entire suite.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=3,
                    title="Formulating a Reproduction Test",
                    content="Consider adding a test case that reproduces the issue before writing the fix.",
                    kind="conceptual_guidance",
                ),
            ],
            checkpoint=StepCheckpoint(
                question="Did existing tests for this component pass locally?",
                verification_guidance="Confirm exit code 0 when running the targeted test command.",
            ),
            patch_suggestion=None,
        ),
        ImplementationStep(
            id="step-3",
            order=3,
            title="Implement the Focused Change",
            objective=f"Apply the minimal, targeted modification in '{target_file}'.",
            why_it_matters="Keeps the pull request small, reviewable, and focused strictly on #{issue_number}.",
            files=[target_file],
            what_to_inspect="Keep edits minimal; adhere strictly to repository formatting and style conventions.",
            expected_outcome=f"Modified {target_file} cleanly resolving #{issue_number}.",
            dependencies=["step-1", "step-2"],
            completion_criteria="Code or documentation modified without syntax errors or formatting regressions.",
            hints=[
                ProgressiveHint(
                    level=1,
                    title="Keep Edits Surgical",
                    content="Change only what is necessary to resolve the issue. Avoid unrelated refactorings.",
                    kind="conceptual_guidance",
                ),
                ProgressiveHint(
                    level=2,
                    title="Preserving Existing Conventions",
                    content="Follow the exact quotation, docstring formatting, and naming conventions in the file.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=3,
                    title="Guarding Against Common Mistakes",
                    content="Ensure new parameters are optional or backward compatible to prevent breaking existing callers.",
                    kind="conceptual_guidance",
                ),
            ],
            checkpoint=StepCheckpoint(
                question="Does your change directly satisfy the explicit requirements of this issue?",
                verification_guidance="Check your diff against the requirements listed in the Issue Learning Brief.",
            ),
            patch_suggestion=PatchSuggestion(
                target_path=target_file,
                target_symbol="Target component",
                summary=f"Educational draft illustrating minimal change for #{issue_number}.",
                code_snippet=f"# Review and adapt for {target_file}\n# Ensure changes match existing repository code style\n",
                assumptions=["Assumes standard repository environment and dependencies."],
                expected_effect=f"Addresses #{issue_number} with minimal footprint.",
                potential_risks=["Review backwards compatibility with existing callers."],
                verification_status="unverified_educational_draft",
            ),
        ),
        ImplementationStep(
            id="step-4",
            order=4,
            title="Verify Fix & Prepare for Contribution",
            objective="Re-run tests, inspect your git diff, and confirm clean build.",
            why_it_matters="Ensures maintainers receive a high-quality contribution with zero regressions.",
            files=[target_file, test_ref] if test_ref in valid_paths_set else [target_file],
            what_to_inspect="Review `git diff` for stray whitespace, debug print statements, or unwanted files.",
            expected_outcome="All tests pass, git diff is clean, and pull request description is ready.",
            dependencies=["step-3"],
            completion_criteria="Clean local git diff and 100% passing tests.",
            hints=[
                ProgressiveHint(
                    level=1,
                    title="Diff Inspection",
                    content="Run `git diff` in your terminal to inspect every changed line.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=2,
                    title="Linter & Formatter Verification",
                    content="Run the project's linter or code formatter if specified in CONTRIBUTING.md.",
                    kind="evidence_based",
                ),
                ProgressiveHint(
                    level=3,
                    title="Drafting PR Description",
                    content="Reference issue number in the PR body (e.g. 'Fixes #{issue_number}') and summarize testing done.",
                    kind="conceptual_guidance",
                ),
            ],
            checkpoint=StepCheckpoint(
                question="Is your git diff clean and free of extraneous changes?",
                verification_guidance="Ensure only intended lines in targeted files are modified.",
            ),
            patch_suggestion=None,
        ),
    ]

    # 4. Build Implementation Approaches
    approaches = [
        ImplementationApproach(
            approach_id="approach-minimal-surgical",
            title="Minimal Surgical Change (Recommended)",
            summary=f"Modify only '{target_file}' to address reported behavior with minimal blast radius.",
            relevant_design_patterns=["Single Responsibility", "Backward Compatibility"],
            pros=[
                "Minimal risk of regressions in existing workflows",
                "Easy for maintainers to review quickly",
                "Preserves existing public APIs without breaking changes",
            ],
            cons_and_tradeoffs=[
                "May not address deeper architectural limitations if issue is symptomatic of a larger pattern",
            ],
            edge_cases=["Verify behavior when optional parameters are omitted or None."],
            regression_risks=["Low risk to unrelated components."],
            unanswered_questions=["Confirm maintainer preference on deprecation warnings if changing signatures."],
        ),
        ImplementationApproach(
            approach_id="approach-comprehensive-hardening",
            title="Comprehensive Validation & Interface Hardening",
            summary=f"Update '{target_file}' and extend test cases in '{test_ref}' with comprehensive boundary validation.",
            relevant_design_patterns=["Defensive Programming", "Regression Testing"],
            pros=[
                "Provides thorough test coverage across edge cases",
                "Documents expected behavior formally in the test suite",
            ],
            cons_and_tradeoffs=[
                "Requires more contributor time to write and verify tests",
                "Larger diff may take maintainers slightly longer to review",
            ],
            edge_cases=["Network timeouts, unexpected exception hierarchies, or malformed inputs."],
            regression_risks=["Potential test suite execution time increase."],
            unanswered_questions=["Are there existing shared test fixtures to reuse?"],
        ),
    ]

    overview = (
        f"Guided Implementation roadmap for #{issue_number}: '{issue_title}'. "
        f"Adapted for {level} level: prioritizes locating existing definitions, running focused tests, "
        f"and keeping changes minimal and reviewable."
    )

    return GuidedImplementationPlan(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        experience_level=level,  # type: ignore
        overview=overview,
        steps=steps,
        exploration_targets=exploration_targets,
        approaches=approaches,
        recommended_approach_id="approach-minimal-surgical",
        ai_status="unavailable_or_invalid",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="inference",
            source="deterministic_guided_implementation_engine",
            observed_at=observed,
            detail="Synthesized deterministic implementation plan without external model calls.",
        ),
        checked_at=observed,
    )


async def generate_guided_implementation_plan(
    repo_url: str,
    issue_number: int,
    profile: ContributorProfile,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[ModelProvider] = None,
    learning_brief: Optional[IssueLearningBrief] = None,
) -> GuidedImplementationPlan:
    """
    Generate an evidence-grounded Guided Implementation Plan for a verified issue:
    1. Validate GitHub URL.
    2. Check demo mode; load offline fixture plan if active.
    3. Ingest issue metadata, comments, file tree, docs, and M1/M2 intelligence.
    4. Call AI model provider (Gemma 4) with grounded context & 1 retry on invalid output.
    5. Ground all suggested file paths strictly against ingested file tree.
    6. Fall back safely to deterministic implementation plan on quota, timeout, or model errors.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # Validate requested model provider early
    if provider_name and not (demo or settings.DEMO_MODE):
        get_provider(provider_name)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        logger.info("Serving guided implementation plan from offline fixture dataset (demo_mode=True)")
        return load_fixture_guided_implementation(
            repo_url=repo_url,
            issue_number=issue_number,
            profile=profile,
        )

    gh = github_client or GitHubClient()
    warnings: list[str] = []

    # 1. Fetch fresh issue details and documentation
    issue_data = await gh.fetch_single_issue(owner, repo_name, issue_number)
    issue_title = issue_data.get("title", f"Issue #{issue_number}")
    issue_url = issue_data.get("html_url", f"https://github.com/{owner}/{repo_name}/issues/{issue_number}")
    issue_body = issue_data.get("body", "") or ""
    labels = [
        label.get("name") if isinstance(label, dict) else str(label)
        for label in issue_data.get("labels", [])
    ]

    docs = await gh.fetch_documentation(owner, repo_name)
    comments = await gh.fetch_issue_comments(owner, repo_name, issue_number, max_comments=4)

    # 2. Fetch file tree for grounding
    repo_meta = await gh.fetch_repo_metadata(owner, repo_name)
    file_paths, gh_trunc, app_trunc = await gh.fetch_file_tree(
        owner, repo_name, repo_meta.default_branch
    )
    is_truncated = gh_trunc or app_trunc
    if is_truncated:
        warnings.append("Repository file tree was truncated due to scale bounds (retained top 400 paths).")

    valid_paths_set = set(file_paths)

    # 3. Generate M1 Repository Intelligence Context
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
        logger.warning("Repository intelligence generation failed during guided implementation: %s", exc)

    # 4. Generate M2 Issue Learning Context (if not already provided)
    if learning_brief is None:
        try:
            learning_brief = await generate_issue_learning_brief(
                repo_url=repo_url,
                issue_number=issue_number,
                profile=profile,
                provider_name=provider_name,
                demo=demo,
                github_client=gh,
                model_provider=model_provider,
            )
        except Exception as exc:
            logger.warning("Issue learning brief generation failed during guided implementation: %s", exc)

    # 5. Check for Demo Mode or Missing Credentials
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key
    if should_skip_ai:
        reason = (
            "Demo/Fixture mode active. Showing deterministic guided implementation plan."
            if (demo or settings.DEMO_MODE)
            else "GEMINI_API_KEY is not configured. Showing deterministic guided implementation plan."
        )
        return create_deterministic_fallback_guided_plan(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            issue_body=issue_body,
            labels=labels,
            profile=profile,
            file_tree=file_paths,
            docs_metadata=docs,
            intelligence_report=intelligence_report,
            learning_brief=learning_brief,
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

    learning_brief_dict = None
    if learning_brief:
        learning_brief_dict = {
            "explanation": {
                "summary": learning_brief.explanation.summary,
                "expected_outcome": learning_brief.explanation.expected_outcome,
            },
            "requirements": [
                {"description": r.description, "classification": r.classification}
                for r in learning_brief.requirements[:4]
            ],
            "relevant_modules": learning_brief.relevant_modules[:4],
        }

    prompt_text, is_prompt_truncated = build_guided_implementation_prompt(
        profile_data=profile.model_dump(),
        issue_data={"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels},
        comments=comments,
        file_tree=file_paths,
        readme_excerpt=docs.get("readme_excerpt", ""),
        contributing_excerpt=docs.get("contributing_excerpt", ""),
        repo_intelligence=repo_intel_dict,
        learning_brief_data=learning_brief_dict,
        max_chars=settings.MAX_PROMPT_CHARS,
    )
    if is_prompt_truncated:
        warnings.append("Guided implementation prompt context exceeded character bounds and was safely truncated.")

    # 7. Call Model Provider with at most 1 retry strictly on InvalidModelOutputError
    guided_response: Optional[GuidedImplementationModelOutput] = None
    actual_model_used = settings.GEMMA_MODEL
    observed = datetime.now(timezone.utc).isoformat()

    for attempt in range(2):
        try:
            model_obj, actual_model_used = await provider.generate_json(
                task_name="guided_implementation",
                system_instruction=GUIDED_IMPLEMENTATION_SYSTEM_INSTRUCTION,
                user_prompt=prompt_text,
                output_schema=GuidedImplementationModelOutput,
            )
            guided_response = model_obj
            break
        except InvalidModelOutputError as ime:
            logger.warning("Guided implementation attempt %d produced invalid model output: %s", attempt + 1, ime)
            if attempt == 0:
                prompt_text = (
                    f"PREVIOUS ATTEMPT FAILED SCHEMA VALIDATION: {str(ime)[:200]}\n"
                    f"Please output strictly schema-valid JSON conforming to GuidedImplementationModelOutput.\n\n"
                    f"{prompt_text}"
                )
            else:
                warnings.append("AI guided implementation output invalid after retry. Falling back to deterministic plan.")
                break
        except (QuotaExceededError, AuthenticationError, SafetyBlockedError, ModelTimeoutError) as non_retryable:
            logger.warning("Non-retryable provider error (%s): %s", type(non_retryable).__name__, non_retryable)
            warnings.append(f"AI guided implementation unavailable ({type(non_retryable).__name__}). Falling back to deterministic plan.")
            break
        except ModelProviderError as mpe:
            logger.warning("Provider error on guided implementation attempt %d: %s", attempt + 1, mpe)
            warnings.append("AI guided implementation encountered an error. Falling back to deterministic plan.")
            break

    # If AI inference failed, return deterministic fallback
    if not guided_response:
        return create_deterministic_fallback_guided_plan(
            issue_number=issue_number,
            issue_title=issue_title,
            issue_url=issue_url,
            issue_body=issue_body,
            labels=labels,
            profile=profile,
            file_tree=file_paths,
            docs_metadata=docs,
            intelligence_report=intelligence_report,
            learning_brief=learning_brief,
            warning_reason="Showing deterministic guided implementation plan with grounded repository context.",
            existing_warnings=warnings,
        )

    # 8. Ground File Targets & Convert Model Objects to Schema
    grounded_exploration_targets: list[CodeExplorationTarget] = []
    dropped_paths: list[str] = []

    for target in guided_response.exploration_targets:
        if target.path in valid_paths_set:
            grounded_exploration_targets.append(
                CodeExplorationTarget(
                    path=target.path,
                    module_name=target.module_name,
                    why_relevant=target.why_relevant,
                    target_symbols=target.target_symbols,
                    behavior_to_observe=target.behavior_to_observe,
                    suggested_search_terms=target.suggested_search_terms,
                    evidence=IntelligenceEvidence(
                        status="inference",
                        source="gemma_guided_exploration_reasoning",
                        observed_at=observed,
                        detail="Model selected candidate target from verified repository file tree.",
                    ),
                )
            )
        else:
            dropped_paths.append(target.path)

    if dropped_paths:
        warnings.append(
            f"Dropped {len(dropped_paths)} ungrounded exploration file path(s) that do not exist in repository tree: {', '.join(dropped_paths[:3])}"
        )

    # Convert and ground steps
    structured_steps: list[ImplementationStep] = []
    for step in guided_response.steps:
        grounded_step_files = [f for f in step.files if f in valid_paths_set]

        # Convert hints
        hints = [
            ProgressiveHint(
                level=h.level if 1 <= h.level <= 3 else 1,
                title=h.title,
                content=h.content,
                kind="evidence_based" if h.kind.lower() == "evidence_based" else "conceptual_guidance",
            )
            for h in step.hints
        ]

        checkpoint = StepCheckpoint(
            question=step.checkpoint.question,
            verification_guidance=step.checkpoint.verification_guidance,
        )

        patch_sug = None
        if step.patch_suggestion:
            ps = step.patch_suggestion
            if ps.target_path in valid_paths_set:
                patch_sug = PatchSuggestion(
                    target_path=ps.target_path,
                    target_symbol=ps.target_symbol,
                    summary=ps.summary,
                    code_snippet=ps.code_snippet,
                    assumptions=ps.assumptions,
                    expected_effect=ps.expected_effect,
                    potential_risks=ps.potential_risks,
                    verification_status="unverified_educational_draft",
                )
            else:
                dropped_paths.append(ps.target_path)

        structured_steps.append(
            ImplementationStep(
                id=step.id,
                order=max(1, step.order),
                title=step.title,
                objective=step.objective,
                why_it_matters=step.why_it_matters,
                files=grounded_step_files,
                what_to_inspect=step.what_to_inspect,
                expected_outcome=step.expected_outcome,
                dependencies=step.dependencies,
                completion_criteria=step.completion_criteria,
                hints=hints,
                checkpoint=checkpoint,
                patch_suggestion=patch_sug,
            )
        )

    # Convert approaches
    structured_approaches = [
        ImplementationApproach(
            approach_id=appr.approach_id,
            title=appr.title,
            summary=appr.summary,
            relevant_design_patterns=appr.relevant_design_patterns,
            pros=appr.pros,
            cons_and_tradeoffs=appr.cons_and_tradeoffs,
            edge_cases=appr.edge_cases,
            regression_risks=appr.regression_risks,
            unanswered_questions=appr.unanswered_questions,
        )
        for appr in guided_response.approaches
    ]

    return GuidedImplementationPlan(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        experience_level=profile.experience_level,
        overview=guided_response.overview,
        steps=structured_steps,
        exploration_targets=grounded_exploration_targets,
        approaches=structured_approaches,
        recommended_approach_id=guided_response.recommended_approach_id or (structured_approaches[0].approach_id if structured_approaches else "default-approach"),
        ai_status="complete",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="inference",
            source="gemma_guided_implementation_engine",
            observed_at=observed,
            detail=f"Synthesized Guided Implementation Plan using {actual_model_used}.",
        ),
        checked_at=observed,
    )
