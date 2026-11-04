"""Isolated Test Execution Boundary for PatchLoom 2.0 (M4 VERIFY & CONTRIBUTE Pillar).

CRITICAL SECURITY INVARIANTS:
1. Untrusted repository code is NEVER executed directly on the host machine.
2. All test execution is strictly isolated inside disposable, network-disabled,
   read-only, unprivileged Docker containers with dropped capabilities, bounded resources,
   and strict timeouts.
3. Base-executable matching is replaced by strict structured command validation.
   Arbitrary subcommands (e.g. npm install, npm run, python script.py, cargo run, go run)
   are rejected.
4. Shell metacharacters, interpreter execution flags (-c, -m, --eval, --import),
   configuration overrides (-o, --override-ini), and path traversal (../) are rejected.
5. If Docker daemon is unavailable, or a verified workspace cannot be safely constructed
   without out-of-scope repository cloning, the runner reports 'execution_unavailable'
   rather than falling back to simulated execution outside demo mode.
6. Unique deterministic container names are assigned and killed explicitly with 'docker kill'
   on timeout or cancellation, and forced removal with 'docker rm -f' in finally blocks.
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Optional
import uuid

from app.schemas import TestExecutionPlan, TestExecutionResult

logger = logging.getLogger(__name__)

# Bounded output limit for stdout/stderr (50 KB)
MAX_OUTPUT_CHARS = 50_000

# Prohibited shell injection metacharacters
PROHIBITED_CHARS = set(";&|`$><\n\r()\\*?!{}[]~^\"'\x00")

# Dangerous flag prefixes that allow arbitrary code execution or config overriding
DANGEROUS_FLAG_PREFIXES = (
    "-o",
    "--override-ini",
    "-c",
    "--eval",
    "-e",
    "--import",
    "--exec",
    "-r",
    "--require",
    "--inspect",
    "--target-dir",
    "-exec",
)

# Immutable supported runner configurations
# Note: Base container images are runtime environments, NOT pre-baked test runner images.
# Runners requiring unbundled third-party tooling (e.g. pytest, vitest, jest) are marked
# tooling_preinstalled=False and report execution_unavailable unless provisioned images are used.
SUPPORTED_RUNNER_CONFIGS: dict[str, dict] = {
    "pytest": {
        "mandatory_tokens": ["pytest"],
        "runtime_image": "python:3.13-slim",
        "tooling_preinstalled": False,
        "required_tooling": "pytest",
        "allowed_flags": {"-v", "-vv", "-q", "--quiet", "-s", "-x", "-l", "--show-capture=no"},
        "allowed_flag_prefixes": ("-k", "--tb="),
        "allowed_path_extensions": (".py",),
    },
    "python_pytest": {
        "mandatory_tokens": ["python", "-m", "pytest"],
        "runtime_image": "python:3.13-slim",
        "tooling_preinstalled": False,
        "required_tooling": "pytest",
        "allowed_flags": {"-v", "-vv", "-q", "--quiet", "-s", "-x", "-l", "--show-capture=no"},
        "allowed_flag_prefixes": ("-k", "--tb="),
        "allowed_path_extensions": (".py",),
    },
    "python_unittest": {
        "mandatory_tokens": ["python", "-m", "unittest"],
        "runtime_image": "python:3.13-slim",
        "tooling_preinstalled": True,  # Standard library module
        "required_tooling": "standard library unittest",
        "allowed_flags": {"-v", "-q", "-f", "-b"},
        "allowed_flag_prefixes": ("-k",),
        "allowed_path_extensions": (".py",),
    },
    "npm_test": {
        "mandatory_tokens": ["npm", "test"],
        "runtime_image": "node:22-alpine",
        "tooling_preinstalled": False,
        "required_tooling": "project node_modules",
        "allowed_flags": {"--"},
        "allowed_flag_prefixes": (),
        "allowed_path_extensions": (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"),
    },
    "vitest": {
        "mandatory_tokens": ["npx", "vitest", "run"],
        "runtime_image": "node:22-alpine",
        "tooling_preinstalled": False,
        "required_tooling": "vitest",
        "allowed_flags": {"--run", "--passWithNoTests"},
        "allowed_flag_prefixes": ("-t=", "-t"),
        "allowed_path_extensions": (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"),
    },
    "jest": {
        "mandatory_tokens": ["npx", "jest"],
        "runtime_image": "node:22-alpine",
        "tooling_preinstalled": False,
        "required_tooling": "jest",
        "allowed_flags": {"--runInBand", "--passWithNoTests"},
        "allowed_flag_prefixes": ("-t=", "-t"),
        "allowed_path_extensions": (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"),
    },
    "cargo_test": {
        "mandatory_tokens": ["cargo", "test"],
        "runtime_image": "rust:1.80-slim",
        "tooling_preinstalled": True,  # cargo pre-installed in rust image
        "required_tooling": "cargo",
        "allowed_flags": {"--lib", "--test"},
        "allowed_flag_prefixes": (),
        "allowed_path_extensions": (".rs",),
    },
    "go_test": {
        "mandatory_tokens": ["go", "test"],
        "runtime_image": "golang:1.23-alpine",
        "tooling_preinstalled": True,  # go pre-installed in golang image
        "required_tooling": "go",
        "allowed_flags": {"-v"},
        "allowed_flag_prefixes": ("-run=", "-run"),
        "allowed_path_extensions": (".go",),
    },
}

# Legacy mapping for backward-compatibility checks
SUPPORTED_RUNNERS = {
    k: v["mandatory_tokens"] for k, v in SUPPORTED_RUNNER_CONFIGS.items()
}


def tokenize_command(command: str, arguments: list[str]) -> list[str]:
    """Tokenize command string and arguments into discrete tokens."""
    cmd_tokens = [tok.strip() for tok in command.strip().split() if tok.strip()]
    arg_tokens = [str(a).strip() for a in arguments if str(a).strip()]
    return cmd_tokens + arg_tokens


def match_runner_config(all_tokens: list[str]) -> Optional[tuple[str, dict, list[str]]]:
    """
    Match tokens against SUPPORTED_RUNNER_CONFIGS.
    Returns: (runner_key, config, remaining_arguments) if valid, else None.
    """
    if not all_tokens:
        return None

    for runner_key, config in SUPPORTED_RUNNER_CONFIGS.items():
        mand = config["mandatory_tokens"]
        if len(all_tokens) >= len(mand):
            if all_tokens[: len(mand)] == mand:
                return runner_key, config, all_tokens[len(mand) :]
    return None


def is_safe_argument(arg: str, config: dict) -> bool:
    """Validate a single extra argument against strict runner safety rules."""
    # 1. Prohibited shell injection metacharacters
    if any(c in PROHIBITED_CHARS for c in arg):
        return False

    # Specific go test wildcard package
    if arg == "./..." and config["mandatory_tokens"][:2] == ["go", "test"]:
        return True

    # 2. Path traversal or absolute paths
    if ".." in arg or arg.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:", arg) or "://" in arg:
        return False

    # 3. Dangerous flag prefixes
    for df in DANGEROUS_FLAG_PREFIXES:
        if arg == df or arg.startswith(df + "=") or (df.startswith("-") and arg.startswith(df)):
            return False

    # 4. Allowed exact flags
    if arg in config["allowed_flags"]:
        return True

    # 5. Allowed flag prefixes
    for prefix in config["allowed_flag_prefixes"]:
        if arg == prefix or arg.startswith(prefix + "=") or arg.startswith(prefix):
            val = arg[len(prefix) :].lstrip("=")
            if re.match(r"^[A-Za-z0-9_.\-]+$", val):
                return True

    # 6. Safe relative test path or module selector
    if re.match(r"^(?:\./)?[A-Za-z0-9_./\-]+$", arg):
        if "." in arg:
            allowed_exts = config["allowed_path_extensions"]
            if any(arg.lower().endswith(ext) for ext in allowed_exts):
                return True
            return False
        return True

    return False


def is_command_allowlisted(command: str, arguments: list[str]) -> bool:
    """
    Validate command and arguments against the strict security allowlist.

    Requirements enforced:
    - Immutable supported runner configurations.
    - Exact executable and mandatory subcommand match (rejects npm install, npm run,
      python script.py, python -m http.server, cargo run, go run).
    - Rejection of shell metacharacters, path traversal, interpreter flags (-c, -m, --eval),
      and configuration overrides (-o, --override-ini).
    """
    all_tokens = tokenize_command(command, arguments)
    if not all_tokens:
        return False

    matched = match_runner_config(all_tokens)
    if not matched:
        return False

    _, config, remaining_args = matched
    for arg in remaining_args:
        if not is_safe_argument(arg, config):
            return False

    return True


def check_docker_availability() -> tuple[bool, str]:
    """
    Check if Docker CLI is installed and the Docker daemon is actively running.
    Returns: (is_available, diagnostic_message)
    """
    docker_path = shutil.which("docker")
    if not docker_path:
        return False, "Docker CLI executable was not found on system PATH."

    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            text=True,
            shell=False,
        )
        if proc.returncode == 0:
            return True, "Docker daemon is running and reachable."
        err_msg = proc.stderr.strip()[:200] or "Docker daemon is not running."
        return False, f"Docker daemon unreachable: {err_msg}"
    except (subprocess.TimeoutExpired, Exception) as exc:
        return False, f"Docker daemon check timed out or failed: {str(exc)}"


def validate_diff_content(diff_text: str) -> tuple[bool, str]:
    """Validate git diff text to prevent path traversal and unsafe file manipulations."""
    if len(diff_text) > MAX_OUTPUT_CHARS:
        return False, f"Diff size exceeds maximum permitted bound ({MAX_OUTPUT_CHARS} characters)."

    for line in diff_text.splitlines():
        if line.startswith(("--- ", "+++ ", "diff --git ")):
            if ".." in line:
                return False, "Diff headers contain forbidden path traversal ('..')."
            tokens = line.split()
            for tok in tokens[1:]:
                if tok in ("/dev/null", "dev/null"):
                    continue
                path_to_check = tok
                if tok.startswith(("a/", "b/")):
                    path_to_check = tok[2:]
                if (
                    path_to_check.startswith(("/", "\\"))
                    or re.match(r"^[a-zA-Z]:", path_to_check)
                    or tok.startswith(("/", "\\"))
                ):
                    return False, f"Diff headers contain forbidden absolute path: {tok}"
        if line.startswith("new file mode 120000"):
            return False, "Diff attempts to create a symbolic link (forbidden mode 120000)."

    return True, "Diff is safe."


def parse_test_counts(
    stdout: str, stderr: str
) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Extract total, passed, failed, and skipped test counts from runner output."""
    combined = stdout + "\n" + stderr
    total = None
    passed = None
    failed = None
    skipped = None

    # Pytest format: "=== 4 passed, 1 failed, 2 skipped in 0.12s ==="
    p_match = re.search(r"(\d+)\s+passed", combined)
    f_match = re.search(r"(\d+)\s+failed", combined)
    s_match = re.search(r"(\d+)\s+skipped", combined)

    if p_match or f_match or s_match:
        passed = int(p_match.group(1)) if p_match else 0
        failed = int(f_match.group(1)) if f_match else 0
        skipped = int(s_match.group(1)) if s_match else 0
        total = passed + failed + skipped
        return total, passed, failed, skipped

    # Vitest / Jest format: "Tests: 1 failed, 3 passed, 4 total"
    j_total = re.search(r"Tests:\s+.*?(\d+)\s+total", combined)
    j_passed = re.search(r"Tests:\s+.*?(\d+)\s+passed", combined)
    j_failed = re.search(r"Tests:\s+.*?(\d+)\s+failed", combined)

    if j_total or j_passed or j_failed:
        total = int(j_total.group(1)) if j_total else None
        passed = int(j_passed.group(1)) if j_passed else 0
        failed = int(j_failed.group(1)) if j_failed else 0
        return total, passed, failed, None

    # Go test format: "PASS" or "FAIL"
    if "PASS\nok" in combined:
        return 1, 1, 0, 0
    elif "FAIL\n" in combined:
        return 1, 0, 1, 0

    return None, None, None, None


