"""Unit tests for PatchLoom 2.0 M4: Verification & Review.

Tests cover:
1. Deterministic unified git diff parsing, bounding (100KB), and roadmap alignment.
2. Grounded test discovery, framework identification, and command formatting.
3. Isolated test runner boundary: Docker isolation invariants, command allowlist,
   shell injection rejection, unauthorized execution prevention, and Docker unavailability handling.
4. Verification analysis engine: AI reasoning, 1 retry on invalid output, strict path grounding,
   and deterministic fallback.
5. Draft PR generation with categorized test results and maintainer checklists.
6. API endpoint integration for /api/verification/analyze, /execute, and /prepare-pr.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from app.diff_analyzer import (
    clean_diff_path,
    evaluate_diff_roadmap_alignment,
    parse_git_diff,
)
from app.github_client import IssueClosedError, IssueNotFoundError
from app.main import app
from app.prompts import (
    ModelDraftPR,
    ModelReadinessAssessment,
    ModelRegressionRisk,
    ModelReviewFinding,
    VerificationModelOutput,
    build_prepare_pr_prompt,
    build_verification_review_prompt,
)
from app.providers.base import InvalidModelOutputError, QuotaExceededError
from app.schemas import (
    ContributorProfile,
    DiffChangeFile,
    DiscoveredTest,
    DraftPR,
    ImplementationStep,
    IntelligenceEvidence,
    ParsedDiff,
    ReadinessAssessment,
    RepoMetadata,
    RepositoryIntelligenceReport,
    StepCheckpoint,
    TestExecutionPlan,
    TestExecutionResult,
    VerificationAnalysisReport,
)
from app.test_discovery import discover_relevant_tests, format_test_command, is_test_path
from app.test_runner import (
    check_docker_availability,
    execute_isolated_test_plan,
    is_command_allowlisted,
    parse_test_counts,
)
from app.verification import (
    create_deterministic_fallback_verification_report,
    generate_draft_pr,
    generate_verification_analysis,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_diff_text():
    return """diff --git a/docs/user/advanced.rst b/docs/user/advanced.rst
index 45b8813..d84f932 100644
--- a/docs/user/advanced.rst
+++ b/docs/user/advanced.rst
@@ -120,6 +120,12 @@ Timeouts
 In streaming mode, timeouts behave differently.
 
+For example, when consuming a slow streaming endpoint::
+
+    r = requests.get('https://httpbin.org/stream/20', stream=True, timeout=(3.05, 27))
+    for line in r.iter_lines():
+        print(line)
+
diff --git a/tests/test_requests.py b/tests/test_requests.py
index 72ef910..93c4102 100644
--- a/tests/test_requests.py
+++ b/tests/test_requests.py
@@ -840,6 +840,11 @@ class TestRequests:
         r = requests.get(httpbin('stream', '5'), stream=True, timeout=10)
         assert r.status_code == 200
 
