"""Unit tests for M5 First-PR Planner, path grounding, unknown detail labeling, and safe fallback."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient

from app.github_client import IssueClosedError, IssueNotFoundError
from app.main import app
from app.planner import generate_first_pr_plan
from app.prompts import PlanModelOutput
from app.providers.base import QuotaExceededError, InvalidModelOutputError
from app.schemas import ContributorProfile, RepoMetadata


@pytest.fixture
def sample_profile():
    return ContributorProfile(
        skills=["python"],
        experience_level="beginner",
        available_hours=3.0,
    )


@pytest.fixture
def mock_gh_planner():
    gh = MagicMock()
    gh.fetch_repo_metadata = AsyncMock(
        return_value=RepoMetadata(
            owner="pallets",
            name="flask",
            default_branch="main",
            open_issues_count=50,
        )
    )
    gh.fetch_single_issue = AsyncMock(
        return_value={
            "number": 42,
            "title": "Fix cookie expiration header bug",
            "body": "Cookie max-age header is omitted when expires is set.",
            "state": "open",
            "html_url": "https://github.com/pallets/flask/issues/42",
        }
    )
    gh.fetch_documentation = AsyncMock(
        return_value={
            "has_readme": True,
            "has_contributing": True,
            "has_setup_guide": True,
            "has_test_guide": True,
            "readme_excerpt": "Run pip install -e . and pytest.",
            "contributing_excerpt": "Submit PRs against main.",
        }
    )
    gh.fetch_issue_comments = AsyncMock(
        return_value=[
            {"user": {"login": "maintainer"}, "body": "PRs welcome!"}
        ]
    )
    gh.fetch_file_tree = AsyncMock(
        return_value=(
            ["src/flask/sessions.py", "src/flask/app.py", "tests/test_sessions.py"],
            False,
            False,
        )
    )
    return gh


@pytest.mark.asyncio
async def test_generate_plan_success_with_grounding(mock_gh_planner, sample_profile):
    """Verify plan generation produces 3-7 steps and grounds files strictly in tree."""
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock(
        return_value=(
            PlanModelOutput(
                summary="Fix cookie max-age omission in sessions module.",
                steps=[
                    {
                        "title": "Inspect sessions cookie code",
                        "detail": "Open sessions.py and check header writing.",
                        "kind": "inference",
                        "files": ["src/flask/sessions.py", "hallucinated/cookies.py"],  # fake file should drop
                    },
                    {
                        "title": "Write reproduction test",
                        "detail": "Add test case in test_sessions.py.",
                        "kind": "inference",
                        "files": ["tests/test_sessions.py"],
                    },
                    {
                        "title": "Verify fix locally",
                        "detail": "Run pytest tests/test_sessions.py.",
                        "kind": "inference",
                        "files": [],
                    },
                ],
                setup_guidance={"status": "verified", "notes": "Install with pip install -e ."},
                test_guidance={"status": "verified", "notes": "Run test suite with pytest"},
                checklist=["Check cookie logic", "Run pytest", "Draft PR"],
                pr_title="fix: set cookie max-age header",
                pr_description_draft="## Summary\nFixes cookie header.\n\nFixes #42\n",
                open_questions_for_maintainer=[],
            ),
            "models/gemma-4-31b-it",
        )
    )

    plan = await generate_first_pr_plan(
        repo_url="https://github.com/pallets/flask",
        issue_number=42,
        profile=sample_profile,
        github_client=mock_gh_planner,
        model_provider=mock_provider,
    )

    assert plan.ai_status == "complete"
    assert plan.issue_number == 42
    assert len(plan.steps) == 3
    # Verify grounding: real file kept, hallucinated file dropped
    assert "src/flask/sessions.py" in plan.steps[0].files
    assert "hallucinated/cookies.py" not in plan.steps[0].files
    assert any("hallucinated/cookies.py" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_generate_plan_labels_unknown_guidance(mock_gh_planner, sample_profile):
    """Verify unverified setup or testing instructions are explicitly labeled unknown."""
    mock_gh_planner.fetch_documentation = AsyncMock(
        return_value={
            "has_readme": False,
            "has_contributing": False,
            "has_setup_guide": False,
            "has_test_guide": False,
            "readme_excerpt": "",
            "contributing_excerpt": "",
        }
    )
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock(
        return_value=(
            PlanModelOutput(
                summary="Plan for undocumented repo.",
                steps=[
                    {"title": "Step 1", "detail": "Inspect issue", "kind": "inference", "files": []},
                    {"title": "Step 2", "detail": "Implement fix", "kind": "inference", "files": []},
                    {"title": "Step 3", "detail": "Verify fix", "kind": "inference", "files": []},
                ],
                setup_guidance={"status": "unknown", "notes": "No setup instructions found in documentation."},
                test_guidance={"status": "unknown", "notes": "No test instructions found in documentation."},
                checklist=["Inspect", "Fix", "PR"],
                pr_title="fix: resolve issue #42",
                pr_description_draft="Fixes #42",
                open_questions_for_maintainer=["How to run tests?"],
            ),
            "models/gemma-4-31b-it",
        )
    )

    plan = await generate_first_pr_plan(
        repo_url="https://github.com/pallets/flask",
        issue_number=42,
        profile=sample_profile,
        github_client=mock_gh_planner,
        model_provider=mock_provider,
    )

    assert plan.setup_guidance.status == "unknown"
    assert plan.test_guidance.status == "unknown"


@pytest.mark.asyncio
async def test_generate_plan_fallback_on_provider_quota_error(mock_gh_planner, sample_profile):
    """Verify provider quota exhaustion falls back safely to deterministic plan without retrying."""
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock(side_effect=QuotaExceededError("Rate limit exceeded"))

    plan = await generate_first_pr_plan(
        repo_url="https://github.com/pallets/flask",
        issue_number=42,
        profile=sample_profile,
        github_client=mock_gh_planner,
        model_provider=mock_provider,
    )

    assert plan.ai_status == "unavailable_or_invalid"
    assert mock_provider.generate_json.call_count == 1  # Never retry quota error
    assert len(plan.steps) >= 3
    assert any("QuotaExceededError" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_generate_plan_retries_once_on_invalid_output(mock_gh_planner, sample_profile):
    """Verify invalid model output triggers at most one retry before fallback."""
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock(side_effect=InvalidModelOutputError("Invalid schema"))

    plan = await generate_first_pr_plan(
        repo_url="https://github.com/pallets/flask",
        issue_number=42,
        profile=sample_profile,
        github_client=mock_gh_planner,
        model_provider=mock_provider,
    )

    assert plan.ai_status == "unavailable_or_invalid"
    assert mock_provider.generate_json.call_count == 2
    assert any("AI planning output invalid after retry" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_plan_api_endpoint_closed_issue():
    """Verify POST /api/plan rejects closed issues with 400 Bad Request."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Mock fetch_single_issue to raise IssueClosedError
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.github_client.GitHubClient.fetch_single_issue",
                AsyncMock(side_effect=IssueClosedError("Issue #42 is closed")),
            )
            resp = await client.post(
                "/api/plan",
                json={
                    "repo_url": "https://github.com/pallets/flask",
                    "issue_number": 42,
                    "profile": {
                        "skills": ["python"],
                        "experience_level": "beginner",
                        "available_hours": 3,
                    },
                },
            )
    assert resp.status_code == 400
    assert "is closed" in resp.json()["detail"]
