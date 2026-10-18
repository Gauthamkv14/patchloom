"""Tests for offline fixture mode and hermetic demo scenarios."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from app.analysis import analyze_repository
from app.planner import generate_first_pr_plan
from app.schemas import ContributorProfile


@pytest.fixture
def sample_profile() -> ContributorProfile:
    return ContributorProfile(
        skills=["python", "fastapi"],
        preferred_languages=["python"],
        experience_level="beginner",
        available_hours=3.0,
        learning_goal="Learn to contribute",
    )


@pytest.mark.asyncio
async def test_fixture_analysis_scenario_a_good_fit(sample_profile):
    """Verify Scenario A (psf/requests): good fit with verified evidence and grounded files."""
    mock_gh = MagicMock()
    mock_gh.fetch_repo_metadata = AsyncMock()
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock()

    resp = await analyze_repository(
        repo_url="https://github.com/psf/requests",
        profile=sample_profile,
        demo=True,
        github_client=mock_gh,
        model_provider=mock_provider,
    )

    # Invariant: zero external network or model provider calls
    mock_gh.fetch_repo_metadata.assert_not_called()
    mock_provider.generate_json.assert_not_called()

    assert resp.repo.owner == "psf"
    assert resp.repo.name == "requests"
    assert resp.ai_status == "complete"
    assert any("Demo/Fixture mode active" in w for w in resp.warnings)
    assert len(resp.issues) >= 1

    top_issue = resp.issues[0]
    assert top_issue.number == 6542
    assert top_issue.viability_band == "high"
    assert top_issue.fit_score is not None
    assert top_issue.fit_score >= 80
    assert len(top_issue.likely_files) > 0


@pytest.mark.asyncio
async def test_fixture_analysis_scenario_b_partial_evidence(sample_profile):
    """Verify Scenario B (expressjs/express): partial evidence with unknown factors."""
    resp = await analyze_repository(
        repo_url="https://github.com/expressjs/express",
        profile=sample_profile,
        demo=True,
    )

    assert resp.repo.owner == "expressjs"
    assert resp.repo.name == "express"
    assert any("Demo/Fixture mode active" in w for w in resp.warnings)

    issue = next(i for i in resp.issues if i.number == 5102)
    # Critical invariant: unknown linked PR check is preserved as unknown
    assert issue.signals["linked_pr_status"].status == "unknown"
    assert len(issue.negative_factors) > 0
    assert "Linked PR evidence lookup could not be verified" in issue.unknown_factors


@pytest.mark.asyncio
async def test_fixture_analysis_scenario_c_fallback_demo(sample_profile):
    """Verify Scenario C (encode/uvicorn): AI unavailable fallback with deterministic-only scores."""
    resp = await analyze_repository(
        repo_url="https://github.com/encode/uvicorn",
        profile=sample_profile,
        demo=True,
    )

    assert resp.repo.owner == "encode"
    assert resp.repo.name == "uvicorn"
    assert resp.ai_status == "unavailable_or_invalid"
    # Never fake AI fit scores when AI is unavailable
    assert all(i.fit_score is None for i in resp.issues)
    assert all(i.final_score == float(i.viability_score) for i in resp.issues)


@pytest.mark.asyncio
async def test_fixture_plan_scenario_a_good_fit(sample_profile):
    """Verify Scenario A plan generation from offline fixture snapshot."""
    mock_gh = MagicMock()
    mock_gh.fetch_single_issue = AsyncMock()
    mock_provider = MagicMock()
    mock_provider.generate_json = AsyncMock()

    plan = await generate_first_pr_plan(
        repo_url="https://github.com/psf/requests",
        issue_number=6542,
        profile=sample_profile,
        demo=True,
        github_client=mock_gh,
        model_provider=mock_provider,
    )

    # Invariant: zero external network or model provider calls
    mock_gh.fetch_single_issue.assert_not_called()
    mock_provider.generate_json.assert_not_called()

    assert plan.issue_number == 6542
    assert 3 <= len(plan.steps) <= 7
    assert plan.setup_guidance.status == "verified"
    assert plan.test_guidance.status == "verified"
    assert "Fixes #6542" in plan.pr_description_draft
    assert any("Demo/Fixture mode active" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_fixture_plan_scenario_c_deterministic_fallback(sample_profile):
    """Verify Scenario C fallback plan generation from offline fixture snapshot."""
    plan = await generate_first_pr_plan(
        repo_url="https://github.com/encode/uvicorn",
        issue_number=2185,
        profile=sample_profile,
        demo=True,
    )

    assert plan.issue_number == 2185
    assert plan.ai_status == "unavailable_or_invalid"
    assert len(plan.steps) >= 3
    assert "Fixes #2185" in plan.pr_description_draft
    assert any("offline or unconfigured" in w for w in plan.warnings)
