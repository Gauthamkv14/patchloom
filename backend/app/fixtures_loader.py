"""Fixture loader for offline demo mode and hermetic testing."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas import (
    AnalyzeResponse,
    CandidateIssue,
    ContributorProfile,
    IntelligenceEvidence,
    IssueExplanation,
    IssueLearningBrief,
    IssueRequirement,
    LearningConcept,
    LearningObjective,
    PlanNote,
    PlanResponse,
    PlanStep,
    ReadinessChecklistItem,
    RelevantInvestigationFile,
    RepoMetadata,
    SignalEvidence,
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

