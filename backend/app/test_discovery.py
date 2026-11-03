"""Deterministic Test Discovery Engine for PatchLoom 2.0 (M4 VERIFY & CONTRIBUTE Pillar).

Identifies candidate test files and associated execution commands grounded strictly
in repository intelligence, file tree existence, and contributor diff changes.
"""

from datetime import datetime, timezone
import re
from typing import Optional

from app.schemas import (
    DiscoveredTest,
    ImplementationStep,
    IntelligenceEvidence,
    ModuleSummary,
    ParsedDiff,
    TestExecutionPlan,
    TestProfile,
)


def discover_relevant_tests(
    parsed_diff: ParsedDiff,
    file_tree: list[str],
    test_profile: Optional[TestProfile] = None,
    modules: Optional[list[ModuleSummary]] = None,
    planned_steps: Optional[list[ImplementationStep]] = None,
) -> tuple[list[DiscoveredTest], Optional[TestExecutionPlan]]:
    """
    Deterministically discover relevant test files corresponding to changed diff files.
    Grounded strictly in the verified repository file tree.
    Returns: (discovered_tests, suggested_execution_plan)
    """
    observed = datetime.now(timezone.utc).isoformat()
    tree_set = set(file_tree)
    discovered: list[DiscoveredTest] = []
    seen_test_paths: set[str] = set()

    # Determine default framework & command from test profile
    primary_framework = "pytest"
    default_cmd_prefix = "pytest"

    if test_profile and test_profile.frameworks:
        primary_framework = test_profile.frameworks[0]
        if primary_framework.lower() == "pytest":
            default_cmd_prefix = "pytest"
        elif primary_framework.lower() in ("vitest", "jest"):
            default_cmd_prefix = "npm test"
        elif primary_framework.lower() == "cargo test":
            default_cmd_prefix = "cargo test"
        elif primary_framework.lower() == "go test":
            default_cmd_prefix = "go test"
    elif any(f.endswith(".ts") or f.endswith(".js") for f in file_tree):
        primary_framework = "npm test"
        default_cmd_prefix = "npm test"

    # 1. Inspect direct changes in diff that are test files themselves
    for cf in parsed_diff.files:
        p = cf.path
        if p in tree_set and is_test_path(p):
            if p not in seen_test_paths:
                seen_test_paths.add(p)
                cmd = format_test_command(default_cmd_prefix, primary_framework, p)
                discovered.append(
                    DiscoveredTest(
                        test_file=p,
                        framework=primary_framework,
                        test_command=cmd,
                        confidence="high",
                        selection_rationale="This test file was directly created or modified in the contributor's diff.",
                        kind="verified",
                        target_module="tests",
                        evidence=IntelligenceEvidence(
                            status="verified",
                            source="diff_analysis",
                            observed_at=observed,
                            detail=f"Direct test file modification in diff ({cf.change_type}).",
                        ),
                    )
                )

    # 2. Match changed source files to candidate test files in repository tree
    for cf in parsed_diff.files:
        src_path = cf.path
        if is_test_path(src_path):
            continue

        base_name = src_path.split("/")[-1].split(".")[0]
        ext = src_path.split(".")[-1].lower() if "." in src_path else ""

        # Check common test naming conventions: test_<base>, <base>_test, <base>.test
        candidate_patterns = [
            f"test_{base_name}.{ext}",
            f"{base_name}_test.{ext}",
            f"{base_name}.test.{ext}",
            f"{base_name}.spec.{ext}",
        ]
        # Also check .py test for .py source, .ts test for .ts source
        if ext in ("ts", "tsx", "js", "jsx"):
            candidate_patterns.extend([
                f"{base_name}.test.ts",
                f"{base_name}.test.js",
                f"{base_name}.spec.ts",
                f"{base_name}.spec.js",
            ])

        for tree_path in file_tree:
            tree_fname = tree_path.split("/")[-1].lower()
            if any(tree_fname == cp.lower() for cp in candidate_patterns):
                if tree_path not in seen_test_paths:
                    seen_test_paths.add(tree_path)
                    cmd = format_test_command(default_cmd_prefix, primary_framework, tree_path)
                    discovered.append(
                        DiscoveredTest(
                            test_file=tree_path,
                            framework=primary_framework,
                            test_command=cmd,
                            confidence="high",
                            selection_rationale=f"Direct test counterpart for modified file '{src_path}'.",
                            kind="verified",
                            target_module=src_path.split("/")[0] if "/" in src_path else None,
                            evidence=IntelligenceEvidence(
                                status="verified",
                                source="repository_file_tree",
                                observed_at=observed,
                                detail=f"Found corresponding test file '{tree_path}' matching base name '{base_name}'.",
                            ),
                        )
                    )

    # 3. Check planned M3 roadmap test files
    if planned_steps:
        for s in planned_steps:
            for f in s.files:
                if is_test_path(f) and f in tree_set and f not in seen_test_paths:
                    seen_test_paths.add(f)
                    cmd = format_test_command(default_cmd_prefix, primary_framework, f)
                    discovered.append(
                        DiscoveredTest(
                            test_file=f,
                            framework=primary_framework,
                            test_command=cmd,
                            confidence="medium",
                            selection_rationale=f"Identified in implementation roadmap step: '{s.title}'.",
                            kind="candidate",
                            target_module=f.split("/")[0] if "/" in f else None,
                            evidence=IntelligenceEvidence(
                                status="inference",
                                source="m3_implementation_roadmap",
                                observed_at=observed,
                                detail=f"Step '{s.id}' referenced test target '{f}'.",
                            ),
                        )
                    )

    # 4. Fallback: If no direct test matched, locate general test files from test_profile
    if not discovered and test_profile and test_profile.test_directories:
        for d in test_profile.test_directories:
            matched_in_dir = [p for p in file_tree if p.startswith(d + "/") and is_test_path(p)]
            for t_path in matched_in_dir[:2]:
                if t_path not in seen_test_paths:
                    seen_test_paths.add(t_path)
                    cmd = format_test_command(default_cmd_prefix, primary_framework, t_path)
                    discovered.append(
                        DiscoveredTest(
                            test_file=t_path,
                            framework=primary_framework,
                            test_command=cmd,
                            confidence="low",
                            selection_rationale=f"General repository test in directory '{d}'.",
                            kind="candidate",
                            target_module=d,
                            evidence=IntelligenceEvidence(
                                status="inference",
                                source="test_profile_directory",
                                observed_at=observed,
                                detail=f"Test directory '{d}' contains candidate '{t_path}'.",
                            ),
                        )
                    )

    # Prepare suggested execution plan
    suggested_plan: Optional[TestExecutionPlan] = None
    if discovered:
        top_test = discovered[0]
        runner_id = primary_framework.lower().replace(" ", "_")
        cmd_parts = top_test.test_command.split()
        exec_cmd = cmd_parts[0] if cmd_parts else "pytest"
        exec_args = cmd_parts[1:] if len(cmd_parts) > 1 else [top_test.test_file]

        suggested_plan = TestExecutionPlan(
            test_runner=runner_id,
            command=exec_cmd,
            arguments=exec_args,
            working_dir=".",
            timeout_seconds=30,
            is_allowlisted=True,
            disclaimer="Execution runs in an isolated, network-disabled Docker container with dropped capabilities.",
        )
    elif test_profile and test_profile.likely_commands:
        raw_cmd = test_profile.likely_commands[0].split()[0]
        suggested_plan = TestExecutionPlan(
            test_runner=primary_framework.lower().replace(" ", "_"),
            command=raw_cmd,
            arguments=[],
            working_dir=".",
            timeout_seconds=30,
            is_allowlisted=True,
            disclaimer="Execution runs in an isolated, network-disabled Docker container with dropped capabilities.",
        )

    return discovered, suggested_plan


def is_test_path(path: str) -> bool:
    """Check if file path follows test conventions."""
    p_lower = path.lower()
    return bool(
        p_lower.startswith(("tests/", "test/", "spec/", "__tests__/"))
        or "/tests/" in p_lower
        or "/test/" in p_lower
        or p_lower.endswith(("_test.py", "test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js", "_test.go"))
    )


def format_test_command(cmd_prefix: str, framework: str, test_file: str) -> str:
    """Safely format test command string for display and planning."""
    fw_lower = framework.lower()
    if "pytest" in fw_lower:
        return f"pytest {test_file}"
    elif "vitest" in fw_lower:
        return f"npx vitest run {test_file}"
    elif "jest" in fw_lower:
        return f"npx jest {test_file}"
    elif "cargo" in fw_lower:
        return f"cargo test --test {test_file}"
    elif "go" in fw_lower:
        return f"go test ./{test_file}"
    return f"{cmd_prefix} {test_file}"
