"""Verification & Review Engine for PatchLoom 2.0 (M4 VERIFY & CONTRIBUTE Pillar).

Orchestrates contributor change analysis, test discovery, isolated execution planning,
AI-assisted diff review, regression analysis, contribution readiness assessment,
and maintainer-ready PR preparation.
"""

from datetime import datetime, timezone
import logging
from typing import Optional

from app.config import settings
from app.diff_analyzer import evaluate_diff_roadmap_alignment, parse_git_diff
from app.github_client import (
    GitHubClient,
    IssueClosedError,
    IssueNotFoundError,
    parse_and_validate_github_url,
)
from app.prompts import (
    DRAFT_PR_SYSTEM_INSTRUCTION,
    ModelDraftPR,
    VERIFICATION_SYSTEM_INSTRUCTION,
    VerificationModelOutput,
    build_prepare_pr_prompt,
    build_verification_review_prompt,
)
from app.providers import get_provider
from app.providers.base import (
    InvalidModelOutputError,
    ModelProvider,
    QuotaExceededError,
)
from app.repo_intelligence import generate_repository_intelligence
from app.schemas import (
    ContributorProfile,
    DraftPR,
    ImplementationStep,
    IntelligenceEvidence,
    ParsedDiff,
    ReadinessAssessment,
    RegressionRisk,
    RepositoryIntelligenceReport,
    ReviewFinding,
    TestExecutionPlan,
    TestExecutionResult,
    VerificationAnalysisReport,
)
from app.test_discovery import discover_relevant_tests

logger = logging.getLogger(__name__)


