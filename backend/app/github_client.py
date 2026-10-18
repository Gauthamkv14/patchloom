"""GitHub REST API client with strict structural URL validation, bounding, and caching."""

import base64
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.cache import app_cache
from app.config import settings
from app.schemas import RepoMetadata

GITHUB_API_BASE = "https://api.github.com"
MAX_PATH_COUNT = 400
MAX_TREE_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DOC_PAYLOAD_BYTES = 512 * 1024  # 512 KB

# Path patterns to ignore when building the candidate tree
IGNORED_PATH_PREFIXES = (
    ".git/",
    ".github/",
    ".vscode/",
    ".idea/",
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    "target/",
    "out/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "env/",
    ".pytest_cache/",
)

IGNORED_FILE_EXACT = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
    ".gitignore",
    ".gitattributes",
}

IGNORED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pyc", ".pyo", ".class", ".wasm",
    ".pdf", ".mp4", ".mp3",
)

# Structural identifier pattern for owner and repo
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class InvalidGitHubURLError(ValueError):
    """Raised when the repository URL violates strict canonical GitHub criteria."""
    pass


class GitHubClientError(Exception):
    """Base exception for GitHub API errors."""
    pass


class RepoNotFoundError(GitHubClientError):
    """Repository does not exist or is private."""
    pass


class IssueNotFoundError(GitHubClientError):
    """Requested issue does not exist in the repository."""
    pass


class IssueClosedError(GitHubClientError):
    """Requested issue is already closed."""
    pass


class RepoAccessError(GitHubClientError):
    """Access forbidden or missing permissions."""
    pass


