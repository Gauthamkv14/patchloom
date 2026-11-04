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
    validate_diff_content,
)
from app.plan_signing import (
    compute_plan_signature,
    sign_execution_plan,
    verify_execution_plan,
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


# ==============================================================================
# 5. Security Remediation Regression Tests (Audit P0 & P1)
# ==============================================================================

def test_allowlist_bypass_regressions():
    """Verify that all allowlist bypasses identified in the security audit are strictly rejected."""
    # 1. npm subcommands
    assert is_command_allowlisted("npm", ["run", "arbitrary_script"]) is False
    assert is_command_allowlisted("npm", ["install"]) is False
    assert is_command_allowlisted("npm", ["test", "--", "tests/foo.test.js"]) is True

    # 2. python subcommands and arbitrary files
    assert is_command_allowlisted("python", ["arbitrary.py"]) is False
    assert is_command_allowlisted("python", ["-m", "http.server"]) is False
    assert is_command_allowlisted("python", ["-m", "pytest", "tests/test_api.py"]) is True
    assert is_command_allowlisted("python", ["-m", "unittest", "tests/test_api.py"]) is True

    # 3. cargo subcommands
    assert is_command_allowlisted("cargo", ["run"]) is False
    assert is_command_allowlisted("cargo", ["test", "--test", "tests/foo.rs"]) is True

    # 4. go subcommands
    assert is_command_allowlisted("go", ["run", "main.go"]) is False
    assert is_command_allowlisted("go", ["test", "./..."]) is True

    # 5. npx subcommands
    assert is_command_allowlisted("npx", ["evil-package"]) is False
    assert is_command_allowlisted("npx", ["vitest", "run", "tests/foo.test.ts"]) is True
    assert is_command_allowlisted("npx", ["jest", "tests/foo.test.js"]) is True

    # 6. dangerous pytest configuration overrides
    assert is_command_allowlisted("pytest", ["-o", "log_cli=true"]) is False
    assert is_command_allowlisted("pytest", ["--override-ini=addopts=--help"]) is False

    # 7. path traversal
    assert is_command_allowlisted("pytest", ["../etc/passwd"]) is False
    assert is_command_allowlisted("pytest", ["tests/../../secret.py"]) is False
    assert is_command_allowlisted("pytest", ["/bin/sh"]) is False
    assert is_command_allowlisted("pytest", ["C:\\Windows\\system32"]) is False

    # 8. dangerous flags and interpreter code injection
    assert is_command_allowlisted("pytest", ["-c", "import os; os.system('sh')"]) is False
    assert is_command_allowlisted("pytest", ["--import", "malicious"]) is False
    assert is_command_allowlisted("pytest", ["--eval", "malicious"]) is False


def test_validate_diff_content_security():
    """Verify that git diff validation strictly catches path traversal, symlinks, and absolute paths."""
    # Safe diff
    safe_diff = (
        "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
        "--- a/tests/test_foo.py\n"
        "+++ b/tests/test_foo.py\n"
        "@@ -1 +1 @@\n"
        "+assert True\n"
    )
    ok, msg = validate_diff_content(safe_diff)
    assert ok is True

    # Path traversal in diff header
    traversal_diff = (
        "diff --git a/../secret.py b/../secret.py\n"
        "--- a/../secret.py\n"
        "+++ b/../secret.py\n"
    )
    ok, msg = validate_diff_content(traversal_diff)
    assert ok is False
    assert "path traversal" in msg.lower()

    # Symlink creation
    symlink_diff = (
        "diff --git a/link b/link\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/link\n"
        "@@ -0,0 +1 @@\n"
        "+/etc/passwd\n"
    )
    ok, msg = validate_diff_content(symlink_diff)
    assert ok is False
    assert "symbolic link" in msg.lower()

    # Absolute path in header
    abs_diff = (
        "diff --git a//etc/passwd b//etc/passwd\n"
        "--- /etc/passwd\n"
        "+++ /etc/passwd\n"
    )
    ok, msg = validate_diff_content(abs_diff)
    assert ok is False


def test_plan_hmac_signing_and_verification():
    """Verify HMAC-SHA256 signature binding, tampering rejection, expiry, missing secret, and multi-worker consistency."""
    secret = "test_verification_secret_12345"
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
    )
    repo_url = "https://github.com/psf/requests"
    issue_number = 6542

    # 1. Missing Secret: When no signing secret is configured, live execution is strictly disabled
    with patch("app.plan_signing.settings.EXECUTION_SIGNING_SECRET", None):
        is_valid, reason = verify_execution_plan(repo_url, issue_number, plan, secret=None)
        assert is_valid is False
        assert "EXECUTION_SIGNING_SECRET is not configured" in reason

    # 2. Sign plan with configured secret
    signed_plan = sign_execution_plan(repo_url, issue_number, plan, ttl_seconds=600, secret=secret)
    assert signed_plan.signature is not None
    assert signed_plan.expires_at is not None

    # 3. Multi-worker / Restart consistency: Independent sign calls produce identical signatures
    worker2_signature = compute_plan_signature(repo_url, issue_number, signed_plan, secret=secret)
    assert signed_plan.signature == worker2_signature

    # 4. Verify unmodified plan
    is_valid, reason = verify_execution_plan(repo_url, issue_number, signed_plan, secret=secret)
    assert is_valid is True

    # 5. Tampered command
    tampered_cmd_plan = signed_plan.model_copy(update={"command": "npm test"})
    is_valid, reason = verify_execution_plan(repo_url, issue_number, tampered_cmd_plan, secret=secret)
    assert is_valid is False
    assert "invalid" in reason.lower()

    # 6. Tampered arguments
    tampered_args_plan = signed_plan.model_copy(update={"arguments": ["tests/other.py"]})
    is_valid, reason = verify_execution_plan(repo_url, issue_number, tampered_args_plan, secret=secret)
    assert is_valid is False

    # 7. Transposed issue number
    is_valid, reason = verify_execution_plan(repo_url, 9999, signed_plan, secret=secret)
    assert is_valid is False

    # 8. Transposed repo URL
    is_valid, reason = verify_execution_plan("https://github.com/other/repo", issue_number, signed_plan, secret=secret)
    assert is_valid is False

    # 9. Expired plan
    expired_plan = signed_plan.model_copy(update={"expires_at": "2020-01-01T00:00:00+00:00"})
    is_valid, reason = verify_execution_plan(repo_url, issue_number, expired_plan, secret=secret)
    assert is_valid is False
    assert "expired" in reason.lower()

    # 10. Missing signature
    unsigned_plan = signed_plan.model_copy(update={"signature": None})
    is_valid, reason = verify_execution_plan(repo_url, issue_number, unsigned_plan, secret=secret)
    assert is_valid is False


