"""Fixture loader for offline demo mode and hermetic testing."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas import (
    AnalyzeResponse,
    CandidateIssue,
    CodeExplorationTarget,
    ContributorProfile,
    GuidedImplementationPlan,
    ImplementationApproach,
    ImplementationStep,
    IntelligenceEvidence,
    IssueExplanation,
    IssueLearningBrief,
    IssueRequirement,
    LearningConcept,
    LearningObjective,
    PatchSuggestion,
    PlanNote,
    PlanResponse,
    PlanStep,
    ProgressiveHint,
    ReadinessChecklistItem,
    RelevantInvestigationFile,
    RepoMetadata,
    SignalEvidence,
    StepCheckpoint,
    VerificationAnalysisReport,
    DraftPR,
    TestExecutionResult,
    ReviewFinding,
    RegressionRisk,
    ReadinessAssessment,
)
from app.repo_intelligence import (
    generate_repository_intelligence,
    map_issue_to_repository_modules,
)

logger = logging.getLogger(__name__)

# Search paths for fixtures/ directory
CANDIDATE_PATHS = [
    Path(__file__).resolve().parent.parent.parent / "fixtures",
    Path.cwd() / "fixtures",
    Path(__file__).resolve().parent.parent / "fixtures",
]


def get_fixtures_dir() -> Path:
    for p in CANDIDATE_PATHS:
        if p.exists() and p.is_dir():
            return p
    return CANDIDATE_PATHS[0]


def get_fixture_data_for_url(repo_url: str) -> dict:
    fixtures_dir = get_fixtures_dir()
    normalized = repo_url.lower()

    if "express" in normalized:
        fixture_file = fixtures_dir / "partial_evidence.json"
    elif "uvicorn" in normalized or "testrepo" in normalized:
        fixture_file = fixtures_dir / "fallback_demo.json"
    else:
        # Default scenario: good fit
        fixture_file = fixtures_dir / "good_fit.json"

    if not fixture_file.exists():
        raise FileNotFoundError(f"Fixture file not found: {fixture_file}")

    with open(fixture_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fixture_analysis(
    repo_url: str,
    profile: Optional[ContributorProfile] = None,
    provider_name: Optional[str] = None,
) -> AnalyzeResponse:
    """Load an offline fixture analysis response with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    repo_data = data["repo"]

    has_ci_val = repo_data.get("has_ci", True)
    ci_status_val = "detected" if has_ci_val is True else ("none_detected" if has_ci_val is False else "unknown")

    repo_meta = RepoMetadata(
        owner=repo_data["owner"],
        name=repo_data["name"],
        description=repo_data.get("description"),
        default_branch=repo_data.get("default_branch", "main"),
        languages=repo_data.get("languages", []),
        open_issues_count=repo_data.get("open_issues_count", 0),
        has_readme=repo_data.get("has_readme", True),
        has_contributing=repo_data.get("has_contributing", False),
        has_ci=has_ci_val,
        ci_status=repo_data.get("ci_status", ci_status_val),
        ci_evidence=SignalEvidence(
            status="verified" if has_ci_val is not None else "unknown",
            source="fixture_snapshot",
            value={"status": ci_status_val, "files": [".github/workflows/ci.yml"] if has_ci_val else []},
        ),
        tree_truncated=repo_data.get("tree_truncated", False),
    )

    candidates: list[CandidateIssue] = []
    for raw in data.get("issues", []):
        signals_map = {}
        for sig_name, sig_dict in raw.get("signals", {}).items():
            signals_map[sig_name] = SignalEvidence(
                status=sig_dict["status"],
                source=sig_dict["source"],
                observed_at=sig_dict.get("observed_at", "2026-10-18T10:00:00Z"),
                value=sig_dict.get("value"),
            )

        c = CandidateIssue(
            number=raw["number"],
            title=raw["title"],
            url=raw["url"],
            labels=raw.get("labels", []),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            comments_count=raw.get("comments_count", 0),
            viability_score=raw["viability_score"],
            viability_band=raw["viability_band"],
            signals=signals_map,
            negative_factors=raw.get("negative_factors", []),
            unknown_factors=raw.get("unknown_factors", []),
            fit_score=raw.get("fit_score"),
            final_score=raw.get("final_score"),
            matching_skills=raw.get("matching_skills", []),
            skill_gaps=raw.get("skill_gaps", []),
            estimated_hours=raw.get("estimated_hours"),
            likely_files=raw.get("likely_files", []),
            reason=raw.get("reason"),
            risks=raw.get("risks", []),
            inferences=raw.get("inferences", []),
        )
        candidates.append(c)

    # Generate deterministic repository intelligence from fixture data
    file_tree = data.get("file_tree", [])
    docs = data.get("docs", {})
    cand_dicts = [
        {
            "number": raw["number"],
            "title": raw["title"],
            "body": raw.get("body", "") or "",
            "labels": raw.get("labels", []),
        }
        for raw in data.get("issues", [])
    ]
    intelligence = generate_repository_intelligence(
        owner=repo_data["owner"],
        repo_name=repo_data["name"],
        languages=repo_data.get("languages", []),
        file_tree=file_tree,
        docs_metadata=docs,
        ci_evidence=repo_meta.ci_evidence,
        candidate_issues=cand_dicts,
        is_truncated=repo_meta.tree_truncated,
    )

    if intelligence and intelligence.issue_mappings:
        mapping_by_num = {m.issue_number: m for m in intelligence.issue_mappings}
        for c in candidates:
            c.module_mapping = mapping_by_num.get(c.number)

    # Determine ai_status
    any_fit = any(c.fit_score is not None for c in candidates)
    ai_status = "complete" if any_fit else "unavailable_or_invalid"

    warnings = [
        "Demo/Fixture mode active. Showing validated offline snapshot data without external GitHub or model calls."
    ]

    return AnalyzeResponse(
        repo=repo_meta,
        provider=provider_name or "fixture_demo",
        actual_model="fixture-snapshot",
        ai_status=ai_status,
        issues=candidates,
        warnings=warnings,
        intelligence=intelligence,
    )