+    def test_stream_timeout_tuple(self, httpbin):
+        r = requests.get(httpbin('stream', '5'), stream=True, timeout=(3.05, 10))
+        lines = list(r.iter_lines())
+        assert len(lines) > 0
+"""


@pytest.fixture
def sample_file_tree():
    return [
        "docs/user/advanced.rst",
        "docs/user/quickstart.rst",
        "requests/__init__.py",
        "requests/api.py",
        "requests/models.py",
        "requests/sessions.py",
        "tests/__init__.py",
        "tests/test_api.py",
        "tests/test_requests.py",
        "tests/test_structures.py",
        "pyproject.toml",
    ]


@pytest.fixture
def sample_steps():
    return [
        ImplementationStep(
            id="step-1",
            order=1,
            title="Update streaming documentation",
            objective="Add streaming tuple timeout examples",
            why_it_matters="Guidance for users",
            files=["docs/user/advanced.rst"],
            what_to_inspect="Inspect docs/user/advanced.rst",
            expected_outcome="Docs updated",
            completion_criteria="Sphinx compiles",
            hints=[],
            checkpoint=StepCheckpoint(
                question="Done?",
                options=["Yes"],
                correct_index=0,
                explanation="Ok",
                verification_guidance="Check that Sphinx documentation builds cleanly",
            ),
        ),
        ImplementationStep(
            id="step-2",
            order=2,
            title="Add test case for tuple timeout",
            objective="Verify tuple timeout with iter_lines",
            why_it_matters="Prevent regression",
            files=["tests/test_requests.py"],
            what_to_inspect="Inspect tests/test_requests.py",
            expected_outcome="Test passes",
            completion_criteria="pytest passes",
            hints=[],
            checkpoint=StepCheckpoint(
                question="Done?",
                options=["Yes"],
                correct_index=0,
                explanation="Ok",
                verification_guidance="Run pytest tests/test_requests.py",
            ),
        ),
    ]


# ==============================================================================
# 1. Diff Analyzer Tests
# ==============================================================================

def test_clean_diff_path():
    assert clean_diff_path("a/docs/user/advanced.rst") == "docs/user/advanced.rst"
    assert clean_diff_path("b/tests/test_requests.py") == "tests/test_requests.py"
    assert clean_diff_path("/dev/null") == "/dev/null"
    assert clean_diff_path("regular/path.py") == "regular/path.py"


def test_parse_git_diff_success(sample_diff_text):
    parsed = parse_git_diff(sample_diff_text)
    assert parsed.total_files == 2
    assert parsed.lines_added > 0
    assert parsed.lines_removed == 0
    assert len(parsed.files) == 2

    doc_file = next(f for f in parsed.files if f.path == "docs/user/advanced.rst")
    assert doc_file.change_type == "modified"
    assert doc_file.lines_added > 0
    assert doc_file.lines_removed == 0

    test_file = next(f for f in parsed.files if f.path == "tests/test_requests.py")
    assert test_file.change_type == "modified"
    assert test_file.lines_added > 0
    assert "test_stream_timeout_tuple" in test_file.detected_symbols


def test_parse_git_diff_empty():
    parsed = parse_git_diff("")
    assert parsed.total_files == 0
    assert any("diff" in w.lower() for w in parsed.warnings)


def test_parse_git_diff_truncation():
    # Diff exceeding 100,000 characters
    huge_diff = "diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n" + ("+ line of code\n" * 7000)
    assert len(huge_diff) > 100000
    parsed = parse_git_diff(huge_diff)
    assert parsed.is_truncated is True
    assert any("truncated" in w.lower() for w in parsed.warnings)


def test_evaluate_diff_roadmap_alignment(sample_steps):
    files = [
        DiffChangeFile(path="docs/user/advanced.rst", change_type="modified", lines_added=5, lines_removed=0, detected_symbols=[]),
        DiffChangeFile(path="tests/test_requests.py", change_type="modified", lines_added=5, lines_removed=0, detected_symbols=[]),
        DiffChangeFile(path="unrelated.txt", change_type="added", lines_added=1, lines_removed=0, detected_symbols=[]),
    ]
    parsed_diff = ParsedDiff(
        files=files,
        total_files=len(files),
        lines_added=11,
        lines_removed=0,
    )
    summary, unrelated = evaluate_diff_roadmap_alignment(parsed_diff, sample_steps)
    assert "unrelated.txt" in unrelated
    assert "docs/user/advanced.rst" not in unrelated
    assert "roadmap" in summary.lower() or "targets" in summary.lower()


# ==============================================================================
# 2. Test Discovery Tests
# ==============================================================================

def test_is_test_path():
    assert is_test_path("tests/test_requests.py") is True
    assert is_test_path("src/module_test.go") is True
    assert is_test_path("test/unit/runner.js") is True
    assert is_test_path("requests/api.py") is False
    assert is_test_path("docs/user/advanced.rst") is False


def test_discover_relevant_tests_from_diff(sample_file_tree):
    diff = ParsedDiff(
        files=[
            DiffChangeFile(path="requests/api.py", change_type="modified", lines_added=1, lines_removed=0, detected_symbols=[]),
        ],
        total_files=1,
        lines_added=1,
        lines_removed=0,
    )
    tests, plan = discover_relevant_tests(
        parsed_diff=diff,
        file_tree=sample_file_tree,
    )
    assert len(tests) > 0
    assert any("test" in t.test_file for t in tests)
    assert plan is not None
    assert plan.command == "pytest"


def test_format_test_command():
    cmd = format_test_command("pytest", "pytest", "tests/test_api.py")
    assert cmd == "pytest tests/test_api.py"


# ==============================================================================
# 3. Isolated Test Runner Boundary Tests
# ==============================================================================

def test_is_command_allowlisted():
    assert is_command_allowlisted("pytest", ["tests/test_requests.py"]) is True
    assert is_command_allowlisted("pytest", ["-k", "test_stream"]) is True
    assert is_command_allowlisted("npm", ["test"]) is True
    assert is_command_allowlisted("cargo", ["test", "api_tests"]) is True

    # Rejection of dangerous commands and shell operators
    assert is_command_allowlisted("rm", ["-rf", "/"]) is False
    assert is_command_allowlisted("curl", ["https://evil.com"]) is False
    assert is_command_allowlisted("pytest", ["tests/test_requests.py; rm -rf /"]) is False
    assert is_command_allowlisted("pytest", ["tests/test_requests.py && echo bad"]) is False
    assert is_command_allowlisted("pytest", ["$(whoami)"]) is False
    assert is_command_allowlisted("pytest", ["tests/`rm -rf /`"]) is False


def test_parse_test_counts():
    pytest_stdout = "==== 42 passed, 2 failed, 1 skipped in 2.34s ===="
    total, passed, failed, skipped = parse_test_counts(pytest_stdout, "")
    assert passed == 42
    assert failed == 2
    assert skipped == 1
    assert total == 45


@pytest.mark.asyncio
async def test_execute_isolated_unauthorized():
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
        disclaimer="User authorization required",
    )
    res = await execute_isolated_test_plan(plan=plan, authorized=False, demo=False)
    assert res.status == "invalid_or_unsupported"
    assert any("authorized" in d.lower() for d in res.failure_details)


@pytest.mark.asyncio
async def test_execute_isolated_docker_unavailable():
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
        disclaimer="User authorization required",
    )
    with patch("app.test_runner.check_docker_availability", return_value=(False, "Docker daemon not running")):
        res = await execute_isolated_test_plan(plan=plan, authorized=True, demo=False)
        assert res.status == "execution_unavailable"
        assert "Docker daemon not running" in res.stderr_bounded


@pytest.mark.asyncio
async def test_execute_isolated_demo_mode():
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
        disclaimer="User authorization required",
    )
    res = await execute_isolated_test_plan(plan=plan, authorized=True, demo=True)
    assert res.status == "passed"
    assert res.simulated is True
    assert res.tests_passed > 0
    assert res.exit_code == 0


# ==============================================================================
# 4. Verification Analysis & Grounding Tests
# ==============================================================================

def test_deterministic_fallback_verification(sample_diff_text, sample_file_tree, sample_steps):
    parsed = parse_git_diff(sample_diff_text)
    rep = create_deterministic_fallback_verification_report(
        issue_number=6542,
        issue_title="Improve timeout documentation",
        repo_url="https://github.com/psf/requests",
        parsed_diff=parsed,
        file_tree=sample_file_tree,
        planned_steps=sample_steps,
    )
    assert rep.issue_number == 6542
    assert rep.parsed_diff.total_files == 2
    assert len(rep.discovered_tests) > 0
    assert rep.suggested_execution_plan is not None
    assert rep.readiness.status in ["ready_for_review", "needs_attention"]
    assert rep.evidence.status == "inference"


@pytest.mark.asyncio
async def test_generate_verification_with_ai_mock(sample_diff_text, sample_file_tree):
    mock_gh = MagicMock()
    mock_gh.fetch_single_issue = AsyncMock(return_value={"number": 6542, "title": "Timeout docs", "body": "Need streaming timeout docs", "labels": []})
    mock_gh.fetch_documentation = AsyncMock(return_value={})
    mock_gh.fetch_repo_metadata = AsyncMock(return_value=RepoMetadata(owner="psf", name="requests", default_branch="main", open_issues_count=1, has_readme=True, has_contributing=True, has_ci=True, languages=["Python"]))
    mock_gh.fetch_file_tree = AsyncMock(return_value=(sample_file_tree, False, False))
    mock_gh.fetch_ci_workflow_evidence = AsyncMock(return_value=None)

    mock_provider = MagicMock()
    mock_ai_output = VerificationModelOutput(
        roadmap_alignment_summary="All changes align with documentation steps.",
        review_findings=[
            ModelReviewFinding(
                finding_id="f-1",
                category="other",
                severity="low",
                title="Good docs",
                explanation="Grounded doc change",
                evidence="docs/user/advanced.rst",
                file_path="docs/user/advanced.rst",
                line_range="120-128",
                why_it_matters="Clear docs",
                suggested_action="Review",
                confidence="high",
            ),
            # Hallucinated path that must be dropped
            ModelReviewFinding(
                finding_id="f-2",
                category="other",
                severity="critical",
                title="Ghost file",
                explanation="Nonexistent file",
                evidence="invented/ghost.py",
                file_path="invented/ghost.py",
                line_range="1-10",
                why_it_matters="Does not exist",
                suggested_action="Drop",
                confidence="low",
            ),
        ],
        regression_risks=[
            ModelRegressionRisk(
                risk_id="r-1",
                affected_module_or_file="docs/user/advanced.rst",
                risk_type="other",
                evidence="Modified streaming documentation",
                potential_impact="Doc build",
                suggested_verification="Sphinx check",
                confidence="high",
            )
        ],
        readiness=ModelReadinessAssessment(
            status="ready_for_review",
            summary="All good",
            outstanding_items=[],
        ),
    )
    mock_provider.generate_json = AsyncMock(return_value=(mock_ai_output, "{}"))

    rep = await generate_verification_analysis(
        repo_url="https://github.com/psf/requests",
        issue_number=6542,
        diff_text=sample_diff_text,
        github_client=mock_gh,
        model_provider=mock_provider,
    )
    assert rep.issue_number == 6542
    # Verify hallucinated path was dropped by grounding check
    assert len(rep.review_findings) == 1
    assert rep.review_findings[0].file_path == "docs/user/advanced.rst"
    assert rep.readiness.status == "ready_for_review"


@pytest.mark.asyncio
async def test_generate_verification_retry_on_invalid_output(sample_diff_text, sample_file_tree):
    mock_gh = MagicMock()
    mock_gh.fetch_single_issue = AsyncMock(return_value={"number": 6542, "title": "Timeout docs", "body": "Streaming timeout docs", "labels": []})
    mock_gh.fetch_documentation = AsyncMock(return_value={})
    mock_gh.fetch_repo_metadata = AsyncMock(return_value=RepoMetadata(owner="psf", name="requests", default_branch="main", open_issues_count=1, has_readme=True, has_contributing=True, has_ci=True, languages=["Python"]))
    mock_gh.fetch_file_tree = AsyncMock(return_value=(sample_file_tree, False, False))
    mock_gh.fetch_ci_workflow_evidence = AsyncMock(return_value=None)

    mock_provider = MagicMock()
    # First call fails, second succeeds
    mock_ai_output = VerificationModelOutput(
        roadmap_alignment_summary="Aligned after retry",
        review_findings=[],
        regression_risks=[],
        readiness=ModelReadinessAssessment(status="ready_for_review", summary="Retry succeeded", outstanding_items=[]),
    )
    mock_provider.generate_json = AsyncMock(side_effect=[
        InvalidModelOutputError("Malformed schema response"),
        (mock_ai_output, "{}"),
    ])

    rep = await generate_verification_analysis(
        repo_url="https://github.com/psf/requests",
        issue_number=6542,
        diff_text=sample_diff_text,
        github_client=mock_gh,
        model_provider=mock_provider,
    )
    assert rep.issue_number == 6542
    assert mock_provider.generate_json.call_count == 2
    assert rep.readiness.summary == "Retry succeeded"


# ==============================================================================
# 5. Draft PR Generation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_generate_draft_pr_fallback(sample_diff_text):
    mock_gh = MagicMock()
    mock_gh.fetch_single_issue = AsyncMock(return_value={"number": 6542, "title": "Timeout docs", "body": "Streaming timeout", "labels": []})

    pr = await generate_draft_pr(
        repo_url="https://github.com/psf/requests",
        issue_number=6542,
        diff_text=sample_diff_text,
        github_client=mock_gh,
        model_provider=None,
    )
    assert pr.title != ""
    assert "6542" in pr.title or "6542" in pr.summary_of_changes
    assert len(pr.manual_verification_checklist) > 0


# ==============================================================================
# 6. API Endpoint Tests (Integration)
# ==============================================================================

@pytest.mark.asyncio
async def test_api_verification_analyze_demo():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/verification/analyze",
            json={
                "repo_url": "https://github.com/psf/requests",
                "issue_number": 6542,
                "diff_text": "",
                "demo": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["issue_number"] == 6542
        assert len(data["discovered_tests"]) > 0
        assert data["readiness"]["status"] in ["ready_for_review", "needs_attention"]


@pytest.mark.asyncio
async def test_api_verification_execute_demo():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/verification/execute",
            json={
                "repo_url": "https://github.com/psf/requests",
                "issue_number": 6542,
                "execution_plan": {
                    "test_runner": "pytest",
                    "command": "pytest",
                    "arguments": ["tests/test_requests.py"],
                    "working_dir": ".",
                    "timeout_seconds": 30,
                    "is_allowlisted": True,
                    "disclaimer": "Test plan",
                },
                "authorized": True,
                "demo": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "passed"
        assert data["simulated"] is True


@pytest.mark.asyncio
async def test_api_verification_prepare_pr_demo():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/verification/prepare-pr",
            json={
                "repo_url": "https://github.com/psf/requests",
                "issue_number": 6542,
                "diff_text": "",
                "demo": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] != ""
        assert len(data["manual_verification_checklist"]) > 0
