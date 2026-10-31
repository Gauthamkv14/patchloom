"""Tests for Repository Intelligence Engine (PatchLoom 2.0 M1 - UNDERSTAND Pillar).

Verifies deterministic repository overview, entry point detection, test intelligence,
documentation intelligence, module partitioning, and issue-to-module mapping.
Zero live network calls; entirely hermetic with mocked data and fixtures.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.repo_intelligence import (
    analyze_documentation_profile,
    analyze_entry_points,
    analyze_languages_and_project_type,
    analyze_technologies_and_manifests,
    analyze_test_profile,
    generate_repository_intelligence,
    map_issue_to_repository_modules,
    partition_and_analyze_modules,
)
from app.schemas import (
    CandidateIssue,
    ContributorProfile,
    IntelligenceEvidence,
    SignalEvidence,
)


@pytest.fixture
def sample_python_repo():
    return {
        "owner": "testorg",
        "name": "fast-service",
        "languages": ["Python"],
        "file_tree": [
            "README.md",
            "CONTRIBUTING.md",
            "pyproject.toml",
            "setup.cfg",
            "Dockerfile",
            ".github/workflows/ci.yml",
            "src/fast_service/__init__.py",
            "src/fast_service/main.py",
            "src/fast_service/api/routes.py",
            "src/fast_service/core/config.py",
            "src/fast_service/models/user.py",
            "src/fast_service/utils/helpers.py",
            "tests/__init__.py",
            "tests/conftest.py",
            "tests/test_api.py",
            "tests/test_models.py",
            "docs/index.md",
            "docs/setup.md",
        ],
        "docs_metadata": {
            "has_readme": True,
            "has_contributing": True,
            "has_setup_guide": True,
            "has_test_guide": True,
            "readme_excerpt": "FastService is an asynchronous REST API built with FastAPI.\n\n## Setup\nRun `pip install -e .[dev]` to install dependencies.\n\n## Testing\nRun `pytest` to run all test suites.",
            "contributing_excerpt": "Please follow PEP 8 and write tests for every new route.",
        },
    }


@pytest.fixture
def sample_ts_react_repo():
    return {
        "owner": "acme",
        "name": "dashboard-ui",
        "languages": ["TypeScript", "CSS"],
        "file_tree": [
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "README.md",
            "src/main.tsx",
            "src/App.tsx",
            "src/components/Navbar.tsx",
            "src/components/Table.tsx",
            "src/services/api.ts",
            "src/utils/formatters.ts",
            "src/__tests__/App.test.tsx",
            "src/__tests__/Navbar.test.tsx",
        ],
        "docs_metadata": {
            "has_readme": True,
            "has_contributing": False,
            "readme_excerpt": "# Dashboard UI\nA modern analytics dashboard with React and Vite.\n\n### Scripts\n`npm run dev` to start.\n`npm test` to run tests.",
        },
    }


# =====================================================================
# 1. Overview & Language Analysis
# =====================================================================


def test_language_and_project_type_detection(sample_python_repo):
    lang_dist, ptype, rationale, structure = analyze_languages_and_project_type(
        sample_python_repo["file_tree"],
        sample_python_repo["languages"],
    )

    assert lang_dist.primary == "Python"
    assert lang_dist.secondary == []
    assert lang_dist.source == "github_languages_and_tree"
    assert ptype in ("api_service", "library_or_sdk", "other")
    assert len(rationale) > 0
    assert structure in ("monorepo", "single_package", "multi_module", "standard_flat")


def test_language_empty_and_unknown_handling():
    lang_dist, ptype, rationale, structure = analyze_languages_and_project_type(
        ["arbitrary_file.xyz", "data.dat"],
        [],
    )
    assert lang_dist.primary is None
    assert lang_dist.secondary == []
    assert ptype == "other"


def test_technologies_and_manifests_detection(sample_python_repo, sample_ts_react_repo):
    # Python repo detection
    techs, pkg_mgrs, manifests, configs = analyze_technologies_and_manifests(
        sample_python_repo["file_tree"],
        sample_python_repo["docs_metadata"].get("readme_excerpt", ""),
    )
    tech_names = {t.name for t in techs}
    assert "FastAPI" in tech_names
    assert "pyproject.toml" in manifests or "setup.cfg" in manifests
    assert any("Dockerfile" in c for c in configs)

    # TypeScript repo detection
    ts_techs, ts_pkgs, ts_manifests, ts_configs = analyze_technologies_and_manifests(
        sample_ts_react_repo["file_tree"],
        sample_ts_react_repo["docs_metadata"].get("readme_excerpt", ""),
    )
    ts_names = {t.name for t in ts_techs}
    assert "React" in ts_names or "TypeScript" in ts_names
    assert "package.json" in ts_manifests
    assert any("vite.config.ts" in c or "tsconfig.json" in c for c in ts_configs)


# =====================================================================
# 2. Entry Point Analysis
# =====================================================================


def test_entry_points_detected_vs_candidate(sample_python_repo):
    entry_points = analyze_entry_points(sample_python_repo["file_tree"])
    assert len(entry_points) > 0

    # Main entry point should be detected
    main_entry = next((e for e in entry_points if "main.py" in e.path), None)
    assert main_entry is not None
    assert main_entry.confidence == "detected"
    assert main_entry.kind in ("application", "backend")
    assert "main" in main_entry.reason.lower()

    # Manifest/config should be present
    manifest_entry = next((e for e in entry_points if "pyproject.toml" in e.path), None)
    assert manifest_entry is not None
    assert manifest_entry.kind == "manifest"
    assert manifest_entry.confidence == "detected"

    # All entry paths must be strictly present in the tree
    tree_set = set(sample_python_repo["file_tree"])
    for ep in entry_points:
        assert ep.path in tree_set


# =====================================================================
# 3. Test & CI Intelligence
# =====================================================================


def test_test_profile_detected(sample_python_repo):
    ci_evidence = SignalEvidence(
        status="verified",
        source="github_actions_tree",
        value={"status": "detected", "files": [".github/workflows/ci.yml"]},
    )
    test_profile = analyze_test_profile(
        sample_python_repo["file_tree"],
        sample_python_repo["docs_metadata"].get("readme_excerpt", ""),
        ci_evidence,
        is_truncated=False,
    )

    assert test_profile.status == "detected"
    assert "tests" in test_profile.test_directories
    assert test_profile.test_file_count > 0
    assert "pytest" in test_profile.frameworks
    assert test_profile.ci_configuration is not None
    assert test_profile.ci_configuration.status == "verified"
    assert any("pytest" in cmd for cmd in test_profile.likely_commands)


def test_test_profile_not_detected():
    tree = ["src/main.py", "README.md"]
    test_profile = analyze_test_profile(
        tree,
        "Simple project.",
        ci_evidence=None,
        is_truncated=False,
    )
    assert test_profile.status == "not_detected"
    assert test_profile.test_directories == []
    assert test_profile.test_file_count == 0
    assert test_profile.frameworks == []
    assert test_profile.evidence.status == "inference"


def test_test_profile_unknown_when_truncated():
    tree = ["src/main.py", "README.md"]
    test_profile = analyze_test_profile(
        tree,
        "",
        ci_evidence=None,
        is_truncated=True,
    )
    # When tree is truncated and no test dirs found, status must be unknown, never verified absent
    assert test_profile.status == "unknown"
    assert test_profile.evidence.status == "unknown"


# =====================================================================
# 4. Documentation Intelligence
# =====================================================================


def test_documentation_profile_extraction(sample_python_repo):
    doc_profile = analyze_documentation_profile(
        sample_python_repo["docs_metadata"],
        sample_python_repo["file_tree"],
    )

    assert doc_profile.has_readme is True
    assert doc_profile.has_contributing is True
    assert doc_profile.project_purpose is not None
    assert "FastAPI" in doc_profile.project_purpose or "REST API" in doc_profile.project_purpose
    assert doc_profile.setup_instructions is not None
    assert "pip install" in doc_profile.setup_instructions
    assert doc_profile.test_instructions is not None
    assert "pytest" in doc_profile.test_instructions
    assert len(doc_profile.docs) >= 2


def test_documentation_profile_missing_sections():
    doc_profile = analyze_documentation_profile(
        {},
        ["main.py"],
    )
    assert doc_profile.has_readme is False
    assert doc_profile.has_contributing is False
    assert doc_profile.project_purpose is None
    assert doc_profile.setup_instructions is None
    assert doc_profile.evidence.status == "unknown"


# =====================================================================
# 5. Module Intelligence & Partitioning
# =====================================================================


def test_partition_and_analyze_modules(sample_python_repo):
    techs, _, _, _ = analyze_technologies_and_manifests(sample_python_repo["file_tree"])
    modules = partition_and_analyze_modules(sample_python_repo["file_tree"], techs)
    assert len(modules) >= 2

    mod_types = {m.component_type for m in modules}
    assert "tests" in mod_types or "core_logic" in mod_types

    # Check tests module
    test_mod = next((m for m in modules if m.component_type == "tests"), None)
    if test_mod:
        assert any("tests" in f for f in test_mod.files)
        assert test_mod.confidence == "high"


# =====================================================================
# 6. Issue-to-Module Mapping
# =====================================================================


def test_issue_to_module_mapping_grounded(sample_python_repo):
    techs, _, _, _ = analyze_technologies_and_manifests(sample_python_repo["file_tree"])
    modules = partition_and_analyze_modules(sample_python_repo["file_tree"], techs)
    issue = {
        "number": 101,
        "title": "Fix user authentication error in api routes",
        "body": "When requesting /api/user, an unhandled exception occurs in api/routes.py with model validation.",
        "labels": ["bug", "api"],
    }

    mapping = map_issue_to_repository_modules(
        issue=issue,
        file_tree=sample_python_repo["file_tree"],
        modules=modules,
    )

    assert mapping.issue_number == 101
    assert mapping.issue_title == issue["title"]
    assert len(mapping.candidate_files) > 0

    # Grounding check: candidate paths MUST be in repository file tree
    tree_set = set(sample_python_repo["file_tree"])
    for cand in mapping.candidate_files:
        assert cand.path in tree_set
        assert cand.relevance_score >= 0.0
        assert cand.relevance_score <= 1.0
        assert len(cand.reasons) > 0

    # Top candidate should be routes or user model
    top_paths = [c.path for c in mapping.candidate_files[:3]]
    assert any("routes.py" in p or "user.py" in p for p in top_paths)
    assert len(mapping.unknowns_and_limitations) >= 2


# =====================================================================
# 7. Complete Deterministic Intelligence Report
# =====================================================================


def test_generate_repository_intelligence_end_to_end(sample_python_repo):
    issues = [
        {
            "number": 101,
            "title": "Bug in API routes",
            "body": "Detail on api routes.",
            "labels": ["bug"],
        }
    ]

    report = generate_repository_intelligence(
        owner=sample_python_repo["owner"],
        repo_name=sample_python_repo["name"],
        languages=sample_python_repo["languages"],
        file_tree=sample_python_repo["file_tree"],
        docs_metadata=sample_python_repo["docs_metadata"],
        ci_evidence=SignalEvidence(
            status="verified",
            source="test",
            value={"status": "detected"},
        ),
        candidate_issues=issues,
        is_truncated=False,
    )

    assert report.repo_name == "fast-service"
    assert report.repo_owner == "testorg"
    assert report.languages.primary == "Python"
    assert len(report.entry_points) > 0
    assert report.test_profile.status == "detected"
    assert report.documentation_profile.has_readme is True
    assert len(report.modules) > 0
    assert len(report.issue_mappings) == 1
    assert report.issue_mappings[0].issue_number == 101
    assert report.tree_truncated is False


# =====================================================================
# 8. API Endpoint POST /api/intelligence
# =====================================================================


@pytest.mark.asyncio
async def test_intelligence_endpoint_demo_mode():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/intelligence",
            json={"repo_url": "https://github.com/psf/requests", "demo": True},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["repo_owner"] == "psf"
        assert data["repo_name"] == "requests"
        assert "languages" in data
        assert "entry_points" in data
        assert "test_profile" in data
        assert "documentation_profile" in data
        assert "modules" in data
        assert "issue_mappings" in data
        assert len(data["entry_points"]) > 0
        assert data["test_profile"]["status"] == "detected"


@pytest.mark.asyncio
async def test_intelligence_endpoint_invalid_url():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/intelligence",
            json={"repo_url": "https://notgithub.com/bad/url"},
        )
        assert resp.status_code == 400
        assert "Only repositories hosted directly on github.com are supported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_analyze_endpoint_includes_intelligence_in_demo_mode():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/analyze",
            json={
                "repo_url": "https://github.com/psf/requests",
                "profile": {
                    "skills": ["python"],
                    "preferred_languages": ["python"],
                    "experience_level": "intermediate",
                    "available_hours": 5.0,
                    "learning_goal": "Contribute to HTTP client",
                },
                "demo": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "intelligence" in data
        assert data["intelligence"] is not None
        assert data["intelligence"]["repo_name"] == "requests"

        # Check candidate issues have module_mapping populated
        for issue in data["issues"]:
            assert "module_mapping" in issue
            if issue.get("module_mapping"):
                assert "candidate_files" in issue["module_mapping"]
                assert "candidate_modules" in issue["module_mapping"]
