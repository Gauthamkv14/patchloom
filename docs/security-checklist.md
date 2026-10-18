# PatchLoom Security Checklist & Hardening Audit

This document details the defensive safeguards, automated test evidence, and operational limitations implemented for **PatchLoom** in Milestone M8 (P1 Hardening).

---

## 1. Defensive Safeguards & Verification Matrix

| # | Security Category | Safeguard Implemented | Verification Test | Status |
|---|---|---|---|---|
| **1** | **SSRF & URL Injection** | Strict structural parsing (`parse_and_validate_github_url`), host pinned strictly to `github.com:443`, path traversal (`..`, `%2f`) and null byte (`%00`) rejection. Outbound requests fixed to `api.github.com`. | `test_url_validation.py` (26 tests) | **Verified** |
| **2** | **Application Rate Limiting** | Sliding-window in-memory limiter on `/api/analyze` (10/10m), `/api/plan` (10/10m), and `/api/health` (60/m). Returns structured `429 Too Many Requests` with `Retry-After` header. | `test_hardening.py::test_rate_limiting_enforcement_and_retry_after` | **Verified** |
| **3** | **Anti-IP Spoofing** | Client IP extracted from direct connection (`request.client.host`). `X-Forwarded-For` header is rejected and ignored unless the peer IP is explicitly listed in `settings.TRUSTED_PROXIES`. | `test_hardening.py::test_client_ip_untrusted_proxy_rejection`, `test_client_ip_trusted_proxy_acceptance` | **Verified** |
| **4** | **HTTP Security Headers** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`. | `test_hardening.py::test_security_headers_present_on_api_responses` | **Verified** |
| **5** | **Content Security Policy (CSP)** | Strict `default-src 'none'; frame-ancestors 'none'` on all `/api/*` endpoints; Swagger asset exceptions (`cdn.jsdelivr.net`) restricted strictly to `/docs` and `/redoc`. | `test_hardening.py::test_docs_csp_allows_swagger_assets` | **Verified** |
| **6** | **Credential & Log Redaction** | `SecretRedactionFilter` installed on root, Uvicorn, and app loggers. Sanitizes Google API keys (`AIza...`), GitHub classic PATs (`ghp_...`), fine-grained PATs (`github_pat_...`), Bearer tokens, and configured secrets from log records. | `test_hardening.py::test_redact_sensitive_string_tokens_and_keys`, `test_logging_filter_redacts_record_message` | **Verified** |
| **7** | **Prompt Injection Defense** | All untrusted repository content (issue titles, bodies, comments, README excerpts) enclosed within `<untrusted_issue_data>` XML blocks. System prompt forbids model from executing embedded instructions. | `test_hardening.py::test_prompt_injection_structural_delimiters`, `test_analysis.py::test_prompt_injection_safety_enclosure` | **Verified** |
| **8** | **Path Grounding & Sanitization** | All file paths proposed by Gemma 4 are strictly validated against the ingested repository file tree. Adversarial or hallucinated paths (`/etc/passwd`, `C:\Windows\System32`, `../../.env`) are pruned and warned. | `test_hardening.py::test_planner_drops_hallucinated_or_adversarial_paths`, `test_analysis.py::test_analyze_repository_success_with_grounding` | **Verified** |
| **9** | **Request Body Size Limits** | HTTP middleware enforces a strict 32,768-byte cap on incoming request payloads, returning `413 Payload Too Large`. | `test_main.py` / `limit_request_body_size` middleware | **Verified** |
| **10** | **Epistemic Provenance Integrity** | Verified GitHub facts and model inferences are strictly bifurcated in schemas and UI. Incomplete lookups yield `unknown` or `none_detected`, never a verified negative. | `test_signals.py::test_linked_pr_penalties`, `test_fixtures.py::test_fixture_analysis_scenario_b_partial_evidence` | **Verified** |
| **11** | **Deterministic Error Fallback** | Non-retryable provider errors (`QuotaExceededError`, `AuthenticationError`, `ModelTimeoutError`) never retry blindly; they fall back immediately to deterministic heuristic scoring and plans. | `test_analysis.py::test_quota_failure_never_retries`, `test_planner.py::test_generate_plan_fallback_on_provider_quota_error` | **Verified** |
| **12** | **Safe UI Rendering** | Plain text rendering in React JSX with high-contrast badge indicators. **Zero use of `dangerouslySetInnerHTML`** or unsanitized markdown renderers. | Verified by frontend TypeScript compilation & code inspection | **Verified** |

---

## 2. Server-Side Key Isolation

- `GEMINI_API_KEY` and `GITHUB_TOKEN` are loaded exclusively into backend memory via `backend/app/config.py`.
- No credentials exist in client-side bundles, Vite environment variables (`VITE_*`), or HTTP response payloads.
- `.env` is covered by `.gitignore`. `.env.example` contains safe placeholders only.
- Automated tests run 100% offline without live API credentials.

---

## 3. Known Limitations & Production Roadmap

1. **In-Memory Rate Limiting:**
   - *Current Implementation:* Thread-safe sliding window stored in process memory.
   - *Limitation:* Does not coordinate limits across multiple horizontally scaled backend instances.
   - *Production Roadmap:* In production (100× scale), replace with a distributed Redis-backed rate limiter.
2. **Reverse Proxy Trust Configuration:**
   - *Current Implementation:* `settings.TRUSTED_PROXIES` defaults to `[]`, completely ignoring `X-Forwarded-For`.
   - *Deployment Requirement:* If deploying behind Cloudflare, Render, or AWS ALB, the operator must explicitly configure `TRUSTED_PROXIES` in `.env` with the upstream proxy CIDRs.
3. **Public Repositories Only:**
   - *Design Scope:* PatchLoom intentionally does not support private repositories or OAuth contributor write tokens, eliminating the risk of unauthorized write actions or private data leakage.
