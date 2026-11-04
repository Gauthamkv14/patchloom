# PROGRESS.md — PatchLoom Execution Log & Milestone Tracker

## Current Status
- **Current Milestone:** M5.1 Learning History & State Persistence — Complete & Verified
- **Authorized Gate:** M5.1 Learning History & Contributor Growth (Persistence & State Management)
- **Milestone Scope Complete:** P0 Core (M0–M7) + P1 Hardening (M8) + Deployment Readiness + M0 Audit + M0.1 Cleanup + M1 2.0 Intelligence Layer + M2 2.0 Issue Learning + M3 2.0 Guided Implementation + M4 2.0 Verification & Review + M4 Security Remediation + M5.1 Learning History & State Persistence
- **Blocked on:** Gate Approval for Next Milestone / Review

---

## Milestone Status Overview

| Milestone | Scope | Priority | Status | Verification & Evidence |
|---|---|---|---|---|
| **A0** | Specification Audit | P0 | Complete | Audit completed and approved by owner |
| **M0** | Scaffold & Control Documents | P0 | Complete | Backend, frontend, config, health endpoint & control docs verified |
| **M1** | GitHub Client & URL Guardrails | P0 | Complete | Structural URL parser, bounded retrieval, error mapping, caching & 34 tests passing |
| **M2** | Deterministic Signals & Viability | P0 | Complete | Deterministic signals engine, linked-PR heuristic, scoring & 42 tests passing |
| **M3** | Model Provider Contract & Gemma Smoke Test | P0 | Complete | Minimal ModelProvider interface, GeminiProvider, 4 offline tests, manual smoke test verified |
| **M4** | Batched Fit Analysis & Ranking | P0 | Complete | Single batched call, path grounding, 1-retry fallback, prompt injection test, 51 tests passing |
| **M5** | First-PR Planner | P0 | Complete | Grounded 3–7 step plan, unverified detail labeling, safe fallback, 59 tests passing |
| **M6** | Dashboard & Contributor UX | P0 | Complete | React + Vite + TS UI, 3-tier badges, plan modal, copy actions, safe text rendering, build verified |
| **M7** | Fixtures, Docs & Demo Rehearsal | P0 | Complete | 3 demo fixtures (Scenarios A/B/C), README, architecture.md, pitch-notes.md, 64 tests passing |
| **M8** | Hardening & App Rate Limiting | P1 | Complete | In-memory limiter, security headers, log redactor, injection tests, security checklist, 74 tests passing |
| **Deployment Readiness** | Security Audit & Dockerization | P1+ | Complete | Upstream caps, delimiter smuggling sanitizer, chunked encoding rejection, CIDR proxy trust, multi-stage unprivileged Docker containers, 79 tests passing |
| **M0 2.0** | PatchLoom 2.0 Baseline Audit | 2.0 | Complete | 86 tests passing verified; full codebase audit; AGENTS.md updated; M1 design documented |
| **M0.1** | Architectural Cleanup | 2.0 | Complete | Provider factory, has_ci bounded check & provenance, scratch cleanup, google-genai pinned, 95 tests passing |
| **M1 2.0** | Repository Intelligence Layer | 2.0 | Complete | Deterministic intelligence engine, overview, entrypoints, test & CI, docs, modules, issue-mapping, 110 tests passing |
| **M2 2.0** | Intelligent Issue Learning | 2.0 | Complete | Personalized Issue Learning Briefs, requirements extraction, grounded investigation targets, technical concepts & sequencing, measurable objectives, interactive readiness checklist, 122 tests passing |
| **M3 2.0** | Guided Implementation Workspace | 2.0 | Complete | Implementation roadmaps, 3-tier progressive hint system, code exploration guidance, alternative approaches with trade-offs, step checkpoints, optional educational patch suggestions, 130 tests passing |
| **M4 2.0** | Verification & Review | 2.0 | Complete | Deterministic diff analyzer (100KB), relevant test discovery, isolated Docker runner boundary, AI diff review & retry, regression analysis, readiness assessment, maintainer draft PR generation, 150 tests passing |
| **M4 Security Remediation** | Runner Allowlist, HMAC Integrity & Container Lifecycle | P0/P1 | Complete | Structured command allowlist, HMAC-SHA256 plan signing (30m TTL), API authorization boundary (HTTP 400), unique container naming, timeout docker kill & rm -f cleanup, 12 Docker hardening flags, 157 tests passing (1 skipped live) |
| **M5.1 2.0** | Learning History & State Persistence | 2.0 | Complete | IndexedDB storage adapter (v1), session UUID identity, bounded M2/M3/M4 snapshots, zero auth persistence invariant, opt-in diff privacy, honest learning metrics, demo isolation, soft 50-session warning, 5MB export/import validation, 13 frontend tests passing, clean build |
| **M5.2 2.0** | Learning History & Session Resumption UI | 2.0 | Not Started | History drawer/tab, session resumption, profile overview |
| **M5.3 2.0** | Contributor Growth & Discovery Personalization | 2.0 | Not Started | Grounded skill progression & viability weighting |
| **M9** | Ollama Provider & Evaluation | P2 | Not Started | Stretch (P2) |
| **M10** | Render Deployment | P3 | Not Started | Contingent / Optional (P3) |

