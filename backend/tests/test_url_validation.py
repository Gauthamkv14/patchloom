"""Unit tests for GitHub URL structural validation and canonicalization."""

import pytest
from app.github_client import InvalidGitHubURLError, parse_and_validate_github_url


@pytest.mark.parametrize(
    "valid_url,expected_owner,expected_repo",
    [
        ("https://github.com/psf/requests", "psf", "requests"),
        ("https://github.com/psf/requests/", "psf", "requests"),
        ("https://github.com/psf/requests.git", "psf", "requests"),
        ("https://github.com/fastapi/fastapi", "fastapi", "fastapi"),
        ("https://github.com/owner-123/repo_abc.v2", "owner-123", "repo_abc.v2"),
        ("https://GITHUB.COM/owner/repo", "owner", "repo"),
        ("https://github.com:443/owner/repo", "owner", "repo"),
    ],
)
def test_valid_github_urls(valid_url, expected_owner, expected_repo):
    owner, repo = parse_and_validate_github_url(valid_url)
    assert owner == expected_owner
    assert repo == expected_repo


@pytest.mark.parametrize(
    "invalid_url,reason",
    [
        ("", "Empty string"),
        ("   ", "Whitespace only"),
        ("http://github.com/psf/requests", "Non-HTTPS"),
        ("ftp://github.com/psf/requests", "FTP scheme"),
        ("ssh://git@github.com/psf/requests", "SSH scheme"),
        ("https://gitlab.com/psf/requests", "Non-GitHub host"),
        ("https://gist.github.com/username/123456", "Gist host"),
        ("https://ghe.company.com/owner/repo", "Enterprise host"),
        ("https://github.com/owner", "Missing repo segment (user profile)"),
        ("https://github.com/owner/repo/pull/12", "Extra path segment"),
        ("https://github.com/owner/repo/issues", "Extra path segment"),
        ("https://user:pass@github.com/owner/repo", "Credentials in URL"),
        ("https://github.com:8080/owner/repo", "Non-standard port"),
        ("https://github.com/owner/repo?tab=readme", "Query string present"),
        ("https://github.com/owner/repo#section", "Fragment present"),
        ("https://github.com/owner/repo%00", "Null byte trick"),
        ("https://github.com/owner/..%2fadmin", "Encoded path traversal"),
        ("https://github.com/owner/../repo", "Path traversal"),
        ("https://github.com/owner/repo/sub/dir", "Subdirectory deep path"),
    ],
)
def test_invalid_github_urls(invalid_url, reason):
    with pytest.raises(InvalidGitHubURLError):
        parse_and_validate_github_url(invalid_url)
