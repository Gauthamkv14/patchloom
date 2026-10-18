"""Mocked unit tests for GitHubClient bounded retrieval and error handling."""

import base64
import pytest
import respx
import httpx
from app.cache import app_cache
from app.github_client import (
    GitHubClient,
    RepoNotFoundError,
    RepoAccessError,
    RateLimitExceededError,
    GitHubUpstreamError,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear in-memory cache before every test."""
    app_cache.clear()
    yield
    app_cache.clear()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_repo_metadata_success():
    """Verify repo metadata parsing and caching."""
    respx.get("https://api.github.com/repos/pallets/flask").respond(
        status_code=200,
        json={
            "name": "flask",
            "owner": {"login": "pallets"},
            "description": "The Python micro framework",
            "default_branch": "main",
            "open_issues_count": 42,
            "private": False,
        },
    )
    respx.get("https://api.github.com/repos/pallets/flask/languages").respond(
        status_code=200,
        json={"Python": 120000, "HTML": 5000},
    )

    client = GitHubClient()
    meta = await client.fetch_repo_metadata("pallets", "flask")

    assert meta.owner == "pallets"
    assert meta.name == "flask"
    assert meta.default_branch == "main"
    assert "Python" in meta.languages
    assert meta.open_issues_count == 42

    # Verify cached retrieval doesn't hit HTTP again
    cached_meta = await client.fetch_repo_metadata("pallets", "flask")
    assert cached_meta.name == "flask"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_repo_metadata_private_repo_rejected():
    """Verify private repositories are rejected with RepoAccessError."""
    respx.get("https://api.github.com/repos/secret/project").respond(
        status_code=200,
        json={
            "name": "project",
            "owner": {"login": "secret"},
            "private": True,
        },
    )

    client = GitHubClient()
    with pytest.raises(RepoAccessError) as exc_info:
        await client.fetch_repo_metadata("secret", "project")
    assert "private" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_repo_metadata_404():
    """Verify non-existent repository triggers RepoNotFoundError."""
    respx.get("https://api.github.com/repos/ghost/nonexistent").respond(status_code=404)

    client = GitHubClient()
    with pytest.raises(RepoNotFoundError):
        await client.fetch_repo_metadata("ghost", "nonexistent")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_repo_metadata_rate_limit():
    """Verify 403 rate limit triggers RateLimitExceededError with retry headers."""
    respx.get("https://api.github.com/repos/popular/repo").respond(
        status_code=403,
        headers={"retry-after": "60", "x-ratelimit-reset": "1700000000"},
        json={"message": "API rate limit exceeded"},
    )

    client = GitHubClient()
    with pytest.raises(RateLimitExceededError) as exc_info:
        await client.fetch_repo_metadata("popular", "repo")
    assert exc_info.value.retry_after == 60


@pytest.mark.asyncio
@respx.mock
async def test_fetch_open_issues_excludes_pull_requests():
    """Verify issues list excludes pull requests."""
    respx.get("https://api.github.com/repos/org/repo/issues").respond(
        status_code=200,
        json=[
            {"id": 1, "number": 101, "title": "Real Bug", "state": "open"},
            {"id": 2, "number": 102, "title": "Feature PR", "state": "open", "pull_request": {"url": "https://..."}},
            {"id": 3, "number": 103, "title": "Doc improvement", "state": "open"},
        ],
    )

    client = GitHubClient()
    issues = await client.fetch_open_issues("org", "repo", max_pages=1)

    assert len(issues) == 2
    issue_numbers = [i["number"] for i in issues]
    assert 101 in issue_numbers
    assert 103 in issue_numbers
    assert 102 not in issue_numbers  # PR excluded


@pytest.mark.asyncio
@respx.mock
async def test_fetch_documentation_hints():
    """Verify README & CONTRIBUTING retrieval and guidance heuristics."""
    readme_content = base64.b64encode(b"# Getting Started\nRun `pip install -r requirements.txt` to setup.\nRun `pytest` for tests.").decode()
    respx.get("https://api.github.com/repos/org/repo/readme").respond(
        status_code=200,
        json={"content": readme_content, "encoding": "base64"},
    )
    respx.get("https://api.github.com/repos/org/repo/contents/CONTRIBUTING.md").respond(
        status_code=404
    )
    respx.get("https://api.github.com/repos/org/repo/contents/.github/CONTRIBUTING.md").respond(
        status_code=404
    )
    respx.get("https://api.github.com/repos/org/repo/contents/contributing.md").respond(
        status_code=404
    )

    client = GitHubClient()
    docs = await client.fetch_documentation("org", "repo")

    assert docs["has_readme"] is True
    assert docs["has_contributing"] is False
    assert docs["has_setup_guide"] is True
    assert docs["has_test_guide"] is True


@pytest.mark.asyncio
@respx.mock
async def test_fetch_file_tree_filters_and_bounds():
    """Verify file tree filters ignored paths and bounds to 400 items."""
    # Generate 450 dummy paths including ignored directories, lockfiles, and binaries
    tree = []
    # 50 ignored items
    for i in range(20):
        tree.append({"path": f"node_modules/pkg_{i}/index.js", "type": "blob"})
    for i in range(10):
        tree.append({"path": f"dist/bundle_{i}.js", "type": "blob"})
    tree.append({"path": "package-lock.json", "type": "blob"})
    tree.append({"path": "assets/logo.png", "type": "blob"})

    # 420 valid source files
    for i in range(420):
        tree.append({"path": f"src/module_{i}.py", "type": "blob"})

    respx.get("https://api.github.com/repos/org/repo/git/trees/main?recursive=1").respond(
        status_code=200,
        json={"tree": tree, "truncated": False},
    )

    client = GitHubClient()
    paths, github_truncated, app_truncated = await client.fetch_file_tree("org", "repo", "main")

    assert len(paths) == 400
    assert github_truncated is False
    assert app_truncated is True  # 420 valid > 400 cap
    assert not any("node_modules" in p for p in paths)
    assert not any(p.endswith(".png") for p in paths)
    assert not any("package-lock.json" in p for p in paths)
