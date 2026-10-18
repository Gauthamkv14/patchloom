# PROGRESS.md — PatchLoom Execution Log & Milestone Tracker

## Current Status
- **Current Milestone:** Gate 4 (M7 Fixtures, Docs & Demo Rehearsal) — Complete & Verified
- **Authorized Gate:** Gate 4 (M7)
- **Milestone Scope Complete:** P0 Core (M0–M7) Fully Completed & Verified
- **Blocked on:** Awaiting user decision on P1 Hardening (M8) or final presentation

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
| **M8** | Hardening & App Rate Limiting | P1 | Not Started | Contingent (P1) |
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

---

## Verified Facts

- Python 3.13.7, Node v25.0.0, npm 11.18.0 confirmed active in local environment.
- Virtual environment created at `backend/.venv`.
- `google-genai` SDK is the official modern library supporting `client.models.generate_content(...)` and `client.aio.models.generate_content(...)`.
- `gemma-4-31b-it` is available on the Gemini API with key. Canonical model identifier is `models/gemma-4-31b-it`.
- `system_instruction` in API config causes 500 INTERNAL on Gemma 4; per §8 and Decision 6, fixed instructions are prepended directly to the user message.
- `response_schema` structured JSON decoding works properly and natively on `gemma-4-31b-it`.
- Path grounding strictly drops ungrounded file paths and annotates risks without crashing.
- Live public repository test on `psf/requests` verified live URL validation, repo metadata retrieval, 103-file tree bounding, README/CONTRIBUTING extraction, and candidate issue viability scoring without model calls.

---

## Recent Activity & Test Results
 
- **Backend Pytest Suite:** 64 passed in 2.33s (`pytest backend/tests/ -v`).
  - `test_health.py`: 1 test passed (200 OK, no secrets).
  - `test_url_validation.py`: 26 tests passed (strict structural validation, rejected exploits, edge-cases).
  - `test_github_client.py`: 7 tests passed (metadata, 404, 403 rate-limit with retry-after, PR exclusion, docs hints, tree bounding and truncation tracking, caching).
  - `test_signals.py`: 8 tests passed (penalties, clamping to [0,100], bands, linked-PR heuristics, candidate pre-filtering).
  - `test_provider.py`: 4 tests passed (missing key auth error, 429 quota error, 403 auth error, invalid JSON output mapping).
  - `test_analysis.py`: 8 tests passed (grounding, fallback on provider error, demo mode skip, invalid URL 400 rejection, prompt injection safety, quota no-retry, invalid output 1-retry, prompt 60k hard cap).
  - `test_planner.py`: 5 tests passed (grounding with hallucinated paths dropped, unverified setup/test labeled as unknown, fallback on quota error without retry, single retry on invalid output, 400 rejection on closed issue).
  - `test_fixtures.py`: 5 tests passed (Scenario A good-fit, Scenario B partial/unknown evidence, Scenario C deterministic fallback, fixture plan generation, zero external network/model calls).
- **Frontend Production Build:** `npm run build` completed cleanly (TypeScript compiled and Vite packaged in 578ms, zero errors, bundle size 163.04 kB).
- **Demo Rehearsal Verified:** Executed `scratch/rehearse_demo.py` covering health, Scenario A analyze & plan, Scenario B partial evidence, and Scenario C fallback with 100% success.
- **Documentation Complete:** Authored comprehensive `README.md` (60s setup, How PatchLoom uses Gemma 4), `docs/architecture.md` (Mermaid diagram, scalability, extension guide, 100x scaling), and `docs/pitch-notes.md` (1-page pitch and demo flow).
- **Security & Epistemic Audit:** Zero credentials in git or frontend bundles. Epistemic provenance strictly enforced (`verified`, `inference`, `unknown`). P0 Core completed.