@pytest.mark.asyncio
async def test_api_verification_execute_rejects_unauthorized():
    """Verify that unauthorized test execution is strictly rejected at the API boundary with HTTP 400."""
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
                "authorized": False,  # Explicit unauthorized
                "demo": False,
            },
        )
        assert response.status_code == 400
        assert "Explicit contributor authorization was not confirmed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_verification_execute_rejects_forged_or_unsigned_plan_in_live_mode():
    """Verify that unverified or tampered plans in live mode are rejected with HTTP 400."""
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
                    "signature": "forged_signature_12345",
                    "expires_at": "2026-12-31T23:59:59+00:00",
                },
                "authorized": True,
                "demo": False,
            },
        )
        assert response.status_code == 400
        assert "Execution plan rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_container_lifecycle_and_timeout_cleanup(tmp_path):
    """Verify unique container naming, timeout docker kill, and forced docker rm in cleanup."""
    import asyncio

    (tmp_path / ".provisioned").touch()
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=5,
        is_allowlisted=True,
    )
    signed_plan = sign_execution_plan("https://github.com/psf/requests", 6542, plan, secret="test_secret")

    mock_run_proc = AsyncMock()
    mock_run_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_run_proc.kill = MagicMock()
    mock_run_proc.wait = AsyncMock()

    mock_kill_proc = AsyncMock()
    mock_kill_proc.communicate = AsyncMock(return_value=(b"", b""))

    mock_rm_proc = AsyncMock()
    mock_rm_proc.communicate = AsyncMock(return_value=(b"", b""))

    calls = []

    def mock_subprocess(*args, **kwargs):
        calls.append(list(args))
        if len(args) > 1 and args[1] == "kill":
            return mock_kill_proc
        elif len(args) > 1 and args[1] == "rm":
            return mock_rm_proc
        return mock_run_proc

    with patch("app.test_runner.check_docker_availability", return_value=(True, "Docker daemon running")):
        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            res = await execute_isolated_test_plan(
                plan=signed_plan,
                authorized=True,
                demo=False,
                workspace_dir=str(tmp_path),
            )
            assert res.status == "timed_out"
            assert "Container patchloom_test_" in res.stderr_bounded

            # Verify docker kill and docker rm were called
            kill_calls = [c for c in calls if len(c) > 1 and c[1] == "kill"]
            rm_calls = [c for c in calls if len(c) > 1 and c[1] == "rm"]
            assert len(kill_calls) >= 1
            assert len(rm_calls) >= 1
            assert kill_calls[0][0] == "docker"
            assert rm_calls[0][0] == "docker"
            assert kill_calls[0][2].startswith("patchloom_test_")
            assert rm_calls[0][3].startswith("patchloom_test_")