def load_fixture_plan(
    repo_url: str,
    issue_number: int,
    profile: ContributorProfile,
) -> PlanResponse:
    """Load an offline fixture plan response with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    plans = data.get("plans", {})
    plan_data = plans.get(str(issue_number))

    if not plan_data:
        # If the requested issue has no pre-saved plan in the fixture, construct one from fixture context
        matched_issue = next((i for i in data.get("issues", []) if i["number"] == issue_number), None)
        title = matched_issue["title"] if matched_issue else f"Issue #{issue_number}"
        url = matched_issue["url"] if matched_issue else f"{repo_url}/issues/{issue_number}"
        tree = data.get("file_tree", [])
        files = [p for p in tree if any(k in p.lower() for k in ("test", "main", "doc", "src"))][:2]

        return PlanResponse(
            issue_number=issue_number,
            issue_title=title,
            issue_url=url,
            summary=f"Deterministic demo implementation plan for #{issue_number}.",
            steps=[
                PlanStep(
                    title="Review repository documentation and tests",
                    detail=f"Examine relevant files in the repository for #{issue_number}.",
                    kind="verified",
                    files=files[:1],
                ),
                PlanStep(
                    title="Implement changes locally",
                    detail="Make minimal, tested changes according to contributor guidelines.",
                    kind="inference",
                    files=files,
                ),
                PlanStep(
                    title="Run test suite",
                    detail="Execute tests locally to ensure no regressions.",
                    kind="inference",
                    files=[],
                ),
            ],
            setup_guidance=PlanNote(
                status="verified" if data.get("docs", {}).get("has_setup_guide") else "unknown",
                notes="Setup guide available in repository documentation." if data.get("docs", {}).get("has_setup_guide") else "No documented setup instructions found in repository.",
            ),
            test_guidance=PlanNote(
                status="verified" if data.get("docs", {}).get("has_test_guide") else "unknown",
                notes="Test suite runner and commands documented in repository." if data.get("docs", {}).get("has_test_guide") else "No specific test instructions documented.",
            ),
            checklist=[
                f"Verify issue #{issue_number} requirements",
                "Make targeted modifications",
                "Execute local tests",
            ],
            pr_title=f"fix: address #{issue_number} - {title}",
            pr_description_draft=f"## Summary of Changes\nAddresses #{issue_number}.\n\n## Testing Done\n- Verified locally.\n\nFixes #{issue_number}",
            open_questions_for_maintainer=[],
            ai_status="complete",
            warnings=["Demo/Fixture mode active. Showing validated offline snapshot plan."],
        )

    # Use exact fixture plan
    steps = [
        PlanStep(
            title=s["title"],
            detail=s["detail"],
            kind=s.get("kind", "inference"),
            files=s.get("files", []),
        )
        for s in plan_data["steps"]
    ]

    return PlanResponse(
        issue_number=plan_data["issue_number"],
        issue_title=plan_data["issue_title"],
        issue_url=plan_data["issue_url"],
        summary=plan_data["summary"],
        steps=steps,
        setup_guidance=PlanNote(
            status=plan_data["setup_guidance"]["status"],
            notes=plan_data["setup_guidance"]["notes"],
        ),
        test_guidance=PlanNote(
            status=plan_data["test_guidance"]["status"],
            notes=plan_data["test_guidance"]["notes"],
        ),
        checklist=plan_data.get("checklist", []),
        pr_title=plan_data["pr_title"],
        pr_description_draft=plan_data["pr_description_draft"],
        open_questions_for_maintainer=plan_data.get("open_questions_for_maintainer", []),
        ai_status=plan_data.get("ai_status", "complete"),
        warnings=plan_data.get("warnings", ["Demo/Fixture mode active."]),
    )


def load_fixture_learn(
    repo_url: str,
    issue_number: int,
    profile: Optional[ContributorProfile] = None,
) -> IssueLearningBrief:
    """Load an offline fixture issue learning brief with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    briefs = data.get("learning_briefs", {})
    brief_data = briefs.get(str(issue_number))
    observed = datetime.now(timezone.utc).isoformat()
    level = profile.experience_level if profile else "beginner"

    if not brief_data:
        # Construct deterministic brief from fixture data
        matched_issue = next((i for i in data.get("issues", []) if i["number"] == issue_number), None)
        title = matched_issue["title"] if matched_issue else f"Issue #{issue_number}"
        url = matched_issue["url"] if matched_issue else f"{repo_url}/issues/{issue_number}"
        body = matched_issue.get("body", "") if matched_issue else ""
        tree = data.get("file_tree", [])
        docs = data.get("docs", {})
        repo_data = data.get("repo", {})

        # Compute intelligence to map modules
        intel = generate_repository_intelligence(
            owner=repo_data.get("owner", "org"),
            repo_name=repo_data.get("name", "repo"),
            languages=repo_data.get("languages", []),
            file_tree=tree,
            docs_metadata=docs,
            candidate_issues=[{"number": issue_number, "title": title, "body": body, "labels": matched_issue.get("labels", []) if matched_issue else []}],
            is_truncated=repo_data.get("tree_truncated", False),
        )

        mapping = map_issue_to_repository_modules(
            issue={"number": issue_number, "title": title, "body": body, "labels": matched_issue.get("labels", []) if matched_issue else []},
            file_tree=tree,
            modules=intel.modules,
            docs_text=docs.get("readme_excerpt", ""),
        )

        investigation_targets = [
            RelevantInvestigationFile(
                path=c.path,
                module_name=c.module_name,
                why_relevant=f"Fixture target identified via keyword overlap ({'; '.join(c.reasons[:2])}).",
                what_to_inspect="Review function signatures, documentation strings, or error checks.",
                kind="candidate",
                evidence=c.evidence,
            )
            for c in mapping.candidate_files[:3]
        ]
        if not investigation_targets:
            fallback_files = [p for p in tree if any(k in p.lower() for k in ("main", "doc", "test", "src"))][:2]
            for f in fallback_files:
                investigation_targets.append(
                    RelevantInvestigationFile(
                        path=f,
                        module_name="general",
                        why_relevant="Plausible core file from repository tree.",
                        what_to_inspect="Review code structure and tests.",
                        kind="candidate",
                        evidence=IntelligenceEvidence(
                            status="inference",
                            source="fixture_tree",
                            observed_at=observed,
                            detail=f"Candidate path {f}.",
                        ),
                    )
                )

        explanation = IssueExplanation(
            summary=f"Offline learning brief for #{issue_number}: '{title}'.",
            problem_description=f"Issue #{issue_number} reports an improvement or bug in the repository component.",
            why_it_matters="Resolving this issue improves developer ergonomics and project documentation clarity.",
            expected_outcome=f"Clear, tested resolution of #{issue_number} matching contributor expectations.",
            explicit_requirements=[f"Address requirements stated in #{issue_number}."],
            constraints_and_conditions=["Ensure compatibility with existing tests and contributor guidelines."],
            ambiguities_and_unanswered_questions=[],
            experience_adaptation_note=f"Adapted for {level} level: emphasizes foundational clarity and guided investigation targets.",
        )

        concepts = [
            LearningConcept(
                name="Repository Architecture & Layout",
                explanation="How files, tests, and documentation are organized across this repository.",
                why_it_matters="Helps you identify which module is responsible for the behavior.",
                prerequisites=["Basic Git version control"],
                learning_order=1,
                difficulty="beginner",
            ),
            LearningConcept(
                name="Test Suite Verification",
                explanation="Running unit tests locally to verify expected behavior.",
                why_it_matters="Ensures proposed changes do not cause regressions.",
                prerequisites=["Command-line terminal"],
                learning_order=2,
                difficulty="beginner",
            ),
        ]

        objectives = [
            LearningObjective(
                title="Locate the Target Code",
                description=f"Inspect {', '.join(t.path for t in investigation_targets[:2])} to understand current implementation.",
                relevance="Grounds your contribution in actual repository code.",
                completion_criterion="You can locate the functions or documentation sections being modified.",
            ),
            LearningObjective(
                title="Verify Local Test Execution",
                description="Run the repository test suite locally.",
                relevance="Validates your local development environment before writing code.",
                completion_criterion="Existing tests execute and pass without unexpected errors.",
            ),
        ]

        checklist = [
            ReadinessChecklistItem(
                category="problem_understanding",
                item=f"Can you explain the problem in #{issue_number} in your own words?",
                guidance="Draft a 2-sentence summary of the expected change.",
            ),
            ReadinessChecklistItem(
                category="architecture_components",
                item="Have you inspected the candidate investigation files?",
                guidance=f"Check {', '.join(t.path for t in investigation_targets[:2])}.",
            ),
            ReadinessChecklistItem(
                category="testing_approach",
                item="Do you know how to run tests locally for this component?",
                guidance="Refer to the repository's test guidelines or documentation.",
            ),
        ]

        return IssueLearningBrief(
            issue_number=issue_number,
            issue_title=title,
            issue_url=url,
            experience_level=level,  # type: ignore
            explanation=explanation,
            requirements=[
                IssueRequirement(
                    description=f"Address issue #{issue_number}: {title}",
                    source="issue_description",
                    supporting_evidence=title,
                    classification="explicit",
                    confidence="high",
                )
            ],
            relevant_modules=mapping.candidate_modules,
            investigation_targets=investigation_targets,
            related_tests_and_docs=[f"{d}/" for d in intel.test_profile.test_directories] + (["README.md"] if intel.documentation_profile.has_readme else []),
            concepts=concepts,
            learning_objectives=objectives,
            readiness_checklist=checklist,
            unresolved_questions=[],
            ai_status="complete",
            warnings=["Demo/Fixture mode active. Showing validated offline snapshot learning brief."],
            evidence=IntelligenceEvidence(
                status="verified",
                source="fixture_snapshot",
                observed_at=observed,
                detail="Synthesized from validated fixture snapshot data.",
            ),
            checked_at=observed,
        )

    # Use pre-saved fixture brief
    return IssueLearningBrief(
        issue_number=brief_data["issue_number"],
        issue_title=brief_data["issue_title"],
        issue_url=brief_data["issue_url"],
        experience_level=level,  # type: ignore
        explanation=IssueExplanation(**brief_data["explanation"]),
        requirements=[IssueRequirement(**r) for r in brief_data.get("requirements", [])],
        relevant_modules=brief_data.get("relevant_modules", []),
        investigation_targets=[
            RelevantInvestigationFile(
                path=t["path"],
                module_name=t.get("module_name"),
                why_relevant=t["why_relevant"],
                what_to_inspect=t["what_to_inspect"],
                kind=t.get("kind", "candidate"),
                evidence=IntelligenceEvidence(**t["evidence"]),
            )
            for t in brief_data.get("investigation_targets", [])
        ],
        related_tests_and_docs=brief_data.get("related_tests_and_docs", []),
        concepts=[LearningConcept(**c) for c in brief_data.get("concepts", [])],
        learning_objectives=[LearningObjective(**o) for o in brief_data.get("learning_objectives", [])],
        readiness_checklist=[ReadinessChecklistItem(**cl) for cl in brief_data.get("readiness_checklist", [])],
        unresolved_questions=brief_data.get("unresolved_questions", []),
        ai_status=brief_data.get("ai_status", "complete"),
        warnings=brief_data.get("warnings", ["Demo/Fixture mode active."]),
        evidence=IntelligenceEvidence(**brief_data["evidence"]),
        checked_at=brief_data.get("checked_at", observed),
    )


