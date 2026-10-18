# PROGRESS.md — PatchLoom Execution Log & Milestone Tracker

## Current Status
- **Current Milestone:** Deployment Readiness (Security Audit + Dockerization) — Complete & Verified
- **Authorized Gate:** Deployment Readiness: Security Audit + Dockerization
- **Milestone Scope Complete:** P0 Core (M0–M7) + P1 Hardening (M8) + Deployment Readiness (Security Audit + Dockerization) Fully Verified
- **Blocked on:** Ready for review / Next authorized phase

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
 
- **Backend Pytest Suite:** 82 passed in 2.53s (`pytest backend/tests/ -v`).
  - `test_health.py`: 1 test passed (200 OK, no secrets).
  - `test_url_validation.py`: 26 tests passed (strict structural validation, rejected exploits, edge-cases).
  - `test_github_client.py`: 7 tests passed (metadata, 404, 403 rate-limit with retry-after, PR exclusion, docs hints, tree bounding and truncation tracking, caching).
  - `test_signals.py`: 8 tests passed (penalties, clamping to [0,100], bands, linked-PR heuristics, candidate pre-filtering).
  - `test_provider.py`: 4 tests passed (missing key auth error, 429 quota error, 403 auth error, invalid JSON output mapping).
  - `test_analysis.py`: 8 tests passed (grounding, fallback on provider error, demo mode skip, invalid URL 400 rejection, prompt injection safety, quota no-retry, invalid output 1-retry, prompt 60k hard cap).
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
- **Frontend Production Build:** `npm run build` completed cleanly (TypeScript compiled and Vite packaged in 634ms, zero errors, bundle size 163.04 kB).
- **Docker Compose Production Verification (Revised Network & Digest Pinning):**
  - Base images pinned to immutable digests (`sha256:...`) and built cleanly.
  - Backend port 8000 isolated; host connection refused/timed out on port 8000.
  - Frontend port 3000 acts as exclusive ingress gateway.
  - Live anti-spoofing test passed: 65 requests with rotating spoofed IPs correctly throttled at request 61 with HTTP 429.
  - Container security: backend runs as `appuser` (10001), frontend runs as `nginx` (101), zero `.env` or secrets in image layers.
  - Clean shutdown: `docker compose down` verified cleanly stopping and removing containers and networks.