def create_deterministic_fallback_verification_report(
    issue_number: int,
    issue_title: str,
    repo_url: str,
    parsed_diff: ParsedDiff,
    file_tree: list[str],
    intelligence_report: Optional[RepositoryIntelligenceReport] = None,
    planned_steps: Optional[list[ImplementationStep]] = None,
    warning_reason: str = "Showing deterministic verification analysis without external AI model calls.",
    existing_warnings: Optional[list[str]] = None,
) -> VerificationAnalysisReport:
    """
    Synthesize an evidence-grounded verification report deterministically without AI.
    Used in offline demo mode and when model provider inference is unavailable or fails.
    """
    observed = datetime.now(timezone.utc).isoformat()
    warnings = list(existing_warnings or [])
    warnings.append(warning_reason)

    # 1. Roadmap alignment
    alignment_summary, unrelated_files = evaluate_diff_roadmap_alignment(
        parsed_diff, planned_steps
    )

    # 2. Test discovery
    test_profile = intelligence_report.test_profile if intelligence_report else None
    modules = intelligence_report.modules if intelligence_report else None
    discovered_tests, suggested_plan = discover_relevant_tests(
        parsed_diff=parsed_diff,
        file_tree=file_tree,
        test_profile=test_profile,
        modules=modules,
        planned_steps=planned_steps,
    )

    # 3. Deterministic review findings
    findings: list[ReviewFinding] = []
    finding_counter = 1

    has_test_changes = any(
        "test" in f.path.lower() for f in parsed_diff.files
    )
    has_source_changes = any(
        not ("test" in f.path.lower() or f.path.lower().endswith((".md", ".rst", ".txt")))
        for f in parsed_diff.files
    )

    if has_source_changes and not has_test_changes:
        findings.append(
            ReviewFinding(
                finding_id=f"finding-{finding_counter}",
                severity="medium",
                category="test_coverage",
                title="Source files modified without accompanying test updates",
                explanation=(
                    f"The diff modifies {len(parsed_diff.files)} file(s), but contains no changes "
                    "in test files. Open-source maintainers usually require regression tests for source changes."
                ),
                evidence=f"Touched files: {', '.join(f.path for f in parsed_diff.files[:3])}",
                file_path=parsed_diff.files[0].path if parsed_diff.files else "README.md",
                line_range=None,
                why_it_matters="Increases risk of undetected regressions and slows maintainer review.",
                suggested_action="Add or update a corresponding test case in the test suite.",
                confidence="high",
            )
        )
        finding_counter += 1

    # Check for TODO comments left in diff
    if "TODO" in parsed_diff.raw_diff_sample or "FIXME" in parsed_diff.raw_diff_sample:
        findings.append(
            ReviewFinding(
                finding_id=f"finding-{finding_counter}",
                severity="low",
                category="other",
                title="Unresolved TODO or FIXME comment detected in diff",
                explanation="The diff introduces or modifies lines containing 'TODO' or 'FIXME' markers.",
                evidence="Detected 'TODO' / 'FIXME' in added diff lines.",
                file_path=parsed_diff.files[0].path if parsed_diff.files else "README.md",
                line_range=None,
                why_it_matters="Maintainers may consider unaddressed TODO items as an incomplete submission.",
                suggested_action="Resolve the temporary marker or clarify its future milestone in PR notes.",
                confidence="high",
            )
        )
        finding_counter += 1

    # 4. Deterministic regression risks based on M1 modules
    regression_risks: list[RegressionRisk] = []
    if intelligence_report and intelligence_report.modules:
        diff_paths_lower = [f.path.lower() for f in parsed_diff.files]
        for mod in intelligence_report.modules:
            mod_files_lower = [mf.lower() for mf in mod.files]
            overlap = [p for p in diff_paths_lower if p in mod_files_lower]
            if overlap:
                regression_risks.append(
                    RegressionRisk(
                        affected_module_or_file=mod.name,
                        risk_type="directly_affected",
                        evidence=f"Diff modifies {len(overlap)} file(s) within component '{mod.name}' ({', '.join(overlap[:2])}).",
                        potential_impact=f"Potential regression in {mod.likely_responsibility}.",
                        suggested_verification=f"Run tests covering module '{mod.name}'.",
                        confidence="high",
                    )
                )

    if not regression_risks and parsed_diff.files:
        regression_risks.append(
            RegressionRisk(
                affected_module_or_file=parsed_diff.files[0].path,
                risk_type="potentially_affected",
                evidence="File modified in contributor diff.",
                potential_impact="Behavioral change in modified file.",
                suggested_verification="Inspect git diff and run targeted local tests.",
                confidence="medium",
            )
        )

    # 5. Deterministic readiness assessment
    outstanding: list[str] = []
    if parsed_diff.total_files == 0:
        status = "insufficient_evidence"
        summary = "No diff changes were provided to verify."
        outstanding.append("Provide a non-empty git diff to begin verification.")
    elif not discovered_tests:
        status = "needs_attention"
        summary = "Changes analyzed, but no relevant test files could be identified in repository tree."
        outstanding.append("Verify whether the repository has test suites or manual verification guides.")
    else:
        status = "needs_attention"
        summary = f"Diff touches {parsed_diff.total_files} file(s). Relevant tests identified ({len(discovered_tests)} candidate tests), pending test execution."
        outstanding.append(f"Execute discovered tests ({discovered_tests[0].test_file}) inside the isolated container.")

    readiness = ReadinessAssessment(
        status=status,  # type: ignore
        summary=summary,
        outstanding_items=outstanding,
        checklist_status={
            "diff_parsed": parsed_diff.total_files > 0,
            "tests_discovered": len(discovered_tests) > 0,
            "tests_executed": False,
            "review_findings_resolved": len(findings) == 0,
        },
    )

    return VerificationAnalysisReport(
        issue_number=issue_number,
        issue_title=issue_title,
        repo_url=repo_url,
        parsed_diff=parsed_diff,
        roadmap_alignment_summary=alignment_summary,
        potentially_unrelated_files=unrelated_files,
        discovered_tests=discovered_tests,
        suggested_execution_plan=suggested_plan,
        review_findings=findings,
        regression_risks=regression_risks,
        readiness=readiness,
        ai_status="unavailable_or_invalid",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="inference",
            source="deterministic_verification_engine",
            observed_at=observed,
            detail="Synthesized deterministic verification report without external model calls.",
        ),
        checked_at=observed,
    )


