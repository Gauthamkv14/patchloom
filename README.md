# PatchLoom

> **From "I want to contribute" to a repo-grounded plan for a first PR.**

PatchLoom matches new open-source contributors to viable GitHub issues using deterministic repository signals and Gemma 4 reasoning, then generates a concrete, grounded plan for their first pull request.

Built for **Hacktoberfest Hack Day (Theme 2: AI for Open Innovation)**.

---

## 1. The Problem and Solution

### The Contributor's Dilemma
New open-source contributors face an overwhelming discovery barrier. Repositories often have hundreds of open issues, but most issues are unsuited for beginners:
- Issues may be abandoned, outdated, or already claimed by someone else.
- Issue descriptions frequently lack reproduction steps or environment setup instructions.
- Contributors cannot gauge whether an issue matches their current skillset or available time.
- Even when an issue is selected, contributors struggle to know which files to touch, what tests to run, or how to draft a maintainer-ready pull request.

### The PatchLoom Solution
PatchLoom bridges the gap between wanting to contribute and opening your first PR through a transparent, 3-stage pipeline:
1. **Deterministic Repository Viability Signals:** Ingests live repository metadata, documentation (`README.md`, `CONTRIBUTING.md`), recent issue activity, and the repository file tree. Calculates an objective viability score (0-100) assessing issue staleness, assignment status, linked PR evidence, and reproduction quality.
2. **Gemma 4 Contributor Fit Assessment:** Evaluates pre-filtered candidate issues against the contributor's skills, experience level, and available hours using `models/gemma-4-31b-it`. Identifies matching skills, skill gaps, estimated effort, and candidate files strictly grounded in the ingested file tree.
3. **Grounded First-PR Planner:** Generates an actionable, step-by-step contribution plan (3-7 steps) for a chosen issue, complete with setup verification, test guidance, a draft PR title, and an unopinionated PR description draft.

### What PatchLoom Does and Does Not Do
- **What it does:** Recommends a ranked shortlist of plausible issues (up to 12), explains why each matches your skills and time budget, rigorously separates verified facts from AI inferences, and produces a grounded PR plan.
- **What it does NOT do:** PatchLoom does **not** create accounts or databases, does **not** modify GitHub repositories, does **not** create branches or open automated PRs, does **not** clone repositories or execute arbitrary code, and does **not** hallucinate non-existent files.

---

## 2. Why Gemma 4

PatchLoom leverages **Gemma 4** (`gemma-4-31b-it`) strictly as an analytical text-to-JSON reasoning engine with zero tools, zero code execution, and zero write privileges.

```
+-------------------------------------------------------------------------------+
|                               Why Gemma 4?                                    |
+-------------------------------------------------------------------------------+
|  1. Semantic Fit Reasoning: Matches nuanced issue descriptions to contributor |
|     skills beyond keyword overlap.                                            |
|  2. Structured Output: Emits schema-validated JSON conforming to Pydantic    |
|     contracts via the official google-genai SDK.                              |
|  3. Safe Guardrails: Zero autonomous code execution; runs under structural    |
|     prompts (<untrusted_issue_data>) to neutralize prompt injection.          |
+-------------------------------------------------------------------------------+
```

### Bounded Model Operations
PatchLoom uses exactly two bounded model interactions:
1. **Batched Fit Assessment:** Exactly **1 model call** evaluates candidate issues simultaneously against the contributor profile, avoiding latency creep and token exhaustion.
2. **First-PR Plan Generation:** Exactly **1 model call** produces a sequenced 3-7 step roadmap for a selected issue.

### Verification, Grounding & Safety Invariants
- **Strict Repository Path Grounding:** Gemma 4 is provided with the repository file tree (up to 400 paths). Every file path suggested in `likely_files` or contribution steps is checked against the actual repository tree; hallucinated paths are dropped.
- **Prompt Character Hard Cap:** Every assembled prompt is strictly validated against a **60,000-character hard cap**. Context exceeding this limit is cleanly truncated and flagged in response warnings.
- **Epistemic Evidence Separation:** Outputs clearly differentiate:
  - `verified`: Direct GitHub REST API facts (labels, timestamps, unassigned status).
  - `inference`: Model evaluations (fit score, estimated hours, matching skills).
  - `unknown`: Missing data (e.g. absent setup guide). Missing data is never converted into a verified negative.