@pytest.mark.asyncio
async def test_docker_command_hardening_flags(tmp_path):
    """Verify that all required Docker hardening flags are present in container execution."""
    (tmp_path / ".provisioned").touch()
    plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=10,
        is_allowlisted=True,
    )

    captured_cmds = []
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"=== 1 passed in 0.1s ===", b""))
    mock_proc.returncode = 0

    def mock_subprocess(*args, **kwargs):
        captured_cmds.append(list(args))
        return mock_proc

    with patch("app.test_runner.check_docker_availability", return_value=(True, "Docker daemon running")):
        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            res = await execute_isolated_test_plan(
                plan=plan,
                authorized=True,
                demo=False,
                workspace_dir=str(tmp_path),
            )
            assert res.status == "passed"
            run_cmd = captured_cmds[0]
            # Verify all hardening flags are present
            assert "--read-only" in run_cmd
            assert "--security-opt" in run_cmd and "no-new-privileges:true" in run_cmd
            assert "--network" in run_cmd and "none" in run_cmd
            assert "--cap-drop" in run_cmd and "ALL" in run_cmd
            assert "-u" in run_cmd and "10001:10001" in run_cmd
            assert "--cpus=1.0" in run_cmd
            assert "--memory=512m" in run_cmd
            assert "--memory-swap=512m" in run_cmd
            assert "--pids-limit=64" in run_cmd
            assert any("/tmp:rw,noexec,nosuid,size=64m" in arg for arg in run_cmd)


@pytest.mark.asyncio
async def test_runner_tooling_absence_fails_closed(tmp_path):
    """Verify that runners fail closed as execution_unavailable when tooling or workspace is absent."""
    # 1. Pytest tooling is absent from python:3.13-slim runtime image
    pytest_plan = TestExecutionPlan(
        test_runner="pytest",
        command="pytest",
        arguments=["tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
    )
    with patch("app.test_runner.check_docker_availability", return_value=(True, "Docker daemon running")):
        res = await execute_isolated_test_plan(
            plan=pytest_plan,
            authorized=True,
            demo=False,
            workspace_dir=str(tmp_path),  # No .provisioned marker
        )
        assert res.status == "execution_unavailable"
        assert any("absent from runtime image" in f for f in res.failure_details)

    # 2. Vitest tooling is absent from node:22-alpine runtime image
    vitest_plan = TestExecutionPlan(
        test_runner="vitest",
        command="npx vitest run",
        arguments=["tests/foo.test.ts"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
    )
    with patch("app.test_runner.check_docker_availability", return_value=(True, "Docker daemon running")):
        res = await execute_isolated_test_plan(
            plan=vitest_plan,
            authorized=True,
            demo=False,
            workspace_dir=str(tmp_path),
        )
        assert res.status == "execution_unavailable"
        assert any("absent from runtime image" in f for f in res.failure_details)

    # 3. Unittest has tooling in stdlib, but workspace is not supplied
    unittest_plan = TestExecutionPlan(
        test_runner="python_unittest",
        command="python",
        arguments=["-m", "unittest", "tests/test_requests.py"],
        working_dir=".",
        timeout_seconds=30,
        is_allowlisted=True,
    )
    with patch("app.test_runner.check_docker_availability", return_value=(True, "Docker daemon running")):
        res = await execute_isolated_test_plan(
            plan=unittest_plan,
            authorized=True,
            demo=False,
            workspace_dir=None,  # No workspace supplied
        )
        assert res.status == "execution_unavailable"
        assert any("workspace is unavailable" in f.lower() for f in res.failure_details)


def test_live_docker_honesty():
    """Verify live Docker daemon check; skip honestly with diagnostic if daemon is offline."""
    docker_available, diag = check_docker_availability()
    if not docker_available:
        pytest.skip(f"Docker daemon is not reachable on host ({diag}); live test skipped honestly.")
    assert docker_available is True