class RateLimitExceededError(GitHubClientError):
    """GitHub API rate limit exhausted."""

    def __init__(self, message: str, retry_after: Optional[int] = None, reset_epoch: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.reset_epoch = reset_epoch


class GitHubUpstreamError(GitHubClientError):
    """GitHub service error or bad gateway."""
    pass


def parse_and_validate_github_url(url: str) -> tuple[str, str]:
    """
    Strict structural validation of a GitHub repository URL.

    Accepts:
      - https://github.com/OWNER/REPO
      - https://github.com/OWNER/REPO/
      - https://github.com/OWNER/REPO.git

    Rejects:
      - Non-HTTPS schemes
      - Any host other than exact 'github.com'
      - URLs containing credentials (user:pass@) or ports
      - Query strings or fragments
      - Encoded path traversal (%2f, %2e, %00)
      - Non-canonical paths (extra segments, user pages, gists)
    """
    if not url or not isinstance(url, str):
        raise InvalidGitHubURLError("URL must be a non-empty string")

    stripped = url.strip()
    if not stripped:
        raise InvalidGitHubURLError("URL cannot be empty or whitespace")

    # Reject null bytes or raw control characters
    if "\x00" in stripped or any(ord(c) < 32 for c in stripped):
        raise InvalidGitHubURLError("URL contains invalid control characters")

    # Reject URL-encoded path manipulation tricks before parsing
    lower_raw = stripped.lower()
    if "%00" in lower_raw or "%2f" in lower_raw or "%2e" in lower_raw:
        raise InvalidGitHubURLError("URL contains forbidden encoded traversal or separator sequences")

    try:
        parsed = urllib.parse.urlsplit(stripped)
    except Exception as exc:
        raise InvalidGitHubURLError(f"Malformed URL structure: {exc}") from exc

    # 1. Scheme check
    if parsed.scheme.lower() != "https":
        raise InvalidGitHubURLError("Only HTTPS GitHub URLs are accepted (http:// and other schemes are rejected)")

    # 2. Host check: exactly 'github.com' (no credentials, no subdomains, no alternate ports)
    netloc = parsed.netloc
    if "@" in netloc:
        raise InvalidGitHubURLError("User credentials in URL are strictly rejected")

    host_parts = netloc.split(":")
    hostname = host_parts[0].lower()
    if hostname != "github.com":
        raise InvalidGitHubURLError(f"Only repositories hosted directly on github.com are supported (got '{hostname}')")

    if len(host_parts) > 1 and host_parts[1] != "443":
        raise InvalidGitHubURLError(f"Non-standard port '{host_parts[1]}' is rejected")

    # 3. Query string and fragment check: must be strictly absent
    if parsed.query:
        raise InvalidGitHubURLError("URL query parameters are forbidden")
    if parsed.fragment:
        raise InvalidGitHubURLError("URL fragments are forbidden")

    # 4. Path analysis
    path = parsed.path
    # Normalize .git suffix and slashes
    segments = [s for s in path.strip("/").split("/") if s]

    if len(segments) != 2:
        raise InvalidGitHubURLError(
            "URL must specify exactly /OWNER/REPO with no extra path segments, gists, or user pages"
        )

    owner, repo = segments[0], segments[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise InvalidGitHubURLError("Owner and repository name cannot be empty")

    if owner in (".", "..") or repo in (".", ".."):
        raise InvalidGitHubURLError("Path traversal sequences in repository coordinates are rejected")

    if not ID_PATTERN.match(owner):
        raise InvalidGitHubURLError(f"Invalid characters in owner identifier '{owner}'")

    if not ID_PATTERN.match(repo):
        raise InvalidGitHubURLError(f"Invalid characters in repository identifier '{repo}'")

    return owner, repo


class GitHubClient:
    """Async client for fetching public GitHub repository data with strict boundaries."""

    def __init__(self, token: Optional[str] = None, timeout: float = 20.0):
        self.token = token or settings.GITHUB_TOKEN
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PatchLoom-Contributor-Agent/1.0",
        }
        if self.token and self.token.strip():
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    def _create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=self._get_headers(),
            timeout=self.timeout,
            follow_redirects=False,  # Enforce SSRF protection: never follow arbitrary redirects
        )

    def _handle_response_error(self, response: httpx.Response, resource_name: str) -> None:
        """Map HTTP error codes to domain exceptions safely without leaking tokens."""
        if response.status_code == 404:
            raise RepoNotFoundError(f"Resource '{resource_name}' was not found or is private on GitHub")
        if response.status_code in (403, 429):
            retry_after = response.headers.get("retry-after")
            reset_epoch = response.headers.get("x-ratelimit-reset")
            retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
            reset_ts = int(reset_epoch) if reset_epoch and reset_epoch.isdigit() else None
            raise RateLimitExceededError(
                "GitHub API rate limit exceeded or access forbidden. Please configure a GITHUB_TOKEN.",
                retry_after=retry_seconds,
                reset_epoch=reset_ts,
            )
        if response.status_code >= 500:
            raise GitHubUpstreamError(f"GitHub returned upstream server error {response.status_code}")
        response.raise_for_status()

    async def fetch_repo_metadata(self, owner: str, repo: str) -> RepoMetadata:
        """Fetch canonical repository metadata with 10-minute caching."""
        cache_key = f"repo:{owner.lower()}/{repo.lower()}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        async with self._create_http_client() as client:
            resp = await client.get(f"/repos/{owner}/{repo}")
            if resp.status_code != 200:
                self._handle_response_error(resp, f"{owner}/{repo}")

            data = resp.json()
            if data.get("private", False):
                raise RepoAccessError(f"Repository {owner}/{repo} is private; PatchLoom only supports public repos")

            # Fetch primary languages
            languages: list[str] = []
            lang_resp = await client.get(f"/repos/{owner}/{repo}/languages")
            if lang_resp.status_code == 200:
                lang_data = lang_resp.json()
                languages = list(lang_data.keys())[:5]

            meta = RepoMetadata(
                owner=data.get("owner", {}).get("login", owner),
                name=data.get("name", repo),
                description=data.get("description"),
                default_branch=data.get("default_branch", "main"),
                languages=languages,
                open_issues_count=data.get("open_issues_count", 0),
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
            app_cache.set(cache_key, meta, ttl_seconds=600.0)
            return meta

    async def fetch_open_issues(
        self, owner: str, repo: str, max_pages: int = 2, per_page: int = 100
    ) -> list[dict[str, Any]]:
        """
        Fetch recent open issues, bounded to max_pages (default 2, up to 200 items).
        Excludes pull requests immediately. Cached for 2 minutes.
        """
        cache_key = f"issues:{owner.lower()}/{repo.lower()}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        pure_issues: list[dict[str, Any]] = []

        async with self._create_http_client() as client:
            for page in range(1, max_pages + 1):
                resp = await client.get(
                    f"/repos/{owner}/{repo}/issues",
                    params={
                        "state": "open",
                        "sort": "updated",
                        "direction": "desc",
                        "per_page": min(per_page, 100),
                        "page": page,
                    },
                )
                if resp.status_code != 200:
                    self._handle_response_error(resp, f"issues for {owner}/{repo}")

                items = resp.json()
                if not items or not isinstance(items, list):
                    break

                for item in items:
                    # Filter out pull requests immediately
                    if "pull_request" not in item:
                        pure_issues.append(item)

                if len(items) < per_page:
                    break

        app_cache.set(cache_key, pure_issues, ttl_seconds=120.0)
        return pure_issues

    async def fetch_documentation(self, owner: str, repo: str) -> dict[str, Any]:
        """
        Fetch README and CONTRIBUTING files if present.
        Extracts guidance hints (setup and test instructions).
        Cached for 10 minutes.
        """
        cache_key = f"docs:{owner.lower()}/{repo.lower()}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        readme_text = ""
        contributing_text = ""
        has_readme = False
        has_contributing = False

        async with self._create_http_client() as client:
            # 1. Fetch README
            readme_resp = await client.get(f"/repos/{owner}/{repo}/readme")
            if readme_resp.status_code == 200:
                has_readme = True
                content = readme_resp.json().get("content", "")
                encoding = readme_resp.json().get("encoding", "")
                if encoding == "base64" and content:
                    try:
                        readme_text = base64.b64decode(content).decode("utf-8", errors="replace")[:10000]
                    except Exception:
                        readme_text = ""

            # 2. Fetch CONTRIBUTING if available
            for candidate in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "contributing.md"):
                contrib_resp = await client.get(f"/repos/{owner}/{repo}/contents/{candidate}")
                if contrib_resp.status_code == 200:
                    has_contributing = True
                    content = contrib_resp.json().get("content", "")
                    encoding = contrib_resp.json().get("encoding", "")
                    if encoding == "base64" and content:
                        try:
                            contributing_text = base64.b64decode(content).decode("utf-8", errors="replace")[:10000]
                            break
                        except Exception:
                            pass

        # Simple, transparent heuristics for setup and test guidance presence
        combined_lower = (readme_text + " " + contributing_text).lower()
        has_setup_guide = any(
            hint in combined_lower
            for hint in (
                "getting started", "setup", "installation", "prerequisites",
                "quickstart", "development", "local setup", "pip install", "npm install"
            )
        )
        has_test_guide = any(
            hint in combined_lower
            for hint in (
                "pytest", "npm test", "running tests", "cargo test",
                "test suite", "make test", "how to test", "run the tests"
            )
        )

        result = {
            "has_readme": has_readme,
            "has_contributing": has_contributing,
            "has_setup_guide": has_setup_guide,
            "has_test_guide": has_test_guide,
            "readme_excerpt": readme_text[:2000],
            "contributing_excerpt": contributing_text[:2000],
        }
        app_cache.set(cache_key, result, ttl_seconds=600.0)
        return result

    async def fetch_file_tree(
        self, owner: str, repo: str, default_branch: str = "main"
    ) -> tuple[list[str], bool, bool]:
        """
        Fetch recursive Git tree, bounded to 400 paths.
        Distinguishes GitHub-side truncation from application-side slicing.
        Returns: (paths: list[str], github_truncated: bool, app_truncated: bool)
        Cached for 10 minutes.
        """
        cache_key = f"tree:{owner.lower()}/{repo.lower()}:{default_branch}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        async with self._create_http_client() as client:
            resp = await client.get(f"/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1")
            if resp.status_code != 200:
                # If recursive tree fails, return empty
                return [], False, False

            data = resp.json()
            github_truncated = bool(data.get("truncated", False))
            tree_items = data.get("tree", [])

        valid_paths: list[str] = []
        for item in tree_items:
            path = item.get("path", "")
            item_type = item.get("type", "")
            if item_type != "blob" or not path:
                continue

            lower_path = path.lower()
            filename = lower_path.split("/")[-1]

            if any(lower_path.startswith(prefix) for prefix in IGNORED_PATH_PREFIXES):
                continue
            if filename in IGNORED_FILE_EXACT:
                continue
            if any(lower_path.endswith(ext) for ext in IGNORED_EXTENSIONS):
                continue

            valid_paths.append(path)

        app_truncated = len(valid_paths) > MAX_PATH_COUNT
        retained_paths = valid_paths[:MAX_PATH_COUNT]

        result = (retained_paths, github_truncated, app_truncated)
        app_cache.set(cache_key, result, ttl_seconds=600.0)
        return result

    async def fetch_issue_comments(
        self, owner: str, repo: str, issue_number: int, max_comments: int = 3
    ) -> list[dict[str, Any]]:
        """Fetch recent comments for a candidate issue (bounded). Cached for 2 minutes."""
        cache_key = f"comments:{owner.lower()}/{repo.lower()}:{issue_number}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        async with self._create_http_client() as client:
            resp = await client.get(
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                params={"per_page": max_comments, "sort": "created", "direction": "desc"},
            )
            if resp.status_code != 200:
                return []
            comments = resp.json()
            if not isinstance(comments, list):
                return []

            result = comments[:max_comments]
            app_cache.set(cache_key, result, ttl_seconds=120.0)
            return result

    async def fetch_single_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        """Fetch fresh single issue details and verify it is currently open."""
        cache_key = f"single_issue:{owner.lower()}/{repo.lower()}:{issue_number}"
        cached = app_cache.get(cache_key)
        if cached:
            return cached

        async with self._create_http_client() as client:
            resp = await client.get(f"/repos/{owner}/{repo}/issues/{issue_number}")
            if resp.status_code == 404:
                raise IssueNotFoundError(f"Issue #{issue_number} was not found in {owner}/{repo}")
            if resp.status_code != 200:
                self._handle_response_error(resp, f"issue #{issue_number} in {owner}/{repo}")

            data = resp.json()
            if "pull_request" in data:
                raise IssueNotFoundError(f"#{issue_number} is a pull request, not an issue")
            if data.get("state") != "open":
                raise IssueClosedError(f"Issue #{issue_number} is closed and cannot be planned for contribution")

            app_cache.set(cache_key, data, ttl_seconds=60.0)
            return data

