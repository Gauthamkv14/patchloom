# PatchLoom

> **From "I want to contribute" to a repo-grounded plan for a first PR.**

PatchLoom matches new open-source contributors to viable GitHub issues using deterministic repository viability signals and Gemma 4 reasoning. It bridges the gap between wanting to contribute and knowing where to start without overwhelming the contributor.

Built for **Hacktoberfest Hack Day (Theme 2: AI for Open Innovation)**.

---

## 60-Second Evaluator Quickstart

You can run PatchLoom completely locally in under 60 seconds. **No API keys or GitHub tokens are required** to run the app or verify the complete workflow via offline fixture mode.

### 1. Prerequisites
- **Python 3.11+** (tested on Python 3.13)
- **Node.js 18+** & **npm** (tested on Node v25 / npm 11)

### 2. Backend Setup
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
Backend health check is available at: [http://localhost:8000/api/health](http://localhost:8000/api/health)  
Interactive OpenAPI documentation is available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Frontend Setup
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the interactive UI at: [http://localhost:5173](http://localhost:5173)

---

## Environment Variables

Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```

| Variable | Required? | Default | Description |
|---|---|---|---|
| `APP_ENV` | Optional | `development` | Environment mode (`development` or `production`). |
| `DEMO_MODE` | Optional | `0` | Set to `1` to force server-wide hermetic fixture mode (no outbound calls). |
| `MODEL_PROVIDER` | Optional | `gemini` | Model provider (`gemini` supported in P0). |
| `GEMINI_API_KEY` | Optional | *empty* | Google AI Studio key for live Gemma 4 fit and planning calls. Kept strictly server-side. |
| `GEMMA_MODEL` | Optional | `gemma-4-31b-it` | Target Gemma model ID (normalized to `models/gemma-4-31b-it` by SDK). |
| `GITHUB_TOKEN` | Optional | *empty* | Personal GitHub token for higher REST rate limits (60/hr -> 5,000/hr). |
| `REQUEST_TIMEOUT_SECONDS` | Optional | `20` | Timeout for outbound GitHub REST requests. |
| `MODEL_TIMEOUT_SECONDS` | Optional | `60` | Timeout for Gemma 4 provider requests. |
| `MAX_PROMPT_CHARS` | Optional | `60000` | Hard cap on assembled prompt characters sent to the model. |
| `MAX_CANDIDATES` | Optional | `12` | Maximum issues evaluated per fit reasoning request. |

> **Startup Invariant:** The application starts and runs cleanly even if `GEMINI_API_KEY` and `GITHUB_TOKEN` are empty. When keys are absent, `/api/health` reports status, and `/api/analyze` gracefully provides deterministic viability ranking without failing.

---

## Offline Fixture Mode & Demo Presets

PatchLoom includes 3 committed repository snapshots in `fixtures/` allowing zero-network evaluation:

1. **Scenario A (Good Fit):** `https://github.com/psf/requests` — High-fit candidate issues with verified grounded files, setup/test guides, and a complete first-PR plan.
2. **Scenario B (Partial Evidence):** `https://github.com/expressjs/express` — Stale issues, unknown linked PR status, and missing setup instructions, demonstrating evidence distinction.
3. **Scenario C (Deterministic Fallback):** `https://github.com/encode/uvicorn` — AI offline or quota exhausted; demonstrates that verified GitHub facts remain visible without fabricating AI scores.

To use fixture mode:
- Check **"Use Offline Demo / Fixture Mode"** in the web UI, or click any of the one-click **Demo Presets** at the top of the form.
- Or pass `"demo": true` in the JSON request body.
- Or set `DEMO_MODE=1` in your `.env`.

---

## `curl` API Example

Analyze a public repository using the REST API:

```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/psf/requests",
    "profile": {
      "skills": ["python", "documentation"],
      "preferred_languages": ["python"],
      "experience_level": "beginner",
      "available_hours": 3.0,
      "learning_goal": "Learn Sphinx documentation workflows"
    },
    "demo": true
  }'
```

Generate a first-PR plan for a specific issue:
```bash
curl -X POST "http://localhost:8000/api/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/psf/requests",
    "issue_number": 6542,
    "profile": {
      "skills": ["python", "documentation"],
      "preferred_languages": ["python"],
      "experience_level": "beginner",
      "available_hours": 3.0
    },
    "demo": true
  }'
```

---

## How PatchLoom Uses Gemma 4

PatchLoom utilizes **Gemma 4** (`gemma-4-31b-it`) strictly as a structured reasoning engine with zero tools, zero code execution, and zero write privileges.

### 1. Verified Model Configuration
- **Model ID:** `models/gemma-4-31b-it` (via the official `google-genai` Python SDK).
- **M3 Smoke-Test Verified Fact:** The Gemini API server endpoint returns `500 INTERNAL` when passing `config={'system_instruction': '...'}` to Gemma 4. As documented in `PROGRESS.md`, fixed system instructions are safely prepended directly to the user prompt block.
- **Structured JSON Output:** Model responses are strictly constrained using Pydantic schemas via `response_mime_type="application/json"` and `response_schema`.

### 2. Strictly Bounded Model Calls
- **Fit Assessment:** Exactly **1 batched model call** evaluates up to 12 pre-filtered candidate issues simultaneously, preventing token waste and latency creep.
- **Plan Generation:** Exactly **1 model call** produces a 3–7 step first-PR plan for the contributor's chosen issue.
- **Budget Hard Cap:** Every assembled prompt is strictly validated against a **60,000-character hard cap**. If context exceeds this budget, issues and file trees are truncated safely and warned in the response.

### 3. File Path Grounding & Hallucination Mitigation
Gemma 4 is provided with the ingested repository file tree (capped at 400 paths). Every file path suggested by the model is validated against this real set:
- Hallucinated paths are stripped out.
- Path modifications are annotated in the issue risks.
- If no suggested files exist in the tree, fallback paths are selected from the actual repository tree.

### 4. Deterministic Error & Quota Handling
- **Invalid Output:** If the model returns malformed JSON or schema errors, PatchLoom triggers **at most 1 retry**.
- **Quota / Auth / Timeout:** Upon `429 QuotaExceededError`, `403 AuthenticationError`, or `ModelTimeoutError`, PatchLoom **never retries blindly**. It immediately falls back to deterministic heuristic rankings or plans, preserving all verified GitHub facts.
- **Zero Fabrication:** If AI reasoning fails or is offline, fit scores are returned as `null` and `ai_status` is marked `unavailable_or_invalid`. Verified facts remain 100% visible.

### 5. Server-Side Key Isolation
The `GEMINI_API_KEY` is loaded exclusively in the backend runtime via `app/config.py`. It is never transmitted to the browser, never bundled into frontend assets, never returned in API payloads, and never logged.

---

## Evidence Provenance & Badge System

PatchLoom enforces strict epistemic discipline:

- <span style="color:#34d399">●</span> **Verified Fact:** Direct, deterministic data from GitHub API endpoints or local rule checks (e.g., timestamps, unassigned status, README presence).
- <span style="color:#fbbf24">●</span> **AI Assessment / Inference:** Subjective evaluations generated by Gemma 4 (e.g., skill fit score, estimated hours, likely files).
- <span style="color:#94a3b8">●</span> **Unknown / Not Checked:** Incomplete lookups or missing repository guidance. Missing data is never treated as a verified negative (e.g., an unqueried PR check is `unknown`, not "verified absent").

---

## Running Automated Tests

Run the complete offline test suite (64 tests):
```bash
.\backend\.venv\Scripts\pytest backend/tests -v
```

Run frontend production build & typecheck:
```bash
cd frontend
npm run build
```

---

## Limitations

- **Public Repositories Only:** PatchLoom accepts only canonical `https://github.com/OWNER/REPO` URLs. Private repositories, OAuth user flows, and enterprise GitHub hosts are out of scope.
- **Read-Only / Non-Agentic:** PatchLoom does not create branches, commit code, open pull requests, run builds, or execute commands.
- **GitHub REST Limits:** Unauthenticated requests share GitHub's IP pool limit (60 requests/hr). Providing a personal `GITHUB_TOKEN` in `.env` increases headroom to 5,000 requests/hr.

---

## Architecture & Project Structure

```text
PatchLoom/
|-- AGENTS.md                  # Working contract and invariants for AI agents
|-- PROGRESS.md                # Milestone execution log and decisions ledger
|-- README.md                  # Evaluator quickstart and documentation
|-- backend/
|   |-- requirements.txt       # Pinned backend dependencies
|   |-- app/
|   |   |-- main.py            # FastAPI entry point & CORS configuration
|   |   |-- api.py             # Route handlers (/api/health, /api/analyze, /api/plan)
|   |   |-- config.py          # Typed Pydantic settings & .env loading
|   |   |-- schemas.py         # Request, response, and evidence data models
|   |   |-- github_client.py   # Strict URL parser & bounded GitHub REST client
|   |   |-- signals.py         # Deterministic viability engine & scoring
|   |   |-- prompts.py         # Delimited prompt builders & schema schemas
|   |   |-- analysis.py        # Batched fit ranking orchestration
|   |   |-- planner.py         # Grounded first-PR plan generator
|   |   |-- fixtures_loader.py # Zero-network offline fixture loader
|   |   `-- providers/         # Model provider abstraction (gemini.py)
|   `-- tests/                 # 100% offline pytest suite (64 tests)
|-- frontend/
|   |-- package.json           # React 18, Vite, TypeScript
|   `-- src/
|       |-- App.tsx            # Main dashboard shell
|       |-- types.ts           # Frontend TypeScript schemas
|       `-- components/        # InputForm, IssueCard, PlanModal, EvidenceLegend
|-- fixtures/                  # Committed offline demo datasets (Scenarios A, B, C)
`-- docs/
    |-- architecture.md        # Architecture diagrams, scalability, and extension guide
    `-- pitch-notes.md         # 1-page presentation and pitch notes
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
