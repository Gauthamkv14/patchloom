"""Deterministic Repository Intelligence Engine for PatchLoom 2.0 (UNDERSTAND Pillar).

Examines ingested repository structure, file tree, documentation, and candidate issues
to produce structured, evidence-backed intelligence reports with zero required AI calls.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import os
import re
from typing import Any, Optional

from app.prompts import sanitize_untrusted_text
from app.schemas import (
    DocFileSummary,
    DocSectionSummary,
    DocumentationProfile,
    EntryPoint,
    IntelligenceEvidence,
    IssueCandidateMapping,
    IssueToModuleMapping,
    LanguageDistribution,
    ModuleSummary,
    RepositoryIntelligenceReport,
    SignalEvidence,
    TechnologyItem,
    TestProfile,
)

# -------------------------------------------------------------
# Classification & Pattern Constants
# -------------------------------------------------------------

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SASS",
    ".sql": "SQL",
    ".proto": "Protocol Buffers",
}

MANIFEST_FILES: dict[str, tuple[str, str]] = {
    "requirements.txt": ("pip", "Python"),
    "pyproject.toml": ("pip/poetry/flit", "Python"),
    "setup.py": ("setuptools", "Python"),
    "setup.cfg": ("setuptools", "Python"),
    "pipfile": ("pipenv", "Python"),
    "package.json": ("npm/yarn/pnpm", "Node.js / JavaScript"),
    "cargo.toml": ("cargo", "Rust"),
    "go.mod": ("go modules", "Go"),
    "pom.xml": ("maven", "Java"),
    "build.gradle": ("gradle", "Java / Kotlin"),
    "build.gradle.kts": ("gradle", "Kotlin"),
    "gemfile": ("bundler", "Ruby"),
    "composer.json": ("composer", "PHP"),
}

CONFIG_FILES: dict[str, tuple[str, str]] = {
    "tsconfig.json": ("TypeScript Configuration", "tool"),
    "vite.config.ts": ("Vite Bundler", "bundler"),
    "vite.config.js": ("Vite Bundler", "bundler"),
    "webpack.config.js": ("Webpack Bundler", "bundler"),
    "tailwind.config.js": ("Tailwind CSS", "framework"),
    "tailwind.config.ts": ("Tailwind CSS", "framework"),
    "next.config.js": ("Next.js Configuration", "framework"),
    "next.config.mjs": ("Next.js Configuration", "framework"),
    "next.config.ts": ("Next.js Configuration", "framework"),
    "pytest.ini": ("Pytest Configuration", "test_framework"),
    "tox.ini": ("Tox Test Environment", "test_framework"),
    ".coveragerc": ("Coverage Configuration", "test_framework"),
    "jest.config.js": ("Jest Configuration", "test_framework"),
    "jest.config.ts": ("Jest Configuration", "test_framework"),
    "vitest.config.ts": ("Vitest Configuration", "test_framework"),
    "dockerfile": ("Docker Container", "tool"),
    "docker-compose.yml": ("Docker Compose Orchestration", "tool"),
    "docker-compose.yaml": ("Docker Compose Orchestration", "tool"),
    ".dockerignore": ("Docker Ignore", "tool"),
    "makefile": ("Make Build Automation", "tool"),
    "nginx.conf": ("Nginx Web Server", "tool"),
}

TECHNOLOGY_SIGNATURES: list[dict[str, Any]] = [
    {
        "name": "FastAPI",
        "category": "framework",
        "file_patterns": [r"main\.py$", r"api\.py$"],
        "content_patterns": [r"\bfrom fastapi import\b", r"\bFastAPI\("],
        "manifest_hints": ["fastapi"],
    },
    {
        "name": "Flask",
        "category": "framework",
        "file_patterns": [r"app\.py$", r"wsgi\.py$"],
        "content_patterns": [r"\bfrom flask import\b", r"\bFlask\("],
        "manifest_hints": ["flask"],
    },
    {
        "name": "Django",
        "category": "framework",
        "file_patterns": [r"manage\.py$", r"settings\.py$", r"urls\.py$"],
        "content_patterns": [r"\bdjango\b"],
        "manifest_hints": ["django"],
    },
    {
        "name": "React",
        "category": "framework",
        "file_patterns": [r"\.tsx$", r"\.jsx$", r"App\.tsx$", r"App\.jsx$"],
        "content_patterns": [r"\bfrom ['\"]react['\"]", r"\bimport React\b"],
        "manifest_hints": ["react", "react-dom"],
    },
    {
        "name": "Vue.js",
        "category": "framework",
        "file_patterns": [r"\.vue$"],
        "content_patterns": [r"\bfrom ['\"]vue['\"]"],
        "manifest_hints": ["vue"],
    },
    {
        "name": "Express",
        "category": "framework",
        "file_patterns": [r"server\.js$", r"app\.js$"],
        "content_patterns": [r"\brequire\(['\"]express['\"]\)", r"\bfrom ['\"]express['\"]"],
        "manifest_hints": ["express"],
    },
    {
        "name": "Pydantic",
        "category": "library",
        "file_patterns": [r"schemas\.py$", r"models\.py$"],
        "content_patterns": [r"\bfrom pydantic import\b", r"\bBaseModel\b"],
        "manifest_hints": ["pydantic"],
    },
    {
        "name": "Docker",
        "category": "tool",
        "file_patterns": [r"Dockerfile$", r"docker-compose\.ya?ml$", r"\.dockerignore$"],
        "content_patterns": [r"\bFROM \w+", r"\bservices:"],
        "manifest_hints": [],
    },
    {
        "name": "Pytest",
        "category": "test_framework",
        "file_patterns": [r"pytest\.ini$", r"test_.*\.py$", r".*_test\.py$"],
        "content_patterns": [r"\bimport pytest\b", r"@pytest\."],
        "manifest_hints": ["pytest"],
    },
    {
        "name": "Vite",
        "category": "bundler",
        "file_patterns": [r"vite\.config\.(ts|js|mjs)$"],
        "content_patterns": [r"\bdefineConfig\b"],
        "manifest_hints": ["vite"],
    },
    {
        "name": "TypeScript",
        "category": "tool",
        "file_patterns": [r"tsconfig.*\.json$", r"\.tsx?$" ],
        "content_patterns": [],
        "manifest_hints": ["typescript"],
    },
]

COMMON_TEST_DIRS = {
    "tests",
    "test",
    "__tests__",
    "spec",
    "specs",
    "testing",
    "backend/tests",
    "frontend/tests",
    "src/tests",
    "app/tests",
}

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off",
    "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "s", "same", "she", "should", "so", "some", "such", "t", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself",
}


# -------------------------------------------------------------
# 1. Language & Project Type Detection
# -------------------------------------------------------------


def analyze_languages_and_project_type(
    file_tree: list[str],
    github_languages: list[str],
) -> tuple[LanguageDistribution, str, str, str]:
    """
    Deterministically identify primary and secondary languages and classify project type.

    Returns:
      (languages_dist, project_type, project_type_rationale, structure_type)
    """
    ext_counter: Counter[str] = Counter()
    for path in file_tree:
        _, ext = os.path.splitext(path.lower())
        if ext in LANGUAGE_EXTENSIONS:
            ext_counter[LANGUAGE_EXTENSIONS[ext]] += 1

    sorted_by_ext = [lang for lang, _ in ext_counter.most_common()]

    # Blend GitHub reported languages (byte-based) with file extension counts
    ordered_langs: list[str] = []
    for lang in github_languages:
        if lang not in ordered_langs:
            ordered_langs.append(lang)
    for lang in sorted_by_ext:
        if lang not in ordered_langs:
            ordered_langs.append(lang)

    primary_lang = ordered_langs[0] if ordered_langs else None
    secondary_langs = ordered_langs[1:5] if len(ordered_langs) > 1 else []

    lang_dist = LanguageDistribution(
        primary=primary_lang,
        secondary=secondary_langs,
        source="github_languages_and_tree",
    )

    # Repository structure analysis
    root_dirs = {p.split("/")[0].lower() for p in file_tree if "/" in p}
    has_packages = "packages" in root_dirs or "apps" in root_dirs
    has_dual_roots = ("backend" in root_dirs and "frontend" in root_dirs) or (
        "client" in root_dirs and "server" in root_dirs
    )

    if has_packages or any("pnpm-workspace.yaml" in p.lower() for p in file_tree):
        structure_type = "monorepo"
    elif has_dual_roots:
        structure_type = "multi_module"
    elif "src" in root_dirs or "app" in root_dirs or "lib" in root_dirs:
        structure_type = "single_package"
    else:
        structure_type = "standard_flat"

    # Project type classification
    all_lower_paths = [p.lower() for p in file_tree]
    has_frontend = any(
        ext in p for p in all_lower_paths for ext in (".tsx", ".jsx", ".vue", ".html")
    ) and any("index.html" in p or "app.tsx" in p or "main.tsx" in p for p in all_lower_paths)

    has_backend = any(
        k in p
        for p in all_lower_paths
        for k in (
            "api.py", "main.py", "app.py", "server.js", "server.ts", "routes.py", "routes/", "controllers/"
        )
    )

    has_cli = any(
        k in p
        for p in all_lower_paths
        for k in ("cli.py", "bin/", "cmd/", "commands/")
    )

    has_library_manifest = any(
        p in ("setup.py", "pyproject.toml", "cargo.toml") for p in all_lower_paths
    )

    if structure_type == "monorepo" or (has_frontend and has_backend and has_dual_roots):
        project_type = "monorepo"
        rationale = "Multi-module/monorepo structure with separated frontend and backend or multiple package roots."
    elif has_frontend and has_backend:
        project_type = "web_application"
        rationale = "Full-stack web application with detected frontend UI views and backend server/API endpoints."
    elif has_backend:
        project_type = "api_service"
        rationale = "Backend service or API server with routing/endpoint definitions and no primary frontend bundle."
    elif has_cli:
        project_type = "cli_tool"
        rationale = "Command-line tool containing dedicated CLI entry points or command dispatch definitions."
    elif has_library_manifest or "src" in root_dirs or "lib" in root_dirs:
        project_type = "library_or_sdk"
        rationale = "Software library or SDK exporting modular interfaces for third-party integration."
    elif all(p.endswith((".md", ".rst", ".txt", ".png", ".jpg")) for p in all_lower_paths):
        project_type = "documentation_or_static"
        rationale = "Documentation repository or static assets container."
    else:
        project_type = "other"
        rationale = "General purpose codebase with mixed configuration and source components."

    return lang_dist, project_type, rationale, structure_type


# -------------------------------------------------------------
# 2. Technology & Manifest Detection
# -------------------------------------------------------------


def analyze_technologies_and_manifests(
    file_tree: list[str],
    docs_text: str = "",
) -> tuple[list[TechnologyItem], list[str], list[str], list[str]]:
    """
    Deterministically identify installed technologies, package managers, and configuration files.

    Returns:
      (technologies, package_managers, manifest_files, configuration_files)
    """
    observed = datetime.now(timezone.utc).isoformat()
    package_managers: set[str] = set()
    manifest_files: list[str] = []
    config_files: list[str] = []
    technologies: list[TechnologyItem] = []
    seen_tech_names: set[str] = set()

    file_tree_lower = [p.lower() for p in file_tree]
    filename_to_path: dict[str, list[str]] = defaultdict(list)
    for p in file_tree:
        fname = p.lower().split("/")[-1]
        filename_to_path[fname].append(p)

    # 1. Inspect manifests and package managers
    for manifest_name, (pm_name, ecosystem) in MANIFEST_FILES.items():
        if manifest_name in filename_to_path:
            matched_paths = filename_to_path[manifest_name]
            manifest_files.extend(matched_paths)
            for pm in pm_name.split("/"):
                package_managers.add(pm.strip())

    # 2. Inspect project configuration files
    for config_name, (config_desc, category) in CONFIG_FILES.items():
        if config_name in filename_to_path:
            matched_paths = filename_to_path[config_name]
            config_files.extend(matched_paths)

    # 3. Match technology signatures using file patterns and document hints
    docs_lower = docs_text.lower()

    for sig in TECHNOLOGY_SIGNATURES:
        name = sig["name"]
        category = sig["category"]
        matched_paths: list[str] = []

        # Check file pattern matches
        for pattern in sig["file_patterns"]:
            regex = re.compile(pattern, re.IGNORECASE)
            for path in file_tree:
                if regex.search(path):
                    matched_paths.append(path)

        # Check documentation / manifest text hints
        has_doc_hint = any(h in docs_lower for h in sig["manifest_hints"]) if sig["manifest_hints"] else False
        has_file_matches = len(matched_paths) > 0

        if has_file_matches or (has_doc_hint and len(sig["manifest_hints"]) > 0):
            if name not in seen_tech_names:
                seen_tech_names.add(name)
                evidence_detail = (
                    f"Matched {len(matched_paths)} path(s) in repository tree"
                    if matched_paths
                    else f"Referenced in repository documentation and manifests: {', '.join(sig['manifest_hints'])}"
                )
                technologies.append(
                    TechnologyItem(
                        name=name,
                        category=category,
                        evidence=IntelligenceEvidence(
                            status="verified" if has_file_matches else "inference",
                            source="file_tree_pattern" if has_file_matches else "documentation_heuristic",
                            observed_at=observed,
                            detail=evidence_detail,
                        ),
                        matched_paths=matched_paths[:8],
                    )
                )

    return (
        technologies,
        sorted(package_managers),
        sorted(list(set(manifest_files))),
        sorted(list(set(config_files))),
    )


# -------------------------------------------------------------
# 3. Important Files & Entry Points Detection
# -------------------------------------------------------------


def analyze_entry_points(file_tree: list[str]) -> list[EntryPoint]:
    """
    Identify key repository entry points and explain why each was identified.
    Distinguishes detected direct entry points from heuristic candidate files.
    """
    observed = datetime.now(timezone.utc).isoformat()
    entry_points: list[EntryPoint] = []
    seen_paths: set[str] = set()

    def add_entry(
        path: str,
        kind: str,
        confidence: str,
        reason: str,
        source: str = "standard_entrypoint_pattern",
    ):
        if path not in seen_paths and path in file_tree:
            seen_paths.add(path)
            entry_points.append(
                EntryPoint(
                    path=path,
                    kind=kind,  # type: ignore
                    confidence=confidence,  # type: ignore
                    reason=reason,
                    evidence=IntelligenceEvidence(
                        status="verified" if confidence == "detected" else "inference",
                        source=source,
                        observed_at=observed,
                        detail=reason,
                    ),
                )
            )

    # 1. Backend / Application entrypoints
    for path in file_tree:
        lower = path.lower()
        parts = lower.split("/")
        filename = parts[-1]

        # Direct application roots and subpackage main entrypoints
        if filename in ("main.py", "app.py", "server.js", "server.ts", "index.ts", "index.js", "lib.rs", "main.rs", "main.go"):
            if len(parts) == 1:
                add_entry(path, "application", "detected", f"Primary root application executable entry point ({path}).")
            elif any(part in parts for part in ("src", "backend", "app", "cmd", "server")):
                add_entry(path, "backend" if filename.endswith((".py", ".go", ".rs")) else "frontend", "detected", f"Backend service entry point and application initialization ({path}).")
            else:
                add_entry(path, "application", "candidate", f"Potential application entry point ({path}).")
        elif lower in ("frontend/src/main.tsx", "frontend/src/app.tsx", "src/main.tsx", "src/app.tsx", "frontend/index.html", "index.html"):
            add_entry(path, "frontend", "detected", f"Frontend client interface root entry point ({path}).")
        elif lower in ("cli.py", "app/cli.py", "src/cli.py") or filename == "cli.py":
            add_entry(path, "cli", "detected", f"Command-line interface dispatcher and commands root ({path}).")
        elif lower in ("src/__init__.py", "app/__init__.py") or (lower.endswith("/__init__.py") and len(parts) == 2):
            add_entry(path, "library", "detected", f"Primary package export root defining the module interface ({path}).")
        elif lower.endswith("/__init__.py"):
            add_entry(path, "library", "candidate", f"Top-level subpackage interface module ({path}).")

    # 2. Manifests & Configurations
    for path in file_tree:
        lower = path.lower()
        filename = lower.split("/")[-1]
        if filename in ("package.json", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod"):
            add_entry(path, "manifest", "detected", f"Core dependency manifest defining project dependencies ({path}).")
        elif filename in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "makefile"):
            add_entry(path, "build_deployment", "detected", f"Build automation and deployment environment configuration ({path}).")
        elif filename in ("tsconfig.json", "vite.config.ts", "vite.config.js"):
            add_entry(path, "configuration", "detected", f"Build-time project toolchain configuration ({path}).")
        elif filename in ("readme.md", "contributing.md"):
            add_entry(path, "documentation", "detected", f"Authoritative repository documentation ({path}).")

    return entry_points[:15]


# -------------------------------------------------------------
# 4. Test Intelligence
# -------------------------------------------------------------


def analyze_test_profile(
    file_tree: list[str],
    docs_text: str = "",
    ci_evidence: Optional[SignalEvidence] = None,
    is_truncated: bool = False,
) -> TestProfile:
    """
    Analyze testing infrastructure, framework detection, and test commands.
    Strictly distinguishes detected, not_detected, and unknown states.
    Never claims tests pass.
    """
    observed = datetime.now(timezone.utc).isoformat()
    test_dirs: set[str] = set()
    test_files: list[str] = []
    test_configs: list[str] = []
    frameworks: set[str] = set()
    likely_commands: list[str] = []
    limitations: list[str] = [
        "Tests were not executed; test pass/fail status cannot be claimed.",
        "Analysis reflects static repository configuration and file patterns only.",
    ]

    # Inspect file tree for test files and directories
    test_file_regex = re.compile(
        r"(^|/)(test_[^/]+\.py|[^/]+_test\.py|[^/]+\.test\.(ts|tsx|js|jsx)|[^/]+\.spec\.(ts|tsx|js|jsx)|[^/]+_test\.go)$",
        re.IGNORECASE,
    )

    for path in file_tree:
        lower = path.lower()
        parts = lower.split("/")

        # Check for test directory
        for idx, part in enumerate(parts):
            if part in COMMON_TEST_DIRS:
                test_dirs.add("/".join(path.split("/")[: idx + 1]))
                break

        # Check for test files
        if test_file_regex.search(lower):
            test_files.append(path)

        # Check for test configurations
        fname = parts[-1]
        if fname in ("pytest.ini", "tox.ini", ".coveragerc", "jest.config.js", "jest.config.ts", "vitest.config.ts"):
            test_configs.append(path)
            if "pytest" in fname or "tox" in fname:
                frameworks.add("pytest")
            elif "jest" in fname:
                frameworks.add("Jest")
            elif "vitest" in fname:
                frameworks.add("Vitest")

    # Detect test frameworks from documentation and file patterns
    docs_lower = docs_text.lower()
    if any(p.endswith(".py") for p in test_files) or "pytest" in docs_lower:
        frameworks.add("pytest")
        likely_commands.append("pytest")
    if any(p.endswith((".ts", ".tsx", ".js", ".jsx")) for p in test_files) or "npm test" in docs_lower:
        if "vitest" in docs_lower or any("vitest" in c for c in test_configs):
            frameworks.add("Vitest")
            likely_commands.append("npm run test")
        elif "jest" in docs_lower or any("jest" in c for c in test_configs):
            frameworks.add("Jest")
            likely_commands.append("npm test")
        else:
            likely_commands.append("npm test")
    if any(p.endswith("_test.go") for p in test_files):
        frameworks.add("go test")
        likely_commands.append("go test ./...")
    if any("cargo" in p.lower() for p in file_tree) and any("tests/" in p.lower() for p in file_tree):
        frameworks.add("cargo test")
        likely_commands.append("cargo test")

    has_test_artifacts = len(test_dirs) > 0 or len(test_files) > 0 or len(frameworks) > 0

    if has_test_artifacts:
        status = "detected"
        detail = (
            f"Detected {len(test_files)} test file(s) across {len(test_dirs)} test directory/directories "
            f"with framework(s): {', '.join(sorted(frameworks)) if frameworks else 'Unspecified test suite'}."
        )
    elif is_truncated:
        status = "unknown"
        detail = "Repository tree was truncated due to scale bounds; test infrastructure could not be fully verified."
        limitations.append("File tree truncation prevented exhaustive search for test directories.")
    else:
        status = "not_detected"
        detail = "No test directories, test configuration files, or test suites detected in inspected repository tree."

    evidence = IntelligenceEvidence(
        status="verified" if status == "detected" else ("unknown" if status == "unknown" else "inference"),
        source="github_git_tree_and_docs",
        observed_at=observed,
        detail=detail,
    )

    return TestProfile(
        status=status,  # type: ignore
        test_directories=sorted(list(test_dirs)),
        test_file_count=len(test_files),
        frameworks=sorted(list(frameworks)),
        configuration_files=sorted(test_configs),
        ci_configuration=ci_evidence,
        likely_commands=sorted(list(set(likely_commands)))[:4],
        evidence=evidence,
        limitations=limitations,
    )


# -------------------------------------------------------------
# 5. Documentation Intelligence
# -------------------------------------------------------------


def extract_shell_commands(text: str) -> list[str]:
    """Extract bounded shell command examples from documentation code blocks and inline spans."""
    commands: list[str] = []
    # Match markdown code fences
    fence_pattern = re.compile(r"```(?:bash|sh|shell|console)?\s*([\s\S]*?)```", re.IGNORECASE)
    for match in fence_pattern.finditer(text):
        block = match.group(1)
        for line in block.splitlines():
            line_str = line.strip()
            # Strip prompt symbols ($ or >)
            line_clean = re.sub(r"^[\$>] ", "", line_str).strip()
            if line_clean and any(
                line_clean.startswith(prefix)
                for prefix in ("pip ", "npm ", "yarn ", "pnpm ", "cargo ", "pytest", "make ", "docker ", "python ")
            ):
                if line_clean not in commands:
                    commands.append(line_clean[:80])
            if len(commands) >= 5:
                break

    # Match inline code spans
    if len(commands) < 5:
        inline_pattern = re.compile(r"`([^`\n]+)`")
        for match in inline_pattern.finditer(text):
            candidate = match.group(1).strip()
            candidate_clean = re.sub(r"^[\$>] ", "", candidate).strip()
            if candidate_clean and any(
                candidate_clean.startswith(prefix)
                for prefix in ("pip ", "npm ", "yarn ", "pnpm ", "cargo ", "pytest", "make ", "docker ", "python ")
            ):
                if candidate_clean not in commands:
                    commands.append(candidate_clean[:80])
            if len(commands) >= 5:
                break

    return commands


def analyze_documentation_profile(
    docs_dict: dict[str, Any],
    file_tree: list[str],
) -> DocumentationProfile:
    """
    Extract bounded, structured intelligence from repository documentation.
    Defensively sanitizes untrusted markdown and preserves verified vs inferred provenance.
    """
    observed = datetime.now(timezone.utc).isoformat()
    readme_text = docs_dict.get("readme_excerpt", "") or ""
    contrib_text = docs_dict.get("contributing_excerpt", "") or ""

    doc_files: list[DocFileSummary] = []

    # 1. Inspect README
    readme_purpose = None
    readme_setup_cmds: list[str] = []
    readme_test_cmds: list[str] = []
    readme_sections: list[DocSectionSummary] = []

    if docs_dict.get("has_readme"):
        readme_setup_cmds = extract_shell_commands(readme_text)
        readme_test_cmds = [c for c in readme_setup_cmds if any(k in c.lower() for k in ("test", "pytest", "spec"))]
        # Extract purpose from first non-header, non-badge paragraph
        lines = [line.strip() for line in readme_text.splitlines() if line.strip()]
        for line in lines:
            if line.startswith("#") or line.startswith("[!") or line.startswith("<") or line.startswith("["):
                continue
            if len(line) > 25:
                readme_purpose = sanitize_untrusted_text(line[:300])
                break

        # Extract sections by heading
        heading_matches = re.finditer(r"^(#{1,3})\s+(.+)$", readme_text, re.MULTILINE)
        headings = [(m.group(2).strip(), m.start()) for m in heading_matches]
        for idx, (h_title, pos) in enumerate(headings[:5]):
            next_pos = headings[idx + 1][1] if idx + 1 < len(headings) else len(readme_text)
            section_content = sanitize_untrusted_text(readme_text[pos:next_pos][:400].strip())
            h_lower = h_title.lower()
            if any(k in h_lower for k in ("setup", "install", "getting started", "quickstart")):
                cat = "setup"
            elif any(k in h_lower for k in ("test", "testing")):
                cat = "testing"
            elif any(k in h_lower for k in ("contribute", "contributing")):
                cat = "contributing"
            elif any(k in h_lower for k in ("architecture", "design", "overview")):
                cat = "architecture"
            else:
                cat = "purpose" if idx == 0 else "other"

            readme_sections.append(
                DocSectionSummary(
                    heading=h_title[:60],
                    content_excerpt=section_content,
                    category=cat,  # type: ignore
                )
            )

        doc_files.append(
            DocFileSummary(
                path="README.md",
                doc_type="readme",
                exists=True,
                key_sections=readme_sections,
                extracted_purpose=readme_purpose,
                setup_commands=readme_setup_cmds,
                test_commands=readme_test_cmds,
                evidence=IntelligenceEvidence(
                    status="verified",
                    source="github_repo_readme",
                    observed_at=observed,
                    detail="Ingested and parsed repository README.md excerpt.",
                ),
            )
        )

    # 2. Inspect CONTRIBUTING
    if docs_dict.get("has_contributing"):
        contrib_cmds = extract_shell_commands(contrib_text)
        doc_files.append(
            DocFileSummary(
                path="CONTRIBUTING.md",
                doc_type="contributing",
                exists=True,
                key_sections=[],
                extracted_purpose="Contribution workflow and guidelines for pull requests.",
                setup_commands=[c for c in contrib_cmds if "install" in c or "setup" in c],
                test_commands=[c for c in contrib_cmds if "test" in c],
                evidence=IntelligenceEvidence(
                    status="verified",
                    source="github_repo_contributing",
                    observed_at=observed,
                    detail="Ingested repository CONTRIBUTING guide.",
                ),
            )
        )

    # 3. Identify additional architecture or setup docs present in tree
    for path in file_tree:
        lower = path.lower()
        if lower in ("docs/architecture.md", "architecture.md", "docs/design.md"):
            doc_files.append(
                DocFileSummary(
                    path=path,
                    doc_type="architecture",
                    exists=True,
                    key_sections=[],
                    extracted_purpose="System architecture, component diagrams, and technical boundaries.",
                    setup_commands=[],
                    test_commands=[],
                    evidence=IntelligenceEvidence(
                        status="verified",
                        source="file_tree_discovery",
                        observed_at=observed,
                        detail=f"Architecture documentation located at {path}.",
                    ),
                )
            )
        elif lower in ("docs/setup.md", "docs/development.md", "development.md"):
            doc_files.append(
                DocFileSummary(
                    path=path,
                    doc_type="setup",
                    exists=True,
                    key_sections=[],
                    extracted_purpose="Local environment installation and developer setup instructions.",
                    setup_commands=[],
                    test_commands=[],
                    evidence=IntelligenceEvidence(
                        status="verified",
                        source="file_tree_discovery",
                        observed_at=observed,
                        detail=f"Development guide located at {path}.",
                    ),
                )
            )

    has_readme = bool(docs_dict.get("has_readme", False) or any(d.doc_type == "readme" for d in doc_files))
    has_contributing = bool(docs_dict.get("has_contributing", False) or any(d.doc_type == "contributing" for d in doc_files))

    if doc_files or has_readme or has_contributing:
        purpose = readme_purpose or "Open-source software repository."
        setup_instr = (
            "Documented in README/CONTRIBUTING with commands: " + ", ".join(readme_setup_cmds[:3])
            if readme_setup_cmds
            else "No explicit setup shell commands identified in documentation excerpts."
        )
        test_instr = (
            "Documented with commands: " + ", ".join(readme_test_cmds[:3])
            if readme_test_cmds
            else (
                "Test instructions identified in documentation."
                if docs_dict.get("has_test_guide")
                else "No specific test commands located in documentation."
            )
        )
        contrib_summary = (
            "CONTRIBUTING.md guidelines available for new contributors."
            if has_contributing
            else "No formal CONTRIBUTING.md guide detected at standard paths."
        )
    else:
        purpose = None
        setup_instr = None
        test_instr = None
        contrib_summary = None

    return DocumentationProfile(
        has_readme=has_readme,
        has_contributing=has_contributing,
        project_purpose=purpose,
        docs=doc_files,
        setup_instructions=setup_instr,
        test_instructions=test_instr,
        contributing_guidelines_summary=contrib_summary,
        architecture_overview=next(
            (d.path for d in doc_files if d.doc_type == "architecture"),
            "Architecture documented in project documentation files."
            if any(d.doc_type == "architecture" for d in doc_files)
            else None,
        ),
        evidence=IntelligenceEvidence(
            status="verified" if doc_files else "unknown",
            source="documentation_inspection",
            observed_at=observed,
            detail=f"Evaluated {len(doc_files)} documentation asset(s).",
        ),
    )


# -------------------------------------------------------------
# 6. Module Intelligence & Tree Partitioning
# -------------------------------------------------------------


def partition_and_analyze_modules(
    file_tree: list[str],
    technologies: list[TechnologyItem],
) -> list[ModuleSummary]:
    """
    Partition repository tree into logical components with evidence and responsibilities.
    Groups paths by directory structure and classifies component roles deterministically.
    """
    observed = datetime.now(timezone.utc).isoformat()
    modules: list[ModuleSummary] = []

    # Map directories to their child files
    dir_files: dict[str, list[str]] = defaultdict(list)
    for path in file_tree:
        if "/" in path:
            parts = path.split("/")
            # Use 2-level path for top directories like backend/app or frontend/src
            if len(parts) >= 3 and parts[0] in ("backend", "frontend", "src", "packages", "apps"):
                module_dir = f"{parts[0]}/{parts[1]}"
            else:
                module_dir = parts[0]
            dir_files[module_dir].append(path)
        else:
            dir_files["root"].append(path)

    # Classify each logical module
    for mod_dir, files in sorted(dir_files.items(), key=lambda x: len(x[1]), reverse=True):
        if not files:
            continue

        mod_lower = mod_dir.lower()

        # Determine component type and responsibility
        if any(t in mod_lower for t in ("test", "tests", "spec")):
            comp_type = "tests"
            resp = "Automated test suites, unit verification, and test mocks."
            confidence = "high"
        elif any(d in mod_lower for d in ("doc", "docs", "guide")):
            comp_type = "documentation"
            resp = "Project documentation, architecture design, and usage manuals."
            confidence = "high"
        elif any(api in mod_lower for api in ("api", "routes", "endpoints", "controllers", "views")):
            comp_type = "api_routes"
            resp = "HTTP API endpoints, route declarations, and request dispatchers."
            confidence = "high"
        elif any(ui in mod_lower for ui in ("component", "components", "ui", "pages", "views", "frontend")):
            comp_type = "ui_components"
            resp = "User interface rendering, visual components, and frontend presentation."
            confidence = "high"
        elif any(c in mod_lower for c in ("cli", "commands", "bin", "cmd")):
            comp_type = "cli"
            resp = "Command-line interface entry points, flags parsing, and terminal commands."
            confidence = "high"
        elif any(u in mod_lower for u in ("util", "utils", "helper", "helpers", "common", "shared")):
            comp_type = "utility"
            resp = "Reusable utility functions, helper routines, and cross-cutting helpers."
            confidence = "medium"
        elif any(s in mod_lower for s in ("service", "services", "provider", "providers", "client")):
            comp_type = "service"
            resp = "External integration services, provider clients, and integration adapters."
            confidence = "high"
        elif mod_lower in ("root", "."):
            comp_type = "configuration"
            resp = "Root workspace configuration, dependency manifests, and build orchestrators."
            confidence = "medium"
        else:
            comp_type = "core_logic"
            resp = f"Domain business logic, internal models, and processing workflows for {mod_dir}."
            confidence = "medium"

        # Identify key entry files in module
        key_entries = [
            f
            for f in files
            if f.lower().endswith(
                ("__init__.py", "main.py", "app.py", "index.ts", "index.js", "mod.rs", "lib.rs")
            )
        ]

        mod_name = mod_dir.replace("/", "_") if mod_dir != "root" else "root_config"

        modules.append(
            ModuleSummary(
                name=mod_name,
                root_path=mod_dir if mod_dir != "root" else ".",
                files=files[:12],
                file_count=len(files),
                likely_responsibility=resp,
                component_type=comp_type,  # type: ignore
                confidence=confidence,  # type: ignore
                evidence=IntelligenceEvidence(
                    status="inference",
                    source="directory_structure_and_path_heuristics",
                    observed_at=observed,
                    detail=f"Aggregated {len(files)} file(s) under '{mod_dir}'.",
                ),
                key_entry_files=key_entries[:4],
            )
        )

        if len(modules) >= 12:
            break

    return modules


# -------------------------------------------------------------
# 7. Issue-to-Module Mapping
# -------------------------------------------------------------


def tokenize_text(text: str) -> list[str]:
    """Tokenize and normalize text into clean semantic keywords."""
    clean = re.sub(r"[^a-zA-Z0-9_\-\.\/]", " ", text.lower())
    tokens = [t.strip(".-_") for t in clean.split() if len(t.strip(".-_")) >= 3]
    return [t for t in tokens if t not in STOP_WORDS]


def map_issue_to_repository_modules(
    issue: dict[str, Any],
    file_tree: list[str],
    modules: list[ModuleSummary],
    docs_text: str = "",
) -> IssueToModuleMapping:
    """
    Connect a GitHub issue to candidate repository components and files.
    Calculates deterministic token overlap between issue title, labels, body, and file paths.
    """
    observed = datetime.now(timezone.utc).isoformat()
    issue_num = issue.get("number", 0)
    issue_title = issue.get("title", f"Issue #{issue_num}")
    issue_body = issue.get("body", "") or ""
    raw_labels = issue.get("labels", [])
    labels = [
        (l.get("name") if isinstance(l, dict) else str(l)).strip().lower() for l in raw_labels
    ]

    # Weighted tokenization
    title_tokens = tokenize_text(issue_title)
    label_tokens = [tok for lbl in labels for tok in tokenize_text(lbl)]
    body_tokens = tokenize_text(issue_body[:1000])

    token_weights: dict[str, float] = defaultdict(float)
    for t in title_tokens:
        token_weights[t] += 3.0
    for t in label_tokens:
        token_weights[t] += 2.5
    for t in body_tokens:
        token_weights[t] += 1.0

    candidate_files: list[IssueCandidateMapping] = []

    # Score each file in the file tree
    for path in file_tree:
        lower_path = path.lower()
        path_segments = [s.strip(".-_") for s in re.split(r"[\/\._\-]", lower_path) if s]
        file_name = lower_path.split("/")[-1]

        score = 0.0
        reasons: list[str] = []

        # 1. Explicit path in issue body (highest confidence)
        if lower_path in issue_body.lower() or file_name in issue_body.lower():
            score += 0.50
            reasons.append(f"File or path explicitly mentioned in issue description: '{file_name}'")

        # 2. Token matches in filename and segments
        for seg in path_segments:
            if seg in token_weights and seg not in STOP_WORDS:
                weight = token_weights[seg]
                score += min(0.35, weight * 0.10)
                reasons.append(f"Path segment '{seg}' matches issue keyword (weight {weight:.1f})")

        # 3. Label matching
        if any(lbl in lower_path for lbl in labels if len(lbl) >= 4):
            score += 0.15
            reasons.append("Path matches issue label tag")

        # If file is a test file for a matched source file
        if score > 0.15:
            # Normalize score to [0.1, 0.95]
            clamped_score = round(min(0.95, max(0.15, score)), 2)

            # Identify matching module
            matched_mod = next(
                (m.name for m in modules if path.startswith(m.root_path) and m.root_path != "."),
                None,
            )

            candidate_files.append(
                IssueCandidateMapping(
                    path=path,
                    module_name=matched_mod,
                    relevance_score=clamped_score,
                    reasons=reasons[:3],
                    evidence=IntelligenceEvidence(
                        status="inference",
                        source="deterministic_token_and_path_overlap",
                        observed_at=observed,
                        detail="; ".join(reasons[:2]),
                    ),
                )
            )

    # Sort files by relevance descending
    candidate_files.sort(key=lambda c: c.relevance_score, reverse=True)
    top_candidates = candidate_files[:8]

    # Aggregate candidate modules
    candidate_modules: list[str] = []
    for c in top_candidates:
        if c.module_name and c.module_name not in candidate_modules:
            candidate_modules.append(c.module_name)

    if not candidate_modules:
        # Fall back to root or general core module
        candidate_modules = [modules[0].name] if modules else ["core"]

    rationale = (
        f"Identified {len(top_candidates)} candidate file investigation target(s) across module(s): {', '.join(candidate_modules)} "
        f"based on lexical keyword overlap with issue title '{issue_title[:45]}'."
        if top_candidates
        else "No direct keyword or file path correlation detected; general module inspection recommended."
    )

    limitations = [
        "Mapping reflects deterministic lexical overlap between issue text and repository paths.",
        "Runtime invocation graphs, dynamic imports, and AST dependencies were not executed.",
        "Candidate files represent plausible investigation targets, not verified bug locations.",
    ]

    return IssueToModuleMapping(
        issue_number=issue_num,
        issue_title=issue_title,
        candidate_modules=candidate_modules,
        candidate_files=top_candidates,
        rationale=rationale,
        unknowns_and_limitations=limitations,
        evidence=IntelligenceEvidence(
            status="inference" if top_candidates else "unknown",
            source="deterministic_issue_mapping_engine",
            observed_at=observed,
            detail=f"Evaluated against {len(file_tree)} repository file path(s).",
        ),
    )


# -------------------------------------------------------------
# 8. Top-Level Engine Orchestration
# -------------------------------------------------------------


def generate_repository_intelligence(
    owner: str,
    repo_name: str,
    languages: list[str],
    file_tree: list[str],
    docs_metadata: dict[str, Any],
    ci_evidence: Optional[SignalEvidence] = None,
    candidate_issues: Optional[list[dict[str, Any]]] = None,
    is_truncated: bool = False,
) -> RepositoryIntelligenceReport:
    """
    Generate a complete, deterministic repository intelligence report.
    Integrates overview, entry points, test intelligence, documentation, and issue mappings.
    Works completely offline and without external AI dependencies.
    """
    observed = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    if is_truncated:
        warnings.append("Repository file tree was truncated due to scale limits (retained top paths).")

    # 1. Languages, project type, and repository structure
    lang_dist, proj_type, proj_rationale, struct_type = analyze_languages_and_project_type(
        file_tree=file_tree,
        github_languages=languages,
    )

    # 2. Technologies and manifests
    combined_docs_text = (
        (docs_metadata.get("readme_excerpt") or "") + " " + (docs_metadata.get("contributing_excerpt") or "")
    )
    technologies, package_managers, manifests, configs = analyze_technologies_and_manifests(
        file_tree=file_tree,
        docs_text=combined_docs_text,
    )

    # 3. Entry points
    entry_points = analyze_entry_points(file_tree)

    # 4. Test intelligence
    test_profile = analyze_test_profile(
        file_tree=file_tree,
        docs_text=combined_docs_text,
        ci_evidence=ci_evidence,
        is_truncated=is_truncated,
    )

    # 5. Documentation intelligence
    doc_profile = analyze_documentation_profile(
        docs_dict=docs_metadata,
        file_tree=file_tree,
    )

    # 6. Module partitioning
    modules = partition_and_analyze_modules(
        file_tree=file_tree,
        technologies=technologies,
    )

    # 7. Issue-to-module mappings
    issue_mappings: list[IssueToModuleMapping] = []
    if candidate_issues:
        for issue in candidate_issues[:12]:
            mapping = map_issue_to_repository_modules(
                issue=issue,
                file_tree=file_tree,
                modules=modules,
                docs_text=combined_docs_text,
            )
            issue_mappings.append(mapping)

    evidence = IntelligenceEvidence(
        status="verified" if not is_truncated else "unknown",
        source="deterministic_repo_intelligence_engine",
        observed_at=observed,
        detail=f"Engine evaluated {len(file_tree)} paths, {len(modules)} modules, and {len(technologies)} technologies.",
    )

    return RepositoryIntelligenceReport(
        repo_owner=owner,
        repo_name=repo_name,
        languages=lang_dist,
        project_type=proj_type,  # type: ignore
        project_type_rationale=proj_rationale,
        structure_type=struct_type,  # type: ignore
        technologies=technologies,
        package_managers=package_managers,
        manifest_files=manifests,
        configuration_files=configs,
        entry_points=entry_points,
        test_profile=test_profile,
        documentation_profile=doc_profile,
        modules=modules,
        issue_mappings=issue_mappings,
        inspected_paths_count=len(file_tree),
        tree_truncated=is_truncated,
        evidence=evidence,
        warnings=warnings,
    )
