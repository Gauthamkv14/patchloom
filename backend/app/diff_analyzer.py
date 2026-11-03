"""Deterministic Git Diff Analyzer for PatchLoom 2.0 (M4 VERIFY & CONTRIBUTE Pillar).

Safely parses, validates, and bounds unified git diffs without shell execution
or external tool dependencies. Extracts file modifications, hunk statistics,
and touched code symbols.
"""

import re
from typing import Optional
from app.schemas import DiffChangeFile, ImplementationStep, ParsedDiff

# Maximum allowed size for contributor diff input (100 KB)
MAX_DIFF_CHARS = 100_000

# Regexes for symbol detection in added lines
SYMBOL_PATTERNS = [
    re.compile(r"^\+\s*(?:async\s+)?def\s+([A-Za-z0-9_]+)\s*\(", re.MULTILINE),
    re.compile(r"^\+\s*class\s+([A-Za-z0-9_]+)\s*[:\(]", re.MULTILINE),
    re.compile(r"^\+\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(", re.MULTILINE),
    re.compile(r"^\+\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(", re.MULTILINE),
    re.compile(r"^\+\s*#{1,3}\s+([A-Za-z0-9_ \-\.\(\)]+)", re.MULTILINE),
]


def clean_diff_path(raw_path: str) -> str:
    """Strip git diff prefixes ('a/', 'b/') and whitespace."""
    p = raw_path.strip().strip('"').strip("'")
    if p.startswith("a/") or p.startswith("b/"):
        return p[2:]
    return p


def parse_git_diff(
    diff_text: str,
    max_chars: int = MAX_DIFF_CHARS,
) -> ParsedDiff:
    """
    Deterministically parse a unified git diff string.
    Safely bounds input size and extracts per-file change statistics and symbols.
    """
    if not diff_text or not diff_text.strip():
        return ParsedDiff(
            total_files=0,
            lines_added=0,
            lines_removed=0,
            files=[],
            raw_diff_sample="",
            is_truncated=False,
            warnings=["No diff content was provided."],
        )

    is_truncated = False
    warnings: list[str] = []

    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars]
        is_truncated = True
        warnings.append(
            f"Provided diff exceeded safe limit ({max_chars} chars) and was truncated."
        )

    # Split diff into file chunks by 'diff --git '
    raw_chunks: list[str] = []
    if "diff --git " in diff_text:
        parts = diff_text.split("diff --git ")
        for p in parts[1:]:
            raw_chunks.append("diff --git " + p)
    else:
        # Fallback for plain unified diff without git headers
        raw_chunks = [diff_text]

    parsed_files: list[DiffChangeFile] = []
    total_added = 0
    total_removed = 0

    for chunk in raw_chunks:
        lines = chunk.splitlines()
        target_path: Optional[str] = None
        old_path: Optional[str] = None
        change_type = "modified"
        lines_added = 0
        lines_removed = 0
        added_lines_text: list[str] = []

        # Parse header lines
        for line in lines[:25]:
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    old_path = clean_diff_path(parts[2])
                    target_path = clean_diff_path(parts[3])
            elif line.startswith("new file mode"):
                change_type = "added"
            elif line.startswith("deleted file mode"):
                change_type = "deleted"
            elif line.startswith("rename from "):
                old_path = clean_diff_path(line[12:])
                change_type = "renamed"
            elif line.startswith("rename to "):
                target_path = clean_diff_path(line[10:])
                change_type = "renamed"
            elif line.startswith("+++ "):
                p = line[4:].strip()
                if p != "/dev/null":
                    target_path = clean_diff_path(p)
                else:
                    change_type = "deleted"
            elif line.startswith("--- "):
                p = line[4:].strip()
                if p != "/dev/null" and not old_path:
                    old_path = clean_diff_path(p)

        if not target_path and old_path:
            target_path = old_path

        if not target_path:
            continue

        # Count added/removed lines and collect added content
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
                added_lines_text.append(line)
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1

        total_added += lines_added
        total_removed += lines_removed

        # Detect symbols in added lines
        detected_symbols: list[str] = []
        full_added = "\n".join(added_lines_text)
        for pat in SYMBOL_PATTERNS:
            for m in pat.finditer(full_added):
                sym = m.group(1).strip()
                if sym and sym not in detected_symbols:
                    detected_symbols.append(sym)

        parsed_files.append(
            DiffChangeFile(
                path=target_path,
                old_path=old_path if old_path != target_path else None,
                change_type=change_type,  # type: ignore
                lines_added=lines_added,
                lines_removed=lines_removed,
                detected_symbols=detected_symbols[:10],
            )
        )

    # Prepare bounded diff sample for UI display
    raw_sample = diff_text[:4000]

    return ParsedDiff(
        total_files=len(parsed_files),
        lines_added=total_added,
        lines_removed=total_removed,
        files=parsed_files,
        raw_diff_sample=raw_sample,
        is_truncated=is_truncated,
        warnings=warnings,
    )


def evaluate_diff_roadmap_alignment(
    parsed_diff: ParsedDiff,
    planned_steps: Optional[list[ImplementationStep]] = None,
) -> tuple[str, list[str]]:
    """
    Cross-reference touched files in diff against planned M3 implementation steps.
    Identifies potentially unrelated files and summarizes roadmap alignment.
    Returns: (alignment_summary, potentially_unrelated_files)
    """
    if not planned_steps:
        return (
            "No prior implementation roadmap was supplied. Changes reviewed directly against repository context.",
            [],
        )

    planned_files: set[str] = set()
    for s in planned_steps:
        for f in s.files:
            planned_files.add(f.lower().strip())

    if not planned_files:
        return (
            "Implementation roadmap contained no explicit file targets.",
            [],
        )

    diff_files = [f.path for f in parsed_diff.files]
    matching_files = [f for f in diff_files if f.lower().strip() in planned_files]
    unrelated_files = [f for f in diff_files if f.lower().strip() not in planned_files]

    if not diff_files:
        return ("Diff contains no modified files.", [])

    match_pct = int((len(matching_files) / len(diff_files)) * 100)

    if match_pct == 100:
        summary = f"All {len(diff_files)} modified file(s) align directly with targets in the implementation roadmap."
    elif match_pct >= 50:
        summary = f"{len(matching_files)} of {len(diff_files)} modified file(s) ({match_pct}%) match planned roadmap targets. {len(unrelated_files)} file(s) appear outside the original scope."
    else:
        summary = f"Only {len(matching_files)} of {len(diff_files)} modified file(s) match planned roadmap targets. Review unrelated changes carefully before submitting."

    return summary, unrelated_files
