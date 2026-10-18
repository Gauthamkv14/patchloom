"""Deterministic issue viability evaluation and signal extraction engine."""

import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.schemas import CandidateIssue, SignalEvidence

# Keywords indicating active claim on an issue
CLAIM_PATTERNS = (
    r"\bi am working on this\b",
    r"\bi'm working on this\b",
    r"\bi would like to work on this\b",
    r"\bi'd like to work on this\b",
    r"\bcan i take this\b",
    r"\btaking this up\b",
    r"\bworking on a (pr|fix|patch)\b",
    r"\bi'll take this\b",
    r"\bassign this to me\b",
    r"\bassigned to me\b",
)
CLAIM_REGEX = re.compile("|".join(CLAIM_PATTERNS), re.IGNORECASE)

# Keywords indicating linked PR references in text
PR_REF_PATTERNS = (
    r"\bfixes #\d+\b",
    r"\bcloses #\d+\b",
    r"\bresolves #\d+\b",
    r"\bpr #\d+\b",
    r"github\.com\/[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+\/pull\/\d+",
)
PR_REF_REGEX = re.compile("|".join(PR_REF_PATTERNS), re.IGNORECASE)

# Body quality keywords indicating structured repro / expected behavior
REPRO_PATTERNS = (
    r"expected behavior",
    r"actual behavior",
    r"steps to reproduce",
    r"reproduction",
    r"how to reproduce",
    r"acceptance criteria",
    r"to reproduce",
    r"description",
)
REPRO_REGEX = re.compile("|".join(REPRO_PATTERNS), re.IGNORECASE)

# Labels of interest for first-time contributors
GOOD_FIRST_LABELS = {"good first issue", "good-first-issue", "beginner-friendly", "easy", "starter", "e-easy"}
HELP_WANTED_LABELS = {"help wanted", "help-wanted", "up-for-grabs"}
BUG_LABELS = {"bug", "defect", "fix"}
DOC_LABELS = {"documentation", "docs", "doc"}

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def parse_iso_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 string to timezone-aware UTC datetime."""
    if not iso_str:
        return None
    try:
        # Handle trailing Z
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def calculate_days_ago(dt: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Compute elapsed days since a given datetime."""
    if not dt:
        return None
    ref_time = now or datetime.now(timezone.utc)
    delta = ref_time - dt
    return max(0, delta.days)


def detect_linked_pr_status(
    issue: dict[str, Any],
    comments: list[dict[str, Any]],
    timeline_events: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str, Optional[str]]:
    """
    Detect linked open pull request evidence with strict provenance tracking.

    Returns:
      (status: "detected" | "none_detected" | "unknown", source: str, detail: Optional[str])
    """
    # 1. Check timeline events if available
    if timeline_events is not None:
        for event in timeline_events:
            event_type = event.get("event")
            if event_type in ("cross-referenced", "connected"):
                source_issue = event.get("source", {}).get("issue", {})
                if "pull_request" in source_issue and source_issue.get("state") == "open":
                    pr_num = source_issue.get("number")
                    return "detected", "github_issue_timeline", f"Linked open PR #{pr_num} confirmed via timeline"

    # 2. Heuristic check across candidate comments and issue body
    body = (issue.get("body") or "")
    if PR_REF_REGEX.search(body):
        return "detected", "issue_body_heuristic", "PR cross-reference pattern detected in issue description"

    for comment in comments:
        c_body = comment.get("body") or ""
        if PR_REF_REGEX.search(c_body):
            author = comment.get("user", {}).get("login", "unknown")
            return "detected", "comment_text_heuristic", f"PR cross-reference detected in comment by @{author}"

    # If timeline events check was not provided or skipped, and no comment heuristic matched
    if timeline_events is None:
        return "none_detected", "comments_heuristic_only", "No PR cross-references found in comments (timeline unqueried)"

    return "none_detected", "github_timeline_and_comments", "No linked open PRs found in timeline or comments"


