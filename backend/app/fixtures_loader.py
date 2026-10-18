"""Fixture loader for offline demo mode and hermetic testing."""

import json
import logging
from pathlib import Path
from typing import Optional

from app.schemas import (
    AnalyzeResponse,
    CandidateIssue,
    ContributorProfile,
    PlanNote,
    PlanResponse,
    PlanStep,
    RepoMetadata,
    SignalEvidence,
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
    profile: ContributorProfile,
    provider_name: Optional[str] = None,
) -> AnalyzeResponse:
    """Load an offline fixture analysis response with zero external network or model calls."""
    data = get_fixture_data_for_url(repo_url)
    repo_data = data["repo"]

    repo_meta = RepoMetadata(
        owner=repo_data["owner"],
        name=repo_data["name"],
        description=repo_data.get("description"),
        default_branch=repo_data.get("default_branch", "main"),
        languages=repo_data.get("languages", []),
        open_issues_count=repo_data.get("open_issues_count", 0),
        has_readme=repo_data.get("has_readme", True),
        has_contributing=repo_data.get("has_contributing", False),
        has_ci=repo_data.get("has_ci", True),
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