- **Bounded Retries & Deterministic Fallback:** Malformed output triggers at most 1 schema retry. Quota limits (`429`), timeouts, or upstream provider errors never retry blindly-they fall back immediately to deterministic viability ranking.
- **Provider Status:** Evaluated with `models/gemma-4-31b-it` via the Google GenAI SDK. If upstream provider spikes (503/500) occur, PatchLoom honestly surfaces `ai_status: unavailable_or_invalid` and renders deterministic signals without failing the user request.

---

## 3. Architecture

PatchLoom is built as a security-hardened, production-ready modular application orchestrated via Docker Compose:

```mermaid
flowchart TD
    subgraph Client["User Browser"]
        UI["React 18 + TypeScript SPA<br/>(Port 3000)"]
    end

    subgraph Docker["Docker Compose Environment (patchloom-network)"]
        subgraph FrontendContainer["patchloom-frontend (172.28.0.10)"]
            NGINX["Nginx 1.30 Alpine<br/>(Non-Root 'nginx' User)<br/>Port 3000"]
            STATIC["Pre-built Static Bundle<br/>(/usr/share/nginx/html)"]
            NGINX -->|Serves Static UI| STATIC
        end

        subgraph BackendContainer["patchloom-backend (172.28.0.20)"]
            FASTAPI["FastAPI App (Python 3.13 Slim)<br/>(Non-Root 'appuser' UID 10001)<br/>Internal Port 8000 (Exposed Only)"]
            RATELIMIT["SlowAPI Rate Limiter<br/>(Trusted Proxy Validation)"]
            SIGNALS["Viability Engine<br/>(Deterministic Scoring)"]
            PLANNER["First-PR Planner<br/>(Path Grounding & Validation)"]
            FIXTURES["Hermetic Fixtures Loader<br/>(/app/fixtures)"]

            FASTAPI --> RATELIMIT
            FASTAPI --> SIGNALS
            FASTAPI --> PLANNER
            FASTAPI --> FIXTURES
        end

        UI -->|HTTP Requests| NGINX
        NGINX -->|Reverse Proxy /api/ requests| FASTAPI
    end

    subgraph External["External Services (HTTPS Only)"]
        GH["GitHub REST API<br/>(api.github.com)"]
        GEMINI["Google Gemini API<br/>(models/gemma-4-31b-it)"]
    end

    FASTAPI -->|Outbound REST (SSRF Protected)| GH
    FASTAPI -->|Structured JSON Reasoning| GEMINI
```