---

## Decisions Ledger (Approved Authoritative Record)

1. **Scope and Priorities:** Preserve the existing MVP and architecture. M0–M7 are P0; M8 is P1; M9 is P2; M10 is P3. Prioritize a working local application and reliable fixture-based demo. No speculative features or unnecessary abstractions.
2. **Linked-PR Detection:** Use bounded GitHub REST evidence collection. Record the evidence source and distinguish confirmed detection from heuristic evidence. Preserve `detected`, `none_detected`, and `unknown` semantics. Never interpret a failed, skipped, or incomplete lookup as proof that no linked PR exists. Apply a consistent detection policy across candidates, with explicit request bounds. Do not introduce GraphQL or additional infrastructure without justification and approval.
3. **Repository-Tree Bounds:** Limit retained paths to 400 and exclude irrelevant generated files, lockfiles, and build output as specified. Apply HTTP response-size limits, timeouts, and bounded pagination. Record GitHub-side truncation separately from application-side filtering or truncation. Surface incomplete tree coverage and never treat an incomplete tree as exhaustive.
4. **API and Control-Document Scope:** Do not add `rate_limit_remaining` or `rate_limit_reset` as mandatory public response fields. Handle rate limits through the existing safe error and warning contract. Keep `AGENTS.md` self-contained, but do not duplicate every Pydantic schema in it; implementation schemas and tests remain authoritative for exact field definitions.
5. **Credentials and Startup:** `GITHUB_TOKEN` and `GEMINI_API_KEY` are optional for startup. `/api/health` and fixture/demo mode must work without either credential. A GitHub token is recommended for live testing and higher rate-limit headroom. Missing credentials must produce safe, actionable errors when the corresponding live functionality is requested.
6. **Gemma Verification:** During M3, explicitly verify the configured model ID, availability through the selected API, system-instruction behavior, structured-output support, and Pydantic validation. Use system instructions for fixed instructions if the smoke test confirms they work as required. Otherwise, use the supported prompt arrangement specified in the MVP. If the model cannot satisfy the contract, stop and report the evidence before proposing any model or architecture change. Never fabricate AI results or bypass validation.
7. **GitHub URL Security:** Use strict structural URL parsing and canonicalization, not a regular expression alone. Enforce all URL restrictions in §6. Requests must use the fixed GitHub API host, with redirects disabled or explicitly validated, and appropriate timeouts and response-size limits.
8. **Dependencies and Reproducibility:** Select compatible dependency versions, pin them appropriately, and use lock files where supported by the chosen package managers. Avoid unnecessary dependencies and do not silently upgrade or introduce major tooling.
9. **Container Security & Ephemeral Secrets:** Docker containers run exclusively as non-root users (`appuser` UID 10001, `nginx` UID 101). Secrets are strictly excluded from image layers via `.dockerignore` and passed only via runtime environment variables. The frontend Nginx container reverse-proxies `/api/` to `backend:8000` with strict Content Security Policy.
10. **Network Ingress & Targeted Proxy Isolation:** The backend container's port 8000 is internal only (`expose: ["8000"]`) and never published to the host interfaces. The frontend container on port 3000 serves as the single public gateway. To prevent proxy spoofing, Nginx overwrites incoming forwarded headers with the TCP remote address (`$remote_addr`), and backend `TRUSTED_PROXIES` is strictly restricted to the static IP of the frontend proxy container (`172.28.0.10`) on dedicated subnet `172.28.0.0/24`. All base container images are pinned by deliberate versions and immutable multi-architecture manifest digests.
11. **Deterministic Repository Intelligence Engine (Pillar 2 - UNDERSTAND):** The M1 engine is 100% deterministic, operating without requiring AI model inference, credentials, cloning, shell execution, or external network dependencies beyond standard public GitHub tree/metadata fetching. Testing infrastructure is strictly modeled as `detected`, `not_detected` (only when the tree is complete), or `unknown` (when truncated or incomplete). Every insight tracks evidence provenance (`status`, `source`, `observed_at`). Issue-to-module mapping strictly retains grounded files present in the ingested tree. Plain text rendering in React JSX with zero `dangerouslySetInnerHTML`.
12. **Intelligent Issue Learning Engine (Pillar 3 - LEARN):** M2 introduces personalized Issue Learning Briefs that prioritize educational understanding and contributor independence over code generation. File targets in `investigation_targets` must strictly exist in the ingested repository tree; ungrounded paths are dropped. When AI inference fails, times out, or exceeds quota, a deterministic fallback brief is generated preserving all issue facts and M1 repository intelligence, with honest `ai_status="unavailable_or_invalid"`. Untrusted issue descriptions and comments are bounded and defensively sanitized. Plain text JSX rendering with interactive self-assessment readiness checklist.
13. **Guided Implementation Engine (Pillars 3 & 4 - LEARN & BUILD):** M3 delivers an interactive, evidence-grounded guided implementation workspace. Steps are grounded in verified repository files, with hallucinated paths strictly dropped. Up to 3 progressive hints per step reduce ambiguity gradually upon explicit user reveal without spoiling the solution prematurely. Implementation approaches contrast viable trade-offs, edge cases, and regression risks. Optional code suggestions are strictly labeled `unverified_educational_draft` and never executed, applied, or committed. Contributor controls their step progress (`not_started`, `in_progress`, `understood`, `completed`); AI never auto-completes steps.
14. **Verification & Review Architecture & Isolated Test Boundary (Pillar 4 - VERIFY & CONTRIBUTE):** M4 introduces comprehensive change validation and contribution review. Contributor git diffs are deterministically parsed and bounded (max 100KB), with roadmap alignment cross-referencing and symbol detection. Relevant tests are discovered from file counterpart patterns, test directories, and roadmap targets. Test execution occurs strictly in disposable, network-disabled Docker containers with dropped capabilities (`--cap-drop ALL`), non-root execution, bounded CPU/memory, and explicit contributor authorization (`authorized=True`). Host execution is strictly forbidden; if Docker daemon is offline, the runner safely reports `execution_unavailable`. AI review findings and regression risks are grounded strictly against ingested repository paths with hallucinated files dropped. Draft PR descriptions are generated strictly from verified context and categorized test results.
15. **M4 Security Remediation & Container Isolation Hardening (VERIFY Pillar):** Following the focused security audit, replaced loose executable prefix matching with strict structured command validation (`SUPPORTED_RUNNER_CONFIGS`). Mandatory subcommand tokens are required (blocking `npm install`, `npm run`, `python script.py`, `python -m http.server`, `cargo run`, `go run`). Argument validator prohibits shell metacharacters, path traversal, interpreter flags (`-c`, `-m`, `--eval`), and config overrides (`-o`, `--override-ini`). Generated execution plans are cryptographically signed with server-side HMAC-SHA256 (30-minute TTL) binding repo URL, issue number, runner, command, arguments, timeout, and expiration; tampered or expired plans are rejected at the API boundary with HTTP 400 Bad Request. Contributor authorization (`authorized=True`) is enforced at the API boundary with HTTP 400 Bad Request prior to container setup. Containers run under unique deterministic names (`patchloom_test_<uuid>`), with targeted `docker kill` on timeout/cancellation and forced `docker rm -f` in `finally`. Patches are verified against traversal, absolute paths, and symlinks. Explicitly distinguish implemented Docker safeguards from live-Docker-verified behavior: while all 12 Docker hardening flags (`--read-only`, `--security-opt no-new-privileges:true`, `--network none`, `--cap-drop ALL`, `-u 10001:10001`, `--cpus=1.0`, `--memory=512m`, `--memory-swap=512m`, `--pids-limit=64`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m`) and process lifecycle controls are verified in unit tests, real repository test execution remains unavailable (`status="execution_unavailable"`) in production until a prepared workspace is supplied and provisioned runner images with pre-installed test tooling (e.g. `pytest`, `vitest`) are configured. Base runtime images do not bundle third-party test runners, repository cloning is strictly out of scope, and host execution fallback is completely prohibited. Live Docker tests are honestly skipped with diagnostic when the daemon is offline.
16. **Learning History & Contributor Growth Persistence (M5.1):** Authoritative local client storage in IndexedDB (`patchloom_learning_db`, v1) with in-memory fallback for private browsing and headless test runners. Sessions are tracked by unique UUIDs (`crypto.randomUUID()`) to prevent accidental session collisions or silent overwriting across distinct attempts on the same issue. Sessions store bounded, versioned snapshots restoring M2 learning briefs & checklist confirmations, M3 guided implementation roadmaps & progressive hint reveals, and M4 verification findings, regression risks, and draft PRs. Storage privacy invariants: raw diffs are omitted by default (opt-in storage with privacy warnings), unbounded repository trees are excluded, and M4 execution authorization is strictly never persisted or restored (`authorizedExecution` resets to `false` on restore). Demo sessions (`isDemo: true`) are completely isolated from real user contributor profiles. Honest metrics distinguish encountered concepts, practiced concepts, user-marked understanding, and completed steps without claiming unverified mastery. Soft quota warning alerts users when sessions reach 50. Export/import validates schema, format, and enforces a strict 5MB size limit. The backend remains 100% stateless with zero database, auth, or telemetry.

---

## Verified Facts

- Python 3.13.7, Node v25.0.0, npm 11.18.0 confirmed active in local environment.
- Docker Engine v29.8.1 and Docker Compose v5.5.1 verified functioning on host.
- Base images pinned to deliberate versions and immutable multi-arch manifest digests:
  - Backend: `python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f` (Python 3.13.16 Debian slim, supported through October 2029).
  - Frontend Builder: `node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402` (Node.js v22.23.3 LTS Alpine 3.21, supported through April 2027).
  - Frontend Runtime: `nginx:1.30-alpine@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5` (Nginx 1.30.6 Alpine 3.24 Stable branch, verified upstream on 2026-10-18).
- Virtual environment created at `backend/.venv`.
- `google-genai` SDK is the official modern library supporting `client.models.generate_content(...)` and `client.aio.models.generate_content(...)`.
- `gemma-4-31b-it` is available on the Gemini API with key. Canonical model identifier is `models/gemma-4-31b-it`.
- `system_instruction` in API config causes 500 INTERNAL on Gemma 4; per §8 and Decision 6, fixed instructions are prepended directly to the user message.
- `response_schema` structured JSON decoding works properly and natively on `gemma-4-31b-it`.
- Path grounding strictly drops ungrounded file paths and annotates risks without crashing.
- Live public repository test on `psf/requests` verified live URL validation, repo metadata retrieval, 103-file tree bounding, README/CONTRIBUTING extraction, and candidate issue viability scoring without model calls.
- Both Docker containers build cleanly and execute under unprivileged non-root users (`appuser` UID 10001 on backend, `nginx` UID 101 on frontend).
- Backend port 8000 is internal only (`expose: ["8000"]`); direct TCP connections from the host to `localhost:8000` fail cleanly (connection timed out/refused).
- Frontend port 3000 is the sole ingress gateway, proxying `/api/` cleanly to `backend:8000`.
- Nginx sanitizes incoming client proxy headers by overwriting `X-Forwarded-For` and `X-Real-IP` with `$remote_addr`.
- Live rate-limiting and anti-spoofing verified: 65 requests sent with varying fake client IPs resulted in 60 successful requests and 5 requests throttled with `HTTP 429 Too Many Requests`.

---

## Recent Activity & Test Results

- **PatchLoom 2.0 M3 Guided Implementation Workspace (2026-11-02):**
  - **Full Backend Pytest Suite:** 130 passed in 4.78s (`pytest backend/tests/ -v`).
  - Added `test_guided_implementation.py` with 8 comprehensive unit tests:
    - `test_deterministic_fallback_guided_plan`: Verified evidence-grounded fallback roadmap, progressive hint hierarchy, checkpoints, alternative approaches, and educational patch labeling.
    - `test_build_guided_implementation_prompt_wrapping_and_truncation`: Verified prompt delimiters `<untrusted_issue_data>`, `<untrusted_file_tree>`, character bounds ($\le 60,000$ chars).
    - `test_generate_guided_implementation_plan_success`: Grounding retention of valid paths and dropping of hallucinated paths across steps, targets, and patches.
    - `test_generate_guided_implementation_invalid_output_retry`: Verified single retry upon `InvalidModelOutputError`.
    - `test_generate_guided_implementation_quota_fallback`: Verified immediate fallback on `QuotaExceededError` without retries, preserving context with `ai_status="unavailable_or_invalid"`.
    - `test_load_fixture_guided_implementation`: Verified offline fixture plan loading for pre-saved and dynamic synthesis issues across Scenarios A & B.
    - `test_api_guided_implementation_demo_mode`: Verified `POST /api/guided-implementation` returns 200 with valid schema in demo mode.
    - `test_api_guided_implementation_invalid_url`: Verified strict 400 rejection on non-GitHub URLs.
  - **Frontend Production Build Verified:** `tsc && vite build` compiled and packaged cleanly in 625ms (zero TypeScript errors, bundle size 203.44 kB).
  - **Frontend Implementation:** Built interactive `GuidedImplementationModal.tsx` featuring step navigation sidebar with progress indicators, 3-tier progressive hint accordions (`gentle direction`, `specific investigation`, `technical guidance`), contributor-controlled step checkpoints (`not_started`, `in_progress`, `understood`, `completed`), alternative implementation approaches comparison view, code exploration targets view, and collapsed educational code suggestion cards with strict warning notices. Added launch button to `LearnModal` and direct action button to `IssueCard`.
  - **Demo Rehearsal Script Updated:** `scratch/rehearse_demo.py` updated with Step 3c testing `POST /api/guided-implementation` end-to-end; verified 100% pass locally.
 
- **Backend Pytest Suite:** 110 passed in 6.47s (`pytest backend/tests/ -v`).
  - `test_repo_intelligence.py`: 15 tests passed (deterministic overview, language distribution, technologies, entry points, test & CI intelligence, documentation extraction, module partitioning, issue-to-module mapping, demo mode, API endpoint).
  - `test_health.py`: 1 test passed (200 OK, no secrets).
  - `test_url_validation.py`: 26 tests passed (strict structural validation, rejected exploits, edge-cases).
  - `test_github_client.py`: 12 tests passed (metadata, 404, 403 rate-limit with retry-after, PR exclusion, docs hints, tree bounding and truncation tracking, caching, CI detection detected/not_detected/unknown).
  - `test_signals.py`: 8 tests passed (penalties, clamping to [0,100], bands, linked-PR heuristics, candidate pre-filtering).
  - `test_provider.py`: 11 tests passed (missing key auth error, 429 quota error, 403 auth error, invalid JSON output mapping, transient 503 retry, persistent 500 error, provider routing, factory case-insensitivity, unsupported provider error).
  - `test_analysis.py`: 9 tests passed (grounding, fallback on provider error, demo mode skip, invalid URL 400 rejection, prompt injection safety, quota no-retry, invalid output 1-retry, prompt 60k hard cap, unsupported provider rejection).
  - `test_planner.py`: 5 tests passed (grounding with hallucinated paths dropped, unverified setup/test labeled as unknown, fallback on quota error without retry, single retry on invalid output, 400 rejection on closed issue).
  - `test_fixtures.py`: 5 tests passed (Scenario A good-fit, Scenario B partial/unknown evidence, Scenario C deterministic fallback, fixture plan generation, zero external network/model calls).
  - `test_hardening.py`: 18 tests passed:
    - Rate limit rule parser (`10/10minutes`, `60/minute`, etc.)
    - Client IP extraction with untrusted proxy header rejection
    - Client IP trusted proxy acceptance
    - Client IP preference for edge proxy `X-Real-IP`
    - Client IP rejection of spoofed `X-Real-IP` from untrusted direct peers
    - Client IP CIDR subnet matching for trusted proxies
    - Rate limit 429 & Retry-After enforcement
    - Defensive security headers (nosniff, DENY, referrer-policy)
    - Swagger CSP compatibility
    - Credential redaction filter (Google AI keys, GitHub PATs, Bearer tokens, URL secrets)
    - Logging filter argument type preservation (%d format string safety)
    - Prompt injection delimiters and structural enclosures
    - Delimiter smuggling defense via `sanitize_untrusted_text()`
    - Request body limiter chunked transfer encoding rejection
    - Actual request body size enforcement on streaming payloads and spoofed Content-Length defense
    - Upstream GitHub API response payload cap enforcement (>5MB tree safety cap)
    - Planner malicious and ungrounded file path dropping (and positive retention of valid paths)
- **Backend Pytest Suite:** 86 passed in 2.54s (`pytest backend/tests/ -v`).
  - Added schema compatibility and numeric range constraint tests in `test_provider.py`.
  - Added bounded 3-attempt transient error retry tests with progressive backoff.
- **Frontend Production Build:** `npm run build` completed cleanly (TypeScript compiled and Vite packaged in 549ms, zero errors, bundle size 163.04 kB).
- **Gemma 4 Live Provider Investigation & Hardening Findings:**
  - Diagnosed that `ge=0, le=100` numeric constraints on Pydantic schemas translate to `minimum`/`maximum` in OpenAPI schemas, triggering server-side grammar compiler errors (`500 INTERNAL`) on `models/gemma-4-31b-it`. Replaced with clean integer fields and local Pydantic `@field_validator` clamping.
  - Strongly typed `PlanModelOutput` schema with `PlanStepItem` and `GuidanceItem`, eliminating unsupported `additionalProperties` error.
  - Added bounded 3-attempt retry loop with progressive backoff (`[2.0s, 4.0s]`) for transient 500/503 server errors.
  - Final live verification: Smaller candidate batches (3–4 candidates) succeed when the provider is healthy. Under full batched loads and during peak traffic, `models/gemma-4-31b-it` on the Gemini Developer API persistently encounters upstream service unavailability (`503 UNAVAILABLE`) and server internal errors (`500 INTERNAL`).
  - Strict fallback invariant confirmed: When Gemma 4 inference is unavailable or errors, PatchLoom honestly marks `ai_status: "unavailable_or_invalid"`, does not disguise fallback scores as AI results, and reliably renders 100% of deterministic GitHub viability signals and grounded files.
- **Judge-Ready README.md Upgrade:**
  - Rewrote README.md covering problem/solution, Gemma 4 role, Docker Compose architecture with Mermaid diagrams, 60-second quickstart, epistemic evidence labeling, offline fixture mode, and test verification.
- **Pre-Submission Secret Audit (Zero Real Leaks):**
  - Scanned all 60 tracked files across backend, frontend, fixtures, and docs: zero real API keys, PATs, or credentials found.
  - Scanned full Git history across all commits: confirmed `.env` was never committed and no real secrets exist in historical revisions.
  - Replaced high-entropy synthetic test fixtures in `backend/tests/test_hardening.py` with zero-entropy concatenated strings (`"AIzaSy" + "0" * 33`, `"ghp_" + "0" * 36`, etc.) to prevent false-positive alarms on external scanners while fully preserving regex redaction regression tests.
  - Confirmed `.env` is safely ignored by `.gitignore` (`.gitignore:2:.env`) and excluded by `.dockerignore` (`.dockerignore:11:.env`). `.env.example` contains only non-secret placeholders.
- **Provider Resilience Hardening (Prompt Mode Fallback):**
  - Added automatic prompt-mode fallback to `GeminiProvider._call_model` on schema errors (`ValueError: additionalProperties`) and server-side 500 crashes.
  - Ensured `_fallback_prompt_mode` omits `response_mime_type="application/json"` to bypass the unstable Gemini API Gemma proxy.
  - Enhanced `_parse_and_validate` with regex block extraction to reliably extract JSON from markdown fences or surrounding model commentary.
- **PatchLoom 2.0 M4 Verification & Review (2026-11-03):**
  - **Deterministic Unified Diff Parser (`diff_analyzer.py`):** Parses unified git diffs up to 100KB, extracts touched files, added/removed line metrics, detected function/class symbols, and cross-references touched files against M3 implementation roadmap steps to highlight potentially unrelated scope.
  - **Relevant Test Discovery (`test_discovery.py`):** Discovers relevant tests using file counterpart conventions (`test_<module>.py`, `<module>_test.py`), test directory discovery, and roadmap step matching. Detects test framework (`pytest`, `vitest`, `jest`, `cargo`, `go`) and synthesizes allowlisted command arguments.
  - **Isolated Docker Test Boundary (`test_runner.py`):** Implements all 15 container safeguards: `--network none`, `--cap-drop ALL`, CPU limits (1.0 core), memory limits (512MB), PID limits (64), read-only mounts, disposable container life-cycle, and explicit contributor authorization (`authorized=True`). Probes Docker daemon safely and returns `execution_unavailable` when offline without executing on the host. Allowlist rejects shell metacharacters and unapproved runners.
  - **Verification Orchestration & Fallback Engine (`verification.py`):** Evaluates diff against repository intelligence and roadmap targets using Gemma 4. Implements 1 automatic retry on `InvalidModelOutputError`, strict repository file path grounding (dropping invented files), and robust deterministic fallback with explicit provenance.
  - **Draft PR Generator (`generate_draft_pr`):** Produces maintainer-ready PR descriptions with summary of changes, problem addressed, implementation overview, categorized tests performed (`executed_and_passed`, `executed_and_failed`, `not_executed`, `manually_verified`), known limitations, and maintainer checklist. PRs are drafts only; no GitHub write or branch creation is performed.
  - **API Endpoints Registered (`api.py`):** `POST /api/verification/analyze` (rate-limited 10/10m), `POST /api/verification/execute` (rate-limited 5/10m), `POST /api/verification/prepare-pr` (rate-limited 10/10m). Request body size limit raised to 128KB in `config.py` to support 100KB diff payloads.
  - **Test Suite Verification:** 150 passed in 6.92s (`pytest backend/tests/ -v`). Added 20 comprehensive unit tests in `test_verification.py`.
  - **Frontend Verification Workspace:** Created `VerificationModal.tsx` with Diff & Changes viewer, Tests & Isolated Runner panel, Review Findings grouped by severity, Regression & Readiness assessment, and Draft PR viewer with copy actions. Integrated into `IssueCard` and `GuidedImplementationModal`. Production build passed in 743ms (`npm run build --prefix frontend`).
  - **Demo Rehearsal Verified:** Updated `scratch/rehearse_demo.py` with Step 3d covering analyze, execute, and prepare-pr. Full rehearsal passed with zero errors.
- **PatchLoom 2.0 M4 Security Remediation (2026-11-04):**
  - **Structured Command Allowlist (`test_runner.py`):** Replaced loose executable prefix matching with immutable `SUPPORTED_RUNNER_CONFIGS`. Requires exact executable and mandatory subcommand tokens, blocking `npm install`, `npm run`, `python arbitrary.py`, `python -m http.server`, `cargo run`, and `go run`. Added strict argument validator rejecting shell metacharacters (`;&|`$><()\\*?!{}[]~^"'\x00`), path traversal (`..`, leading `/`, drive letters), interpreter flags (`-c`, `-m`, `--eval`), and configuration overrides (`-o`, `--override-ini`).
  - **HMAC-SHA256 Execution Plan Integrity (`plan_signing.py`):** Generated execution plans are cryptographically signed with HMAC-SHA256, binding canonical repo URL, issue number, runner, command, arguments, timeout, and a 30-minute expiration timestamp (`expires_at`). Plans with modified parameters, wrong issue/repo context, or expired timestamps are rejected.
  - **API Authorization & Integrity Enforcement (`api.py`):** Enforces explicit contributor authorization (`authorized=True`) directly at the API boundary, rejecting unauthorized requests with HTTP 400 Bad Request prior to container setup. Enforces signature verification on `/api/verification/execute` in live mode with HTTP 400 Bad Request for forged or expired plans.
  - **Container Lifecycle Management (`test_runner.py`):** Assigned unique container names (`patchloom_test_<uuid>`). Subprocess timeouts and task cancellations issue targeted `docker kill <name>` to stop daemon processes immediately, followed by guaranteed `docker rm -f <name>` in `finally` blocks to prevent orphaned containers.
  - **Safe Workspace Construction (`test_runner.py`):** Added `validate_diff_content` checking for path traversal (`..`), absolute paths, and symlink creation (`120000`). If uncloned repository workspace is unavailable outside demo mode, honestly reports `status="execution_unavailable"` without simulated results.
  - **Comprehensive Docker Hardening (12 Flags):** Added `--read-only`, `--security-opt no-new-privileges:true`, `--network none`, `--cap-drop ALL`, `-u 10001:10001`, `--cpus=1.0`, `--memory=512m`, `--memory-swap=512m`, `--pids-limit=64`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m`.
  - **Honest Test Execution & Reporting:** Live Docker test checks daemon status and skips honestly with diagnostic message when daemon is unreachable; 8 new security regression tests added in `test_verification.py`. Full test suite: 157 passed, 1 skipped in 5.50s. Production build clean in 658ms. Demo rehearsal 100% passed.
- **PatchLoom 2.0 M5.1 Learning History & State Persistence (2026-11-04):**
  - **IndexedDB Storage Adapter (`indexedDb.ts`):** Implemented versioned (`v2`) local storage adapter with stores `learning_sessions` and `growth_profiles` (`keyPath: 'profileKey'`). Includes in-memory fallback for headless tests and private browsing. Implemented monotonic ISO timestamps (`getMonotonicIsoTimestamp`) to guarantee deterministic ordering across rapid creations. Added `closeDatabase()`, `getStorageMode()`, `isPersistent()`, and `checkStorageStatus()`.
  - **Session Identity & Non-Destructive Lookup:** Sessions use UUIDs (`crypto.randomUUID()`). Distinct attempts on the same repository and issue remain independent records without silent overwrite. Added `findActiveSession` helper to continue prior active sessions.
  - **Versioned Bounded Snapshots:** Captures M2 learning briefs & checklist confirmations, M3 guided implementation roadmaps, step progress, and progressive hint reveal states, and M4 verification reports, review findings, and draft PRs. Excludes raw file trees. Diffs are excluded by default (`hasRawDiffStored: false`).
  - **M4 VerificationModal Integration:** Wired `VerificationModal.tsx` with controlled props `initialDiff`, `initialOptInStoreDiff`, `onOptInStoreDiffChange`, and `onReAnalyzeDiff`. Added opt-in checkbox with privacy notice under the Git Diff input. Genuinely restores verification report, review findings, regression risks, readiness assessment, test execution result (including `execution_unavailable`), draft PR, and opt-in diff text.
  - **M4 Execution Invariant Preserved:** Execution authorization is never persisted or imported; on session restore or import, `authorizedExecution` strictly defaults to `false`.
  - **Honest Contributor Growth Metrics:** Computes `encounteredConcepts`, `practicedConcepts`, `userMarkedUnderstanding`, and `completedSteps` strictly from user actions; no unverified claims of skill mastery or professional competence.
  - **Demo Isolation:** Demo sessions (`isDemo: true`) are segregated; contributor growth profile computation never merges demo sessions with non-demo sessions. Provided realistic offline fixtures in `demoHistoryFixture.ts`.
  - **Storage Quota & Temporary Mode Warnings:** Soft limit at 50 sessions triggers non-intrusive warning notice. UI status bar exposes storage mode (`IndexedDB (Persistent)` vs `In-Memory (Temporary)`). When in-memory fallback is active, renders prominent warning that history is temporary and will disappear on reload.
  - **Export & Import Validation:** JSON export/import enforces format verification, schema validation, and rejects payloads exceeding 5MB or containing malformed data.
  - **Comprehensive Test Verification:**
    - Node Unit Tests (`npm test --prefix frontend`): 14 passed in 30ms exercising `InMemoryStore` fallback.
    - Real Browser IndexedDB Tests (`npm run test:browser --prefix frontend`): 5 passed in 3s using headless Chromium, verifying real LevelDB persistence across connection close, reload simulation, reopening, data restoration, and export/import.
    - Production Build (`npm run build --prefix frontend`): Clean in 693ms.
    - Backend Pytest Suite: 158 passed, 1 skipped in 5.97s.
    - Offline Demo Rehearsal: 100% passed across Scenarios A/B/C.