def load_fixture_guided_implementation(
    repo_url: str,
    issue_number: int,
    profile: Optional[ContributorProfile] = None,
) -> GuidedImplementationPlan:
    """Load an offline fixture guided implementation plan with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    plans = data.get("guided_implementation_plans", {})
    plan_data = plans.get(str(issue_number))
    observed = datetime.now(timezone.utc).isoformat()
    level = profile.experience_level if profile else "beginner"

    if plan_data:
        # Pre-saved fixture plan
        steps = []
        for s in plan_data.get("steps", []):
            patch_sug = None
            if s.get("patch_suggestion"):
                ps = s["patch_suggestion"]
                patch_sug = PatchSuggestion(
                    target_path=ps["target_path"],
                    target_symbol=ps.get("target_symbol"),
                    summary=ps["summary"],
                    code_snippet=ps["code_snippet"],
                    assumptions=ps.get("assumptions", []),
                    expected_effect=ps["expected_effect"],
                    potential_risks=ps.get("potential_risks", []),
                    verification_status="unverified_educational_draft",
                )
            steps.append(
                ImplementationStep(
                    id=s["id"],
                    order=s["order"],
                    title=s["title"],
                    objective=s["objective"],
                    why_it_matters=s["why_it_matters"],
                    files=s.get("files", []),
                    what_to_inspect=s["what_to_inspect"],
                    expected_outcome=s["expected_outcome"],
                    dependencies=s.get("dependencies", []),
                    completion_criteria=s["completion_criteria"],
                    hints=[ProgressiveHint(**h) for h in s.get("hints", [])],
                    checkpoint=StepCheckpoint(**s["checkpoint"]),
                    patch_suggestion=patch_sug,
                )
            )

        exploration_targets = [
            CodeExplorationTarget(
                path=t["path"],
                module_name=t.get("module_name"),
                why_relevant=t["why_relevant"],
                target_symbols=t.get("target_symbols", []),
                behavior_to_observe=t.get("behavior_to_observe", "Inspect behavior"),
                suggested_search_terms=t.get("suggested_search_terms", []),
                evidence=IntelligenceEvidence(**t["evidence"]),
            )
            for t in plan_data.get("exploration_targets", [])
        ]

        approaches = [
            ImplementationApproach(**a) for a in plan_data.get("approaches", [])
        ]

        return GuidedImplementationPlan(
            issue_number=plan_data["issue_number"],
            issue_title=plan_data["issue_title"],
            issue_url=plan_data["issue_url"],
            experience_level=level,  # type: ignore
            overview=plan_data["overview"],
            steps=steps,
            exploration_targets=exploration_targets,
            approaches=approaches,
            recommended_approach_id=plan_data.get("recommended_approach_id", approaches[0].approach_id if approaches else "default-approach"),
            ai_status=plan_data.get("ai_status", "complete"),
            warnings=plan_data.get("warnings", ["Demo/Fixture mode active. Showing validated offline snapshot data."]),
            evidence=IntelligenceEvidence(**plan_data["evidence"]),
            checked_at=plan_data.get("checked_at", observed),
        )

    # Dynamic fallback synthesis for issues not pre-saved in fixture
    matched_issue = next((i for i in data.get("issues", []) if i["number"] == issue_number), None)
    title = matched_issue["title"] if matched_issue else f"Issue #{issue_number}"
    url = matched_issue["url"] if matched_issue else f"{repo_url}/issues/{issue_number}"
    body = matched_issue.get("body", "") if matched_issue else ""
    tree = data.get("file_tree", [])
    docs = data.get("docs", {})
    repo_data = data.get("repo", {})

    intel = generate_repository_intelligence(
        owner=repo_data.get("owner", "org"),
        repo_name=repo_data.get("name", "repo"),
        languages=repo_data.get("languages", []),
        file_tree=tree,
        docs_metadata=docs,
        candidate_issues=[{"number": issue_number, "title": title, "body": body, "labels": matched_issue.get("labels", []) if matched_issue else []}],
        is_truncated=repo_data.get("tree_truncated", False),
    )

    from app.guided_implementation import create_deterministic_fallback_guided_plan

    plan = create_deterministic_fallback_guided_plan(
        issue_number=issue_number,
        issue_title=title,
        issue_url=url,
        issue_body=body,
        labels=matched_issue.get("labels", []) if matched_issue else [],
        profile=profile or ContributorProfile(skills=["python"], experience_level="beginner", available_hours=3.0),
        file_tree=tree,
        docs_metadata=docs,
        intelligence_report=intel,
        learning_brief=None,
        warning_reason="Demo/Fixture mode active. Showing validated offline snapshot guided implementation plan.",
    )
    plan.ai_status = "complete"
    return plan


def load_fixture_verification(
    repo_url: str,
    issue_number: int,
    profile: Optional[ContributorProfile] = None,
    diff_text: str = "",
    planned_steps: Optional[list[ImplementationStep]] = None,
) -> VerificationAnalysisReport:
    """Load an offline fixture verification analysis report with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    reports = data.get("verification_reports", {})
    report_data = reports.get(str(issue_number))

    # If pre-saved snapshot exists and no custom diff was provided, return snapshot
    if report_data and not diff_text.strip():
        report = VerificationAnalysisReport.model_validate(report_data)
        if report.suggested_execution_plan:
            from app.plan_signing import sign_execution_plan
            report.suggested_execution_plan = sign_execution_plan(
                repo_url=repo_url,
                issue_number=issue_number,
                plan=report.suggested_execution_plan,
                secret="patchloom_demo_fixture_secret",
            )
        return report

    # Otherwise, dynamically parse the diff and run deterministic fallback on fixture repo data
    from app.diff_analyzer import parse_git_diff
    from app.verification import create_deterministic_fallback_verification_report

    parsed_diff = parse_git_diff(diff_text)
    matched_issue = next((i for i in data.get("issues", []) if i["number"] == issue_number), None)
    title = matched_issue["title"] if matched_issue else f"Issue #{issue_number}"
    url = matched_issue.get("url") if matched_issue else f"{repo_url}/issues/{issue_number}"
    body = matched_issue.get("body", "") if matched_issue else ""
    tree = data.get("file_tree", [])
    docs = data.get("docs", {})
    repo_data = data.get("repo", {})

    intel = generate_repository_intelligence(
        owner=repo_data.get("owner", "org"),
        repo_name=repo_data.get("name", "repo"),
        languages=repo_data.get("languages", []),
        file_tree=tree,
        docs_metadata=docs,
        candidate_issues=[{"number": issue_number, "title": title, "body": body, "labels": matched_issue.get("labels", []) if matched_issue else []}],
        is_truncated=repo_data.get("tree_truncated", False),
    )

    rep = create_deterministic_fallback_verification_report(
        issue_number=issue_number,
        issue_title=title,
        repo_url=url,
        parsed_diff=parsed_diff,
        file_tree=tree,
        intelligence_report=intel,
        planned_steps=planned_steps,
        warning_reason="Demo/Fixture mode active. Showing validated offline snapshot verification report.",
    )
    rep.ai_status = "complete"
    return rep