def extract_issue_signals(
    issue: dict[str, Any],
    docs_metadata: dict[str, Any],
    comments: list[dict[str, Any]],
    timeline_events: Optional[list[dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> tuple[dict[str, SignalEvidence], list[str], list[str], int, str]:
    """
    Extract deterministic signals, compute viability score, and identify factors.

    Returns:
      (signals_dict, negative_factors, unknown_factors, viability_score, viability_band)
    """
    ref_time = now or datetime.now(timezone.utc)
    observed_iso = ref_time.isoformat()

    # Dates
    created_dt = parse_iso_datetime(issue.get("created_at"))
    updated_dt = parse_iso_datetime(issue.get("updated_at"))
    days_created = calculate_days_ago(created_dt, ref_time)
    days_updated = calculate_days_ago(updated_dt, ref_time)

    # Assignees
    assignees = issue.get("assignees") or []
    assignee = issue.get("assignee")
    is_assigned = bool(assignee or assignees)
    assignee_count = len(assignees) if assignees else (1 if assignee else 0)

    # Comments & Maintainer reply
    comments_count = issue.get("comments", 0)
    creator_assoc = issue.get("author_association", "")
    has_maintainer_reply = creator_assoc in MAINTAINER_ASSOCIATIONS

    for comment in comments:
        assoc = comment.get("author_association", "")
        if assoc in MAINTAINER_ASSOCIATIONS:
            has_maintainer_reply = True
            break

    # Linked PR
    pr_status, pr_source, pr_detail = detect_linked_pr_status(issue, comments, timeline_events)

    # Labels
    raw_labels = issue.get("labels") or []
    label_names = [
        (lbl.get("name") if isinstance(lbl, dict) else str(lbl)).strip().lower()
        for lbl in raw_labels
    ]
    has_good_first = any(l in GOOD_FIRST_LABELS for l in label_names)
    has_help_wanted = any(l in HELP_WANTED_LABELS for l in label_names)
    has_bug = any(l in BUG_LABELS for l in label_names)
    has_doc = any(l in DOC_LABELS for l in label_names)

    # Documentation guidance
    has_setup_guide = docs_metadata.get("has_setup_guide", False)
    has_test_guide = docs_metadata.get("has_test_guide", False)
    has_readme = docs_metadata.get("has_readme", False)

    # Body completeness
    body = issue.get("body") or ""
    body_len = len(body.strip())
    has_repro_text = bool(REPRO_REGEX.search(body))
    is_body_complete = (body_len >= 200) and (has_repro_text or body_len >= 500)

    # Claimed by contributor heuristic
    claims_working = False
    claim_context = None
    for comment in comments:
        c_body = comment.get("body") or ""
        match = CLAIM_REGEX.search(c_body)
        if match:
            claims_working = True
            author = comment.get("user", {}).get("login", "unknown")
            claim_context = f"Comment by @{author}: '{match.group(0)}'"
            break

    # Build SignalEvidence map with provenance
    signals: dict[str, SignalEvidence] = {
        "days_since_created": SignalEvidence(
            status="verified" if days_created is not None else "unknown",
            source="github_issue.created_at",
            observed_at=observed_iso,
            value=days_created,
        ),
        "days_since_updated": SignalEvidence(
            status="verified" if days_updated is not None else "unknown",
            source="github_issue.updated_at",
            observed_at=observed_iso,
            value=days_updated,
        ),
        "comments_count": SignalEvidence(
            status="verified",
            source="github_issue.comments",
            observed_at=observed_iso,
            value=comments_count,
        ),
        "is_assigned": SignalEvidence(
            status="verified",
            source="github_issue.assignees",
            observed_at=observed_iso,
            value=is_assigned,
        ),
        "assignee_count": SignalEvidence(
            status="verified",
            source="github_issue.assignees",
            observed_at=observed_iso,
            value=assignee_count,
        ),
        "linked_pr": SignalEvidence(
            status="verified" if pr_status == "detected" and timeline_events is not None else ("unknown" if pr_status == "unknown" else "inference"),
            source=pr_source,
            observed_at=observed_iso,
            value={"status": pr_status, "detail": pr_detail},
        ),
        "has_maintainer_reply": SignalEvidence(
            status="verified",
            source="github_issue.comments.author_association",
            observed_at=observed_iso,
            value=has_maintainer_reply,
        ),
        "has_good_first_issue_label": SignalEvidence(
            status="verified",
            source="github_issue.labels",
            observed_at=observed_iso,
            value=has_good_first,
        ),
        "has_help_wanted_label": SignalEvidence(
            status="verified",
            source="github_issue.labels",
            observed_at=observed_iso,
            value=has_help_wanted,
        ),
        "has_setup_guidance": SignalEvidence(
            status="inference",
            source="repo_readme_contributing_heuristics",
            observed_at=observed_iso,
            value=has_setup_guide,
        ),
        "body_completeness": SignalEvidence(
            status="inference",
            source="issue_body_heuristics",
            observed_at=observed_iso,
            value={"length": body_len, "has_repro_hints": has_repro_text, "is_complete": is_body_complete},
        ),
        "claims_working_on_it": SignalEvidence(
            status="inference",
            source="comment_text_heuristics",
            observed_at=observed_iso,
            value={"detected": claims_working, "context": claim_context},
        ),
    }

    # -------------------------------------------------------------
    # Viability Score Computation (0 - 100)
    # Base: 100
    # -------------------------------------------------------------
    score = 100
    negative_factors: list[str] = []
    unknown_factors: list[str] = []

    # Inactivity penalties
    if days_updated is not None:
        if days_updated >= 180:
            score -= 25
            negative_factors.append("No activity for over 180 days (-25)")
        elif days_updated >= 90:
            score -= 15
            negative_factors.append("No activity for over 90 days (-15)")
    else:
        unknown_factors.append("Update timestamp unavailable")

    # Assignment penalty
    if is_assigned:
        score -= 40
        negative_factors.append(f"Issue is already assigned to {assignee_count} contributor(s) (-40)")

    # Linked PR penalties
    if pr_status == "detected":
        score -= 40
        negative_factors.append("Linked open PR detected in cross-references (-40)")
    elif pr_status == "unknown":
        score -= 10
        negative_factors.append("Linked PR status unknown (-10)")
        unknown_factors.append("Could not verify linked PR presence")

    # Maintainer responsiveness penalty
    if not has_maintainer_reply:
        score -= 10
        negative_factors.append("No maintainer/collaborator comment found (-10)")

    # Documentation guidance penalty
    if not has_setup_guide:
        score -= 15
        negative_factors.append("No clear setup or installation guidance found in README/CONTRIBUTING (-15)")

    # Body completeness penalty
    if not is_body_complete:
        score -= 15
        negative_factors.append("Issue description is brief (<200 chars) or lacks clear reproduction/expected behavior (-15)")

    # Active work claim penalty
    if claims_working:
        score -= 20
        negative_factors.append(f"Contributor already stated intent to work on this: {claim_context} (-20)")

    # Clamp score to [0, 100]
    viability_score = max(0, min(100, score))

    if viability_score >= 75:
        viability_band = "high"
    elif viability_score >= 45:
        viability_band = "medium"
    else:
        viability_band = "low"

    return signals, negative_factors, unknown_factors, viability_score, viability_band


def filter_and_rank_candidates(
    raw_issues: list[dict[str, Any]],
    docs_metadata: dict[str, Any],
    comments_by_issue: Optional[dict[int, list[dict[str, Any]]]] = None,
    max_candidates: int = 12,
    now: Optional[datetime] = None,
) -> list[CandidateIssue]:
    """
    Deterministic candidate pre-filter.
    1. Evaluates signals for all open non-PR issues.
    2. Excludes assigned issues and verified linked PR issues (unless all are assigned).
    3. Ranks candidates prioritizing high viability, beginner/help-wanted labels, and recent activity.
    4. Slices to at most max_candidates (never pads).
    """
    comments_map = comments_by_issue or {}
    evaluated: list[CandidateIssue] = []

    for issue in raw_issues:
        num = issue.get("number")
        if not num or "pull_request" in issue:
            continue

        comments = comments_map.get(num, [])
        signals, neg_factors, unk_factors, v_score, v_band = extract_issue_signals(
            issue=issue,
            docs_metadata=docs_metadata,
            comments=comments,
            now=now,
        )

        labels = [
            (lbl.get("name") if isinstance(lbl, dict) else str(lbl)).strip()
            for lbl in (issue.get("labels") or [])
        ]

        evaluated.append(
            CandidateIssue(
                number=num,
                title=issue.get("title", ""),
                url=issue.get("html_url") or f"https://github.com/unknown/repo/issues/{num}",
                labels=labels,
                created_at=issue.get("created_at", ""),
                updated_at=issue.get("updated_at", ""),
                comments_count=issue.get("comments", 0),
                viability_score=v_score,
                viability_band=v_band,
                signals=signals,
                negative_factors=neg_factors,
                unknown_factors=unk_factors,
            )
        )

    # Primary filter: exclude assigned issues and detected linked PRs
    eligible = [
        c for c in evaluated
        if not c.signals["is_assigned"].value
        and c.signals["linked_pr"].value.get("status") != "detected"
    ]

    # If eligible is empty (e.g. all available open issues are assigned), fall back to evaluated to prevent empty screen
    pool = eligible if eligible else evaluated

    # Sorting heuristic for deterministic candidate preselection:
    # 1. Viability score descending
    # 2. Presence of 'good first issue' / 'help wanted' bonus
    # 3. Recency of update
    def sort_key(cand: CandidateIssue) -> tuple:
        has_gfi = 1 if cand.signals["has_good_first_issue_label"].value else 0
        has_hw = 1 if cand.signals["has_help_wanted_label"].value else 0
        days_updated = cand.signals["days_since_updated"].value or 999
        # Lower days_updated is better, higher viability is better
        return (cand.viability_score, (has_gfi * 2) + has_hw, -days_updated)

    pool.sort(key=sort_key, reverse=True)
    return pool[:max_candidates]