def extract_failure_details(combined: str) -> tuple[list[str], list[str]]:
    """Extract failure messages and file locations from runner output."""
    failure_details: list[str] = []
    failure_locations: list[str] = []

    lines = combined.splitlines()
    for line in lines:
        if line.startswith("FAILED ") or line.startswith("FAIL "):
            failure_details.append(line.strip())
        elif line.startswith("E   ") or line.startswith("AssertionError"):
            if len(failure_details) < 10:
                failure_details.append(line.strip())

        loc_match = re.search(r"([A-Za-z0-9_\-\./]+\.py):(\d+):", line)
        if loc_match:
            loc = f"{loc_match.group(1)}#L{loc_match.group(2)}"
            if loc not in failure_locations:
                failure_locations.append(loc)

    return failure_details[:8], failure_locations[:8]


async def execute_isolated_test_plan(
    plan: TestExecutionPlan,
    diff_text: Optional[str] = None,
    authorized: bool = False,
    demo: bool = False,
    workspace_dir: Optional[str] = None,
) -> TestExecutionResult:
    """
    Execute an authorized test plan within an isolated Docker boundary.

    Enforces all Section 5 safeguards:
    - Rejects unauthorized requests at execution boundary.
    - Validates command allowlist and arguments against structured configurations.
    - In demo/fixture mode, returns simulated result.
    - Requires Docker daemon; never executes on host.
    - Refuses to execute against unconstructed/uncloned workspaces outside demo mode.
    - Runs containers with full security hardening (read-only, network none, cap-drop ALL, no-new-privileges).
    - Uses deterministic container name, targeted 'docker kill' on timeout, and 'docker rm -f' in finally.
    """
    observed = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()

    # 1. Verification of explicit contributor authorization
    if not authorized:
        return TestExecutionResult(
            status="invalid_or_unsupported",
            runner=plan.test_runner,
            command=plan.command,
            duration_seconds=0.0,
            stderr_bounded="Execution rejected: Explicit contributor authorization was not confirmed.",
            failure_details=["Missing authorized=True flag in execution request."],
        )

    # 2. Command Allowlist Validation
    if not is_command_allowlisted(plan.command, plan.arguments):
        return TestExecutionResult(
            status="invalid_or_unsupported",
            runner=plan.test_runner,
            command=plan.command,
            duration_seconds=0.0,
            stderr_bounded=f"Execution rejected: Command '{plan.command}' with arguments {plan.arguments} is not permitted by the test runner security allowlist.",
            failure_details=["Command validation failed against allowlist."],
        )

    # 3. Offline Demo / Fixture Mode
    if demo:
        sim_stdout = f"=== 3 passed in 0.42s ===\nRunning allowlisted command: {plan.command} {' '.join(plan.arguments)}"
        return TestExecutionResult(
            status="passed",
            runner=plan.test_runner,
            command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
            duration_seconds=0.42,
            exit_code=0,
            tests_total=3,
            tests_passed=3,
            tests_failed=0,
            tests_skipped=0,
            stdout_bounded=sim_stdout,
            stderr_bounded="",
            failure_details=[],
            failure_locations=[],
            ai_likely_causes=[],
            ai_suggested_next_steps=["All 3 discovered tests passed in simulated fixture mode."],
            simulated=True,
            executed_at=observed,
        )

    # 4. Check Docker Availability
    docker_available, diag_msg = check_docker_availability()
    if not docker_available:
        logger.warning("Docker isolation unavailable for test execution: %s", diag_msg)
        return TestExecutionResult(
            status="execution_unavailable",
            runner=plan.test_runner,
            command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
            duration_seconds=0.0,
            stderr_bounded=(
                "Isolated Docker execution environment is currently unavailable. "
                f"Diagnostic: {diag_msg}\n\n"
                "CRITICAL SECURITY NOTICE: To protect your host machine, PatchLoom NEVER "
                "executes untrusted repository code directly on the host machine."
            ),
            failure_details=[diag_msg],
            ai_likely_causes=[
                "Docker Desktop or the Docker daemon service is not started on the host machine.",
                "Container virtualization is disabled in host settings.",
            ],
            ai_suggested_next_steps=[
                "Start the Docker service locally if you wish to run isolated test verification.",
                "Review code review findings and regression analysis without local execution.",
            ],
            simulated=False,
            executed_at=observed,
        )

    # 5. Check Workspace Construction & Patch Validation
    if diff_text:
        is_safe_diff, diff_msg = validate_diff_content(diff_text)
        if not is_safe_diff:
            return TestExecutionResult(
                status="invalid_or_unsupported",
                runner=plan.test_runner,
                command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
                duration_seconds=0.0,
                stderr_bounded=f"Execution rejected: {diff_msg}",
                failure_details=[diff_msg],
                simulated=False,
                executed_at=observed,
            )

    # 6. Check Runner Tooling Availability in Base Runtime Image
    all_tokens = tokenize_command(plan.command, plan.arguments)
    matched = match_runner_config(all_tokens)
    if not matched:
        return TestExecutionResult(
            status="invalid_or_unsupported",
            runner=plan.test_runner,
            command=plan.command,
            duration_seconds=0.0,
            stderr_bounded=f"Execution rejected: Command '{plan.command}' is not supported.",
            failure_details=["Command validation failed against allowlist."],
        )

    runner_key, config, _ = matched
    is_provisioned = bool(
        workspace_dir
        and os.path.isdir(workspace_dir)
        and os.path.exists(os.path.join(workspace_dir, ".provisioned"))
    )

    if not config.get("tooling_preinstalled", False) and not is_provisioned:
        logger.info(
            "Runner '%s' requires '%s' not present in base runtime image '%s'.",
            runner_key,
            config["required_tooling"],
            config["runtime_image"],
        )
        return TestExecutionResult(
            status="execution_unavailable",
            runner=plan.test_runner,
            command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
            duration_seconds=0.0,
            stderr_bounded=(
                f"Execution unavailable: Test runner '{plan.test_runner}' requires '{config['required_tooling']}', "
                f"which is not pre-installed in the base runtime image '{config['runtime_image']}'. "
                "Base container runtime images do not include third-party test frameworks, and network isolation "
                "(--network none) prevents runtime package installation (e.g. pip/npm). "
                "A provisioned runner image with pre-installed test tooling is required for container execution."
            ),
            failure_details=[
                f"Required test runner tooling '{config['required_tooling']}' is absent from runtime image '{config['runtime_image']}'."
            ],
            ai_likely_causes=[
                f"Base runtime image '{config['runtime_image']}' does not bundle third-party package '{config['required_tooling']}'.",
                "PatchLoom network isolation (--network none) strictly disables runtime dependency fetching.",
            ],
            ai_suggested_next_steps=[
                "Use fixture demo mode (demo=true) to review verified test verification workflows.",
                "Review static code review findings, regression analysis, and draft PR notes.",
            ],
            simulated=False,
            executed_at=observed,
        )

    # In PatchLoom, arbitrary repository cloning and dependency installation are out of scope.
    # If no pre-prepared workspace directory is provided, report execution_unavailable honestly.
    if not workspace_dir or not os.path.isdir(workspace_dir):
        logger.info("No prepared repository workspace provided for execution. Reporting execution_unavailable.")
        return TestExecutionResult(
            status="execution_unavailable",
            runner=plan.test_runner,
            command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
            duration_seconds=0.0,
            stderr_bounded=(
                "Execution unavailable: Isolated test runner requires a prepared repository workspace, "
                "which is not available without full repository cloning (out of scope for PatchLoom)."
            ),
            failure_details=["Prepared repository workspace is unavailable without cloning."],
            ai_likely_causes=[
                "PatchLoom operates statelessly without cloning untrusted repositories to the host.",
                "Running test suites in isolated containers requires local project files.",
            ],
            ai_suggested_next_steps=[
                "Use fixture demo mode (demo=true) to review verified test workflows.",
                "Review code review findings, regression risks, and draft PR guidance.",
            ],
            simulated=False,
            executed_at=observed,
        )

    # 7. Docker Execution in Disposable Container
    image = config.get("runtime_image", "python:3.13-slim")

    container_name = f"patchloom_test_{uuid.uuid4().hex[:12]}"
    temp_dir = tempfile.mkdtemp(prefix="patchloom_ws_")

    try:
        # If diff is provided, safely write it to the disposable scratch space
        if diff_text:
            diff_file = os.path.join(temp_dir, "change.patch")
            with open(diff_file, "w", encoding="utf-8") as f:
                f.write(diff_text[:MAX_OUTPUT_CHARS])

        # Assemble full docker run command with all 12 hardening flags
        docker_cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "--rm",
            "--read-only",
            "--security-opt",
            "no-new-privileges:true",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "-u",
            "10001:10001",
            "--cpus=1.0",
            "--memory=512m",
            "--memory-swap=512m",
            "--pids-limit=64",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-v",
            f"{workspace_dir}:/workspace:ro",
            "-w",
            "/workspace",
            image,
        ] + all_tokens

        timeout_sec = max(5, min(plan.timeout_seconds, 60))

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_sec,
            )
            duration = round(time.monotonic() - start_time, 2)
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]
            exit_code = proc.returncode

            total, passed, failed, skipped = parse_test_counts(stdout_str, stderr_str)
            fail_details, fail_locs = extract_failure_details(stdout_str + "\n" + stderr_str)

            status = "passed" if exit_code == 0 else "failed"

            return TestExecutionResult(
                status=status,
                runner=plan.test_runner,
                command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
                duration_seconds=duration,
                exit_code=exit_code,
                tests_total=total,
                tests_passed=passed,
                tests_failed=failed,
                tests_skipped=skipped,
                stdout_bounded=stdout_str,
                stderr_bounded=stderr_str,
                failure_details=fail_details,
                failure_locations=fail_locs,
                simulated=False,
                executed_at=observed,
            )

        except asyncio.TimeoutError:
            # Terminate host CLI process
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

            # Explicit docker kill on running container
            try:
                kill_proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "kill",
                    container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(kill_proc.communicate(), timeout=5.0)
            except Exception as kill_err:
                logger.warning("Failed to docker kill container %s: %s", container_name, kill_err)

            duration = round(time.monotonic() - start_time, 2)
            return TestExecutionResult(
                status="timed_out",
                runner=plan.test_runner,
                command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
                duration_seconds=duration,
                exit_code=None,
                stderr_bounded=f"Execution timed out after {timeout_sec} seconds. Container {container_name} was killed.",
                failure_details=[f"Process exceeded maximum time limit ({timeout_sec}s)."],
                simulated=False,
                executed_at=observed,
            )

        except asyncio.CancelledError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            try:
                kill_proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "kill",
                    container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(kill_proc.communicate(), timeout=5.0)
            except Exception:
                pass
            raise

    except Exception as exc:
        duration = round(time.monotonic() - start_time, 2)
        logger.error("Error invoking Docker test container: %s", exc)
        return TestExecutionResult(
            status="error",
            runner=plan.test_runner,
            command=f"{plan.command} {' '.join(plan.arguments)}".strip(),
            duration_seconds=duration,
            exit_code=None,
            stderr_bounded=f"Container execution error: {str(exc)}",
            failure_details=[str(exc)],
            simulated=False,
            executed_at=observed,
        )

    finally:
        # Forced container cleanup
        try:
            rm_proc = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(rm_proc.communicate(), timeout=5.0)
        except Exception:
            pass

        # Cleanup temporary scratch directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