def load_fixture_draft_pr(
    repo_url: str,
    issue_number: int,
    diff_text: str = "",
    execution_result: Optional[TestExecutionResult] = None,
    review_findings: Optional[list[ReviewFinding]] = None,
    regression_risks: Optional[list[RegressionRisk]] = None,
    readiness: Optional[ReadinessAssessment] = None,
) -> DraftPR:
    """Load an offline fixture draft PR description with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    drafts = data.get("draft_prs", {})
    draft_data = drafts.get(str(issue_number))

    if draft_data and not diff_text.strip():
        return DraftPR.model_validate(draft_data)

    from app.diff_analyzer import parse_git_diff

    parsed_diff = parse_git_diff(diff_text)
    matched_issue = next((i for i in data.get("issues", []) if i["number"] == issue_number), None)
    title = matched_issue["title"] if matched_issue else f"Issue #{issue_number}"

    tests_performed: dict[str, list[str]] = {
        "executed_and_passed": [],
        "executed_and_failed": [],
        "not_executed": [],
        "manually_verified": [],
    }

    if execution_result:
        cmd_str = f"{execution_result.plan.command} {' '.join(execution_result.plan.arguments)}"
        summary_entry = f"{cmd_str} -> {execution_result.status.value} (exit {execution_result.exit_code})"
        if execution_result.status.value == "passed":
            tests_performed["executed_and_passed"].append(summary_entry)
        elif execution_result.status.value in ["failed", "timed_out"]:
            tests_performed["executed_and_failed"].append(summary_entry)
        else:
            tests_performed["not_executed"].append(summary_entry)

    files_summary = ", ".join(f.path for f in parsed_diff.files[:3])
    if len(parsed_diff.files) > 3:
        files_summary += f" and {len(parsed_diff.files) - 3} more"

    return DraftPR(
        title=f"fix: address issue #{issue_number} ({title[:50]})",
        summary_of_changes=f"Addresses #{issue_number} by updating {len(parsed_diff.files)} file(s) (+{parsed_diff.lines_added}/-{parsed_diff.lines_removed}).",
        problem_addressed=f"Resolves #{issue_number}: {title}",
        implementation_overview=f"Touched: {files_summary or 'No files modified.'}",
        tests_performed=tests_performed,
        known_limitations=[],
        remaining_concerns=[],
        manual_verification_checklist=[
            "Verify test suite passes locally",
            "Ensure diff contains no accidental debug prints or formatting debt",
            "Review updated documentation and comments",
        ],
    )