async def generate_verification_analysis(
    repo_url: str,
    issue_number: int,
    diff_text: str,
    profile: Optional[ContributorProfile] = None,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[ModelProvider] = None,
    planned_steps: Optional[list[ImplementationStep]] = None,
) -> VerificationAnalysisReport:
    """
    Main orchestration function for POST /api/verification/analyze.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        from app.fixtures_loader import load_fixture_verification
        return load_fixture_verification(
            repo_url=repo_url,
            issue_number=issue_number,
            profile=profile,
            diff_text=diff_text,
            planned_steps=planned_steps,
        )

    observed = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    # 1. Parse diff deterministically
    parsed_diff = parse_git_diff(diff_text)
    if parsed_diff.warnings:
        warnings.extend(parsed_diff.warnings)

    gh = github_client or GitHubClient()

    # 2. Fetch issue details and file tree
    issue_data = await gh.fetch_single_issue(owner, repo_name, issue_number)
    issue_title = issue_data.get("title", f"Issue #{issue_number}")
    issue_body = issue_data.get("body", "") or ""
    labels = [
        label.get("name") if isinstance(label, dict) else str(label)
        for label in issue_data.get("labels", [])
    ]

    docs = await gh.fetch_documentation(owner, repo_name)
    repo_meta = await gh.fetch_repo_metadata(owner, repo_name)
    file_paths, gh_trunc, app_trunc = await gh.fetch_file_tree(
        owner, repo_name, repo_meta.default_branch
    )
    is_truncated = gh_trunc or app_trunc
    if is_truncated:
        warnings.append("Repository file tree was truncated due to scale bounds (top 400 paths retained).")

    # 3. Generate M1 Repository Intelligence Context
    cand_issue_dicts = [{"number": issue_number, "title": issue_title, "body": issue_body, "labels": labels}]
    intel = generate_repository_intelligence(
        owner=owner,
        repo_name=repo_name,
        languages=repo_meta.languages or [],
        file_tree=file_paths,
        docs_metadata=docs,
        ci_evidence=repo_meta.ci_evidence,
        candidate_issues=cand_issue_dicts,
        is_truncated=is_truncated,
    )

    # 4. Test discovery & roadmap alignment
    alignment_summary, unrelated_files = evaluate_diff_roadmap_alignment(parsed_diff, planned_steps)
    discovered_tests, suggested_plan = discover_relevant_tests(
        parsed_diff=parsed_diff,
        file_tree=file_paths,
        test_profile=intel.test_profile,
        modules=intel.modules,
        planned_steps=planned_steps,
    )

    # 5. Check for Demo Mode or Missing Model Keys
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key
    if should_skip_ai:
        reason = (
            "Demo/Fixture mode active. Showing deterministic verification report."
            if (demo or settings.DEMO_MODE)
            else "GEMINI_API_KEY is not configured. Showing deterministic verification report."
        )
        report = create_deterministic_fallback_verification_report(
            issue_number=issue_number,
            issue_title=issue_title,
            repo_url=repo_url,
            parsed_diff=parsed_diff,
            file_tree=file_paths,
            intelligence_report=intel,
            planned_steps=planned_steps,
            warning_reason=reason,
            existing_warnings=warnings,
        )
        if demo or settings.DEMO_MODE:
            report.ai_status = "complete"
        return report

    # 6. Call AI Provider for Grounded Diff Review & Regression Analysis
    provider = model_provider or get_provider(provider_name)
    repo_intel_dict = {
        "primary_language": intel.languages.primary if intel.languages else "unknown",
        "project_type": intel.project_type,
        "modules": [m.name for m in intel.modules],
        "test_frameworks": intel.test_profile.frameworks,
    }
    steps_dict = [s.model_dump() for s in (planned_steps or [])]
    parsed_files_dict = [f.model_dump() for f in parsed_diff.files]

    prompt_text, is_prompt_truncated = build_verification_review_prompt(
        issue_data={"number": issue_number, "title": issue_title, "body": issue_body},
        diff_text=diff_text,
        parsed_files=parsed_files_dict,
        file_tree=file_paths,
        repo_intelligence=repo_intel_dict,
        planned_roadmap_steps=steps_dict,
    )
    if is_prompt_truncated:
        warnings.append("Verification prompt payload exceeded 60,000 character hard cap and was cleanly bounded.")

    model_response: Optional[VerificationModelOutput] = None
    try:
        model_obj, _ = await provider.generate_json(
            task_name="verification_review",
            system_instruction=VERIFICATION_SYSTEM_INSTRUCTION,
            prompt=prompt_text,
            output_schema=VerificationModelOutput,
        )
        if isinstance(model_obj, VerificationModelOutput):
            model_response = model_obj
    except InvalidModelOutputError as exc:
        logger.warning("Verification review attempt 1 failed with invalid schema: %s. Retrying once.", exc)
        try:
            model_obj, _ = await provider.generate_json(
                task_name="verification_review_retry",
                system_instruction=VERIFICATION_SYSTEM_INSTRUCTION,
                prompt=prompt_text + "\n\nCRITICAL RETRY: Output strictly valid JSON conforming to VerificationModelOutput.",
                output_schema=VerificationModelOutput,
            )
            if isinstance(model_obj, VerificationModelOutput):
                model_response = model_obj
        except Exception as retry_exc:
            logger.error("Verification review retry failed: %s", retry_exc)
    except (QuotaExceededError, Exception) as exc:
        logger.error("Model provider error during verification review: %s", exc)

    if not model_response:
        return create_deterministic_fallback_verification_report(
            issue_number=issue_number,
            issue_title=issue_title,
            repo_url=repo_url,
            parsed_diff=parsed_diff,
            file_tree=file_paths,
            intelligence_report=intel,
            planned_steps=planned_steps,
            warning_reason="Showing deterministic verification report due to model unavailability.",
            existing_warnings=warnings,
        )

    # 7. Ground Review Findings and Regression Risks
    valid_paths_set = set(file_paths) | {f.path for f in parsed_diff.files}
    grounded_findings: list[ReviewFinding] = []

    valid_severities = {"critical", "high", "medium", "low", "informational"}
    valid_categories = {
        "logic_error",
        "edge_case",
        "error_handling",
        "input_validation",
        "security",
        "resource_management",
        "regression",
        "test_coverage",
        "other",
    }

    dropped_paths: list[str] = []
    for idx, f in enumerate(model_response.review_findings):
        # File grounding check: file must exist in tree or diff
        if f.file_path not in valid_paths_set:
            dropped_paths.append(f.file_path)
            continue

        sev = f.severity.lower() if f.severity.lower() in valid_severities else "medium"
        cat = f.category.lower() if f.category.lower() in valid_categories else "other"
        conf = f.confidence.lower() if f.confidence.lower() in ("high", "medium", "low") else "medium"

        grounded_findings.append(
            ReviewFinding(
                finding_id=f.finding_id or f"finding-{idx + 1}",
                severity=sev,  # type: ignore
                category=cat,  # type: ignore
                title=f.title,
                explanation=f.explanation,
                evidence=f.evidence or "Observed in diff hunk.",
                file_path=f.file_path,
                line_range=f.line_range,
                why_it_matters=f.why_it_matters,
                suggested_action=f.suggested_action,
                confidence=conf,  # type: ignore
            )
        )

    if dropped_paths:
        warnings.append(
            f"Dropped {len(dropped_paths)} review finding(s) referencing paths not present in repository or diff: {', '.join(dropped_paths[:3])}."
        )

    grounded_risks: list[RegressionRisk] = []
    for r in model_response.regression_risks:
        r_type = r.risk_type.lower() if r.risk_type.lower() in ("directly_affected", "potentially_affected", "unknown") else "potentially_affected"
        r_conf = r.confidence.lower() if r.confidence.lower() in ("high", "medium", "low") else "medium"
        grounded_risks.append(
            RegressionRisk(
                affected_module_or_file=r.affected_module_or_file,
                risk_type=r_type,  # type: ignore
                evidence=r.evidence,
                potential_impact=r.potential_impact,
                suggested_verification=r.suggested_verification,
                confidence=r_conf,  # type: ignore
            )
        )

    # Convert readiness
    rd_status = model_response.readiness.status.lower() if model_response.readiness.status.lower() in ("ready_for_review", "needs_attention", "insufficient_evidence") else "needs_attention"
    readiness = ReadinessAssessment(
        status=rd_status,  # type: ignore
        summary=model_response.readiness.summary,
        outstanding_items=model_response.readiness.outstanding_items,
        checklist_status={
            "diff_parsed": parsed_diff.total_files > 0,
            "tests_discovered": len(discovered_tests) > 0,
            "tests_executed": False,
            "review_findings_resolved": len([f for f in grounded_findings if f.severity in ("critical", "high")]) == 0,
        },
    )

    return VerificationAnalysisReport(
        issue_number=issue_number,
        issue_title=issue_title,
        repo_url=repo_url,
        parsed_diff=parsed_diff,
        roadmap_alignment_summary=model_response.roadmap_alignment_summary or alignment_summary,
        potentially_unrelated_files=model_response.potentially_unrelated_files or unrelated_files,
        discovered_tests=discovered_tests,
        suggested_execution_plan=suggested_plan,
        review_findings=grounded_findings,
        regression_risks=grounded_risks,
        readiness=readiness,
        ai_status="complete",
        warnings=warnings,
        evidence=IntelligenceEvidence(
            status="verified",
            source="gemma_verification_review_engine",
            observed_at=observed,
            detail="Gemma 4 evaluated diff against repository intelligence and implementation steps.",
        ),
        checked_at=observed,
    )


async def generate_draft_pr(
    repo_url: str,
    issue_number: int,
    diff_text: str,
    profile: Optional[ContributorProfile] = None,
    execution_result: Optional[TestExecutionResult] = None,
    review_findings: Optional[list[ReviewFinding]] = None,
    regression_risks: Optional[list[RegressionRisk]] = None,
    readiness: Optional[ReadinessAssessment] = None,
    provider_name: Optional[str] = None,
    demo: bool = False,
    github_client: Optional[GitHubClient] = None,
    model_provider: Optional[ModelProvider] = None,
) -> DraftPR:
    """
    Generate a maintainer-ready draft PR package built strictly from verified context.
    """
    owner, repo_name = parse_and_validate_github_url(repo_url)

    # 0. Offline Fixture/Demo Mode
    if demo or settings.DEMO_MODE:
        from app.fixtures_loader import load_fixture_draft_pr
        return load_fixture_draft_pr(
            repo_url=repo_url,
            issue_number=issue_number,
            diff_text=diff_text,
            execution_result=execution_result,
            review_findings=review_findings,
            regression_risks=regression_risks,
            readiness=readiness,
        )

    gh = github_client or GitHubClient()
    issue_data = await gh.fetch_single_issue(owner, repo_name, issue_number)
    issue_title = issue_data.get("title", f"Issue #{issue_number}")
    issue_body = issue_data.get("body", "") or ""

    parsed_diff = parse_git_diff(diff_text)

    # Classify tests performed accurately
    tests_performed: dict[str, list[str]] = {
        "executed_passed": [],
        "executed_failed": [],
        "not_executed": [],
        "manually_verified": [],
    }

    if execution_result:
        cmd_str = f"{execution_result.command} (exit code: {execution_result.exit_code})"
        if execution_result.status == "passed":
            tests_performed["executed_passed"].append(cmd_str)
        elif execution_result.status == "failed":
            tests_performed["executed_failed"].append(cmd_str)
        else:
            tests_performed["not_executed"].append(f"{cmd_str} [{execution_result.status}]")

    # In demo mode or fallback:
    should_skip_ai = demo or settings.DEMO_MODE or not settings.has_gemini_key
    if should_skip_ai:
        return DraftPR(
            title=f"fix({parsed_diff.files[0].path.split('/')[0] if parsed_diff.files else 'core'}): resolve issue #{issue_number}",
            summary_of_changes=f"Addresses issue #{issue_number} ('{issue_title}') by modifying {parsed_diff.total_files} file(s) (+{parsed_diff.lines_added}/-{parsed_diff.lines_removed} lines).",
            problem_addressed=f"Resolves requirements described in #{issue_number}: {issue_title}.",
            implementation_overview=f"Updated {', '.join(f.path for f in parsed_diff.files[:3])}.",
            tests_performed=tests_performed,
            known_limitations=[
                "Verification performed in offline demo mode." if demo else "Isolated execution pending."
            ],
            remaining_concerns=[
                "Please verify edge cases during maintainer review."
            ],
            manual_verification_checklist=[
                "Local tests executed and passing",
                "Documentation and docstrings updated",
                "Git diff clean of debug prints and temporary comments",
            ],
        )

    provider = model_provider or get_provider(provider_name)
    test_summary = (
        f"Status: {execution_result.status}, command: {execution_result.command}, exit_code: {execution_result.exit_code}"
        if execution_result
        else "No automated tests were executed prior to draft generation."
    )
    findings_summary = (
        f"{len(review_findings or [])} review finding(s) detected. Readiness status: {readiness.status if readiness else 'needs_attention'}."
    )

    prompt_text, _ = build_prepare_pr_prompt(
        issue_data={"number": issue_number, "title": issue_title, "body": issue_body},
        diff_summary=f"{parsed_diff.total_files} files changed (+{parsed_diff.lines_added}/-{parsed_diff.lines_removed} lines).",
        parsed_files=[f.model_dump() for f in parsed_diff.files],
        test_results_summary=test_summary,
        review_findings_summary=findings_summary,
    )

    try:
        model_obj, _ = await provider.generate_json(
            task_name="prepare_pr",
            system_instruction=DRAFT_PR_SYSTEM_INSTRUCTION,
            prompt=prompt_text,
            output_schema=ModelDraftPR,
        )
        if isinstance(model_obj, ModelDraftPR):
            return DraftPR(
                title=model_obj.title,
                summary_of_changes=model_obj.summary_of_changes,
                problem_addressed=model_obj.problem_addressed,
                implementation_overview=model_obj.implementation_overview,
                tests_performed=tests_performed,
                known_limitations=model_obj.known_limitations,
                remaining_concerns=model_obj.remaining_concerns,
                manual_verification_checklist=model_obj.manual_verification_checklist,
            )
    except Exception as exc:
        logger.warning("AI PR preparation failed: %s. Using deterministic fallback.", exc)

    return DraftPR(
        title=f"fix: address issue #{issue_number} ({issue_title[:50]})",
        summary_of_changes=f"Modifies {parsed_diff.total_files} file(s) to address #{issue_number}.",
        problem_addressed=f"Resolves requirements stated in #{issue_number}.",
        implementation_overview=f"Touches {', '.join(f.path for f in parsed_diff.files[:3])}.",
        tests_performed=tests_performed,
        known_limitations=[],
        remaining_concerns=[],
        manual_verification_checklist=[
            "Verified test suite execution",
            "Inspected git diff for unintended changes",
        ],
    )
