"""Unit tests for deterministic viability scoring, evidence labeling, and candidate filtering."""

from datetime import datetime, timezone, timedelta
import pytest

from app.signals import (
    extract_issue_signals,
    filter_and_rank_candidates,
    detect_linked_pr_status,
)


@pytest.fixture
def base_time():
    return datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def perfect_docs():
    return {
        "has_readme": True,
        "has_contributing": True,
        "has_setup_guide": True,
        "has_test_guide": True,
    }


def make_issue(
    number=1,
    title="Clear issue",
    body="This is an extensive description with steps to reproduce the bug. " * 5,  # >200 chars
    created_days_ago=10,
    updated_days_ago=5,
    assignees=None,
    author_association="MEMBER",
    labels=None,
    base_time=None,
):
    now = base_time or datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    created_at = (now - timedelta(days=created_days_ago)).isoformat()
    updated_at = (now - timedelta(days=updated_days_ago)).isoformat()
    return {
        "number": number,
        "title": title,
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at,
        "comments": 2,
        "assignees": assignees or [],
        "assignee": (assignees[0] if assignees else None),
        "author_association": author_association,
        "labels": labels or [{"name": "bug"}],
        "html_url": f"https://github.com/org/repo/issues/{number}",
    }


def test_perfect_issue_viability_score(perfect_docs, base_time):
    """Verify an active, well-documented issue with maintainer involvement gets score 100 (high)."""
    issue = make_issue(base_time=base_time)
    comments = [
        {"author_association": "MEMBER", "body": "Thank you for the report!", "user": {"login": "maintainer"}}
    ]

    signals, neg, unk, score, band = extract_issue_signals(
        issue=issue, docs_metadata=perfect_docs, comments=comments, now=base_time
    )

    assert score == 100
    assert band == "high"
    assert len(neg) == 0


def test_inactivity_penalties(perfect_docs, base_time):
    """Verify 90+ days penalty (-15) and 180+ days penalty (-25 non-cumulative)."""
    # 100 days old -> -15
    issue_90 = make_issue(updated_days_ago=100, base_time=base_time)
    _, neg_90, _, score_90, band_90 = extract_issue_signals(
        issue=issue_90, docs_metadata=perfect_docs, comments=[], now=base_time
    )
    assert score_90 == 85
    assert any("-15" in f for f in neg_90)

    # 200 days old -> -25
    issue_180 = make_issue(updated_days_ago=200, base_time=base_time)
    _, neg_180, _, score_180, band_180 = extract_issue_signals(
        issue=issue_180, docs_metadata=perfect_docs, comments=[], now=base_time
    )
    assert score_180 == 75
    assert any("-25" in f for f in neg_180)


def test_assignment_penalty(perfect_docs, base_time):
    """Verify assigned issues receive a -40 penalty."""
    issue = make_issue(assignees=[{"login": "contributor1"}], base_time=base_time)
    _, neg, _, score, _ = extract_issue_signals(
        issue=issue, docs_metadata=perfect_docs, comments=[], now=base_time
    )
    assert score == 60
    assert any("-40" in f for f in neg)


def test_linked_pr_penalties(perfect_docs, base_time):
    """Verify detected linked PR receives -40, while unknown link status receives -10."""
    # Detected via timeline
    issue = make_issue(base_time=base_time)
    timeline = [{"event": "cross-referenced", "source": {"issue": {"pull_request": {}, "state": "open", "number": 99}}}]
    _, neg_det, _, score_det, band_det = extract_issue_signals(
        issue=issue, docs_metadata=perfect_docs, comments=[], timeline_events=timeline, now=base_time
    )
    assert score_det == 60
    assert any("-40" in f for f in neg_det)

    # Detected via heuristic keyword in comment
    comment_with_pr = [{"body": "I submitted fixes #1 in PR #99", "user": {"login": "dev"}}]
    _, neg_heur, _, score_heur, _ = extract_issue_signals(
        issue=issue, docs_metadata=perfect_docs, comments=comment_with_pr, timeline_events=None, now=base_time
    )
    assert score_heur == 60


def test_missing_setup_guidance_and_brief_body(base_time):
    """Verify penalties for missing setup guidance (-15) and brief description (-15)."""
    docs_no_setup = {"has_setup_guide": False, "has_readme": True}
    brief_issue = make_issue(body="Bug found.", base_time=base_time)  # <200 chars

    _, neg, _, score, band = extract_issue_signals(
        issue=brief_issue, docs_metadata=docs_no_setup, comments=[], now=base_time
    )

    # 100 - 15 (no setup) - 15 (brief body) = 70 (medium)
    assert score == 70
    assert band == "medium"
    assert len(neg) == 2


def test_work_claimed_heuristic(perfect_docs, base_time):
    """Verify -20 penalty when contributor states they are working on it."""
    issue = make_issue(base_time=base_time)
    comments = [{"body": "I am working on this, please don't touch", "user": {"login": "student"}}]

    _, neg, _, score, _ = extract_issue_signals(
        issue=issue, docs_metadata=perfect_docs, comments=comments, now=base_time
    )
    assert score == 80
    assert any("-20" in f for f in neg)


def test_viability_score_clamping(base_time):
    """Verify viability score clamps at 0 and never becomes negative."""
    # Accumulate all penalties: -25 (old) -40 (assigned) -40 (PR) -10 (no maintainer) -15 (no setup) -15 (brief) -20 (claimed) = -165
    awful_issue = make_issue(
        body="x",
        updated_days_ago=300,
        assignees=[{"login": "user"}],
        author_association="NONE",
        base_time=base_time,
    )
    awful_docs = {"has_setup_guide": False}
    timeline = [{"event": "cross-referenced", "source": {"issue": {"pull_request": {}, "state": "open"}}}]
    comments = [{"body": "i am working on this", "author_association": "NONE"}]

    _, _, _, score, band = extract_issue_signals(
        issue=awful_issue, docs_metadata=awful_docs, comments=comments, timeline_events=timeline, now=base_time
    )

    assert score == 0
    assert band == "low"


def test_candidate_filtering_and_ranking(perfect_docs, base_time):
    """Verify candidate filtering excludes assigned issues and ranks appropriately."""
    issues = [
        # 1. Assigned issue (should be filtered out)
        make_issue(number=101, title="Assigned Issue", assignees=[{"login": "worker"}], base_time=base_time),
        # 2. Great beginner issue (good first issue label, fresh)
        make_issue(number=102, title="Good First Bug", labels=[{"name": "good first issue"}], base_time=base_time),
        # 3. Regular active issue
        make_issue(number=103, title="Regular Issue", labels=[{"name": "bug"}], base_time=base_time),
        # 4. Old stale issue (200 days old)
        make_issue(number=104, title="Stale Issue", updated_days_ago=200, base_time=base_time),
    ]

    candidates = filter_and_rank_candidates(
        raw_issues=issues,
        docs_metadata=perfect_docs,
        max_candidates=3,
        now=base_time,
    )

    # 101 should be excluded because assigned
    candidate_numbers = [c.number for c in candidates]
    assert 101 not in candidate_numbers

    # 102 (good first issue) should be ranked first
    assert candidate_numbers[0] == 102
    assert len(candidates) == 3