### Docker Hardening & Network Isolation
- **No Direct Host Exposure for Backend:** Port 8000 is only `expose`d within the internal `patchloom-network` bridge (`172.28.0.0/24`). It is never published to host interfaces. All client access flows through Nginx.
- **Reverse Proxy Gateway:** Nginx listens on port 3000, serves the compiled React single-page app, enforces defensive security headers (`CSP`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`), and proxies `/api/` traffic to `http://backend:8000/api/`.
- **Non-Root Execution:** 
  - Frontend runs as unprivileged user `nginx` (UID 101).
  - Backend runs as dedicated unprivileged user `appuser` (UID 10001).
- **Digest-Pinned Base Images:**
  - Frontend builder: `node:22-alpine` (Node 22 LTS, support through April 2027).
  - Frontend runtime: `nginx:1.30-alpine` (Nginx 1.30 Stable).
  - Backend runtime: `python:3.13-slim` (Python 3.13, support through October 2029).
- **Container Health Checks:** Backend includes automated `HEALTHCHECK` probing `http://127.0.0.1:8000/api/health` via standard Python `urllib` without external curl dependencies.

---

## 4. Technology Stack

| Domain | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18, TypeScript 5, Vite | Fast, type-safe reactive dashboard with zero raw HTML rendering. |
| **Icons & UI** | Lucide React, Custom CSS | Clean, accessible GitHub-inspired UI with custom status badges. |
| **Backend** | Python 3.13, FastAPI, Uvicorn | Async ASGI REST API providing high-throughput endpoint orchestration. |
| **Data Contracts** | Pydantic v2 | Strict request/response validation, OpenAPI specs, and schema generation. |
| **Security & Limits** | SlowAPI, Limits | Sliding-window IP rate limiting with trusted reverse-proxy verification. |
| **AI Reasoning** | Google GenAI SDK, Gemma 4 | `models/gemma-4-31b-it` text-to-JSON reasoning engine for fit and planning. |
| **Containerization** | Docker, Docker Compose | Multi-stage reproducible builds, non-root users, and isolated networking. |
| **Reverse Proxy** | Nginx 1.30 Stable Alpine | High-performance static server, security header enforcement, and API proxy. |

---

## 5. Quick Start (Evaluator Ready in 60 Seconds)

PatchLoom runs completely locally. **No API keys or GitHub tokens are required** to test or verify the application using the included offline fixture mode.

### Option A: Docker Compose (Recommended)

**Prerequisites:** Docker Engine 24+ and Docker Compose v2+.

```bash
# 1. Clone repository
git clone https://github.com/your-username/PatchLoom.git
cd PatchLoom

# 2. (Optional) Configure environment
cp .env.example .env

# 3. Build and launch containers
docker compose up -d --build
```

- **Interactive UI:** Open [http://localhost:3000](http://localhost:3000)
- **Health Check:** [http://localhost:3000/api/health](http://localhost:3000/api/health)
- **View Container Logs:**
  ```bash
  docker compose logs -f
  ```
- **Stop Containers:**
  ```bash
  docker compose down
  ```

---

### Option B: Local Python & Node Setup

**Prerequisites:** Python 3.11+ and Node.js 18+.

#### 1. Backend Setup
From the repository root:
```bash
# Create and activate virtual environment
python -m venv backend/.venv

# Windows (PowerShell):
.\backend\.venv\Scripts\Activate.ps1
# Linux / macOS:
source backend/.venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start backend server
uvicorn app.main:app --app-dir backend --port 8000
```
- API Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- Swagger OpenAPI Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2. Frontend Setup
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
- Development UI: [http://localhost:5173](http://localhost:5173)

---

## 6. Environment Configuration

Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```

| Variable | Required? | Default | Description |
|---|---|---|---|
| `APP_ENV` | Optional | `development` | Runtime mode (`development` or `production`). |
| `DEMO_MODE` | Optional | `0` | Set to `1` to run 100% offline using hermetic repository fixtures. |
| `MODEL_PROVIDER` | Optional | `gemini` | AI reasoning provider (`gemini`). |
| `GEMINI_API_KEY` | Optional | *empty* | Google AI Studio API key for live Gemma 4 fit and planning calls. |
| `GEMMA_MODEL` | Optional | `gemma-4-31b-it` | Target Gemma model ID (`models/gemma-4-31b-it`). |
| `GITHUB_TOKEN` | Optional | *empty* | GitHub Personal Access Token for increased API rate limits (5,000 req/hr). |
| `REQUEST_TIMEOUT_SECONDS` | Optional | `20` | Timeout for outbound GitHub REST calls. |
| `MODEL_TIMEOUT_SECONDS` | Optional | `60` | Timeout for Gemma 4 provider requests. |
| `MAX_PROMPT_CHARS` | Optional | `60000` | Upper limit on assembled prompt character count. |
| `MAX_CANDIDATES` | Optional | `6` | Upper limit on candidate issues evaluated per fit request. |
| `TRUSTED_PROXIES` | Optional | `127.0.0.1,172.28.0.10` | IP/CIDR addresses allowed to pass client IP headers. |

> **Credential Safety:** `GEMINI_API_KEY` and `GITHUB_TOKEN` remain strictly on the server. They are never logged, never returned in API payloads, and never bundled into frontend assets. The backend boots cleanly even when keys are absent.

---

## 7. How to Use PatchLoom

### 1. Enter Repository & Contributor Profile
- Provide any canonical public GitHub repository URL (e.g. `https://github.com/psf/requests`).
- Enter contributor skills (e.g. `Python`, `Sphinx`, `pytest`), preferred languages, experience level (`beginner`, `intermediate`, `advanced`), available hours, and an optional learning goal.
- Click **"Analyze Repository"** or select one of the built-in **Demo Presets**.

### 2. Review Viability Signals & Fit Ranking
- Review the repository overview: star count, open issues, default branch, README presence, and contributing guide status.
- Inspect the shortlisted candidate issues. Each issue card displays:
  - **Deterministic Viability Score (0-100):** Visual status bar and band (`high`, `medium`, `low`).
  - **AI Fit Score:** Contributor suitability percentage calculated by Gemma 4.
  - **Evidence Badges:** Activity recency, assignment status, linked PR evidence, reproduction quality, and setup hints.
  - **Skill Matches & Gaps:** Explicit breakdown of matching skills vs. required knowledge.
  - **Estimated Effort:** Inferred hours with stated assumptions.

### 3. Generate a Grounded First-PR Plan
- Click **"Generate PR Plan"** on any candidate issue.
- PatchLoom fetches fresh issue context, comments, and documentation, then instructs Gemma 4 to draft:
  - A sequenced 3-7 step roadmap categorized into `inspect`, `reproduce`, `implement`, and `test`.
  - Concrete files to inspect, chosen strictly from the repository tree.
  - Setup guidance and test verification instructions (clearly labeled `verified` or `unknown`).
  - A checklist of PR deliverables.
  - A draft pull request title and copy-pasteable Markdown PR description.

---

## 8. Offline Fixture Mode & Representative Datasets

PatchLoom includes 3 committed repository snapshots in `fixtures/` allowing complete zero-network demonstration:

| Preset | Repository | Outcome Demonstrated |
|---|---|---|
| **Scenario A** | `psf/requests` | **Good-fit issues:** High viability, grounded repository paths, verified setup guides, and complete PR plan. |
| **Scenario B** | `expressjs/express` | **Partial evidence:** Stale issues, unverified linked PR status, and missing setup instructions, showing evidence discipline. |
| **Scenario C** | `encode/uvicorn` | **Deterministic fallback:** AI offline or quota exhausted; demonstrates that verified GitHub facts remain fully visible without fabricating AI scores. |

**How to activate:**
- In the Web UI: Click any preset button at the top of the form, or check **"Use Offline Demo / Fixture Mode"**.
- Via API: Include `"demo": true` in the JSON request payload.
- System-wide: Set `DEMO_MODE=1` in `.env`.

---

## 9. Reliability, Safety, and Epistemic Invariants

- **Zero Unsanitized HTML:** The React UI renders strictly through JSX text nodes. The codebase contains zero instances of `dangerouslySetInnerHTML`.
- **SSRF & URL Restrictions:** Only canonical HTTPS URLs matching `https://github.com/OWNER/REPO` are accepted. Outbound HTTP requests disable automatic redirect following and connect exclusively to `api.github.com`.
- **Prompt Injection Resilience:** Repository metadata, descriptions, comments, and file paths are treated as untrusted user data. They are wrapped in `<untrusted_issue_data>` delimiters with defanged tag breakout protection.
- **Epistemic Invariant (No False Negatives):** Missing or unqueried data is labeled `unknown` or `none_detected`. PatchLoom never turns an incomplete lookup into a verified negative.
- **Deterministic Fallback Transparency:** If Gemma 4 encounters rate limits or upstream provider errors, PatchLoom honestly surfaces `ai_status: unavailable_or_invalid` with clear explanations. Fallback scores are never disguised as AI results.

---

## 10. Future Scope
### Practice Issues & PRs

PatchLoom could recommend similar past issues and pull requests as learning resources, helping contributors understand relevant concepts, implementation patterns, and previous solutions before tackling an issue themselves. This would turn issue discovery into a guided learning experience, making open-source contribution more approachable for beginners.

---

## 11. Development and Testing

### Backend Unit & Integration Tests (100% Offline)
The backend test suite contains **86 tests** with zero real model or network calls:
```bash
# Run full pytest suite
.\backend\.venv\Scripts\pytest backend/tests -v
```

Test coverage includes:
- Strict GitHub URL validation and SSRF defenses (`test_url_validation.py`)
- Deterministic signal scoring, penalties, and clamping (`test_signals.py`)
- Safe prompt construction and 60,000-character cap enforcement (`test_analysis.py`)
- File path grounding and hallucination dropping (`test_planner.py`, `test_hardening.py`)
- Rate limiting, IP spoofing defenses, and security headers (`test_hardening.py`)
- Offline fixtures and demo loader verification (`test_fixtures.py`)
- Schema compatibility and transient error retry mapping (`test_provider.py`)

### Frontend Typecheck & Production Build
```bash
cd frontend
npm run build
```
Generates clean production assets into `frontend/dist` with 0 TypeScript or packaging errors.

---

## 12. Open Source & Credits

- **License:** Released under the [MIT License](LICENSE).
- **Model:** Powered by Google's [Gemma 4](https://ai.google.dev/gemma) (`gemma-4-31b-it`) via the Google GenAI SDK.
- **Built For:** Hacktoberfest Hack Day 2026 - Theme 2: AI for Open Innovation.
- **Contributions:** Issues and pull requests are welcome. Please ensure all 86 offline tests pass before submitting changes.
