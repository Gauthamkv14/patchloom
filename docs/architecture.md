# PatchLoom Architecture & System Design

This document details the architecture, data flows, scalability boundaries, and extension patterns of **PatchLoom**.

---

## 1. System Architecture Diagram

```mermaid
flowchart TD
    User["Contributor (Web Browser)"] -->|Canonical URL & Profile| Frontend["React + Vite + TypeScript Frontend"]
    
    subgraph FastAPI Backend ["PatchLoom FastAPI Backend (Port 8000)"]
        API["Route Layer (api.py)"]
        Parser["Strict URL Parser & Guardrails (github_client.py)"]
        Signals["Deterministic Signals Engine (signals.py)"]
        PromptBuilder["Prompt Builder with XML Delimiters (prompts.py)"]
        Grounding["Path Grounding & Validation Engine (analysis.py / planner.py)"]
        Fixtures["Offline Fixture Loader (fixtures_loader.py)"]
        
        subgraph Providers ["Model Provider Layer"]
            ProviderBase["ModelProvider (base.py)"]
            Gemini["GeminiProvider: models/gemma-4-31b-it"]
        end
    end

    subgraph External ["External Services"]
        GitHub["GitHub REST API (https://api.github.com)"]
        GoogleGenAI["Google Gemini API (Gemma 4)"]
    end

    subgraph OfflineFixtures ["Local Fixture Storage"]
        FixtureFiles["Committed Snapshots (fixtures/*.json)"]
    end

    Frontend -->|POST /api/analyze| API
    Frontend -->|POST /api/plan| API
    
    API --> Parser
    Parser -->|Fetch Metadata, Tree, Issues, Docs| GitHub
    Parser -.->|Demo Mode Active| Fixtures
    Fixtures --> FixtureFiles

    GitHub --> Signals
    Signals -->|Pre-filtered Candidates (Max 12)| PromptBuilder
    PromptBuilder --> ProviderBase
    ProviderBase --> Gemini
    Gemini -->|1 Batched Fit Assessment| GoogleGenAI
    Gemini -->|1 Bounded Plan Call| GoogleGenAI
    
    GoogleGenAI --> Grounding
    Grounding -->|Drop Hallucinated Paths| API
    API -->|Ranked Issues + Evidence Badges| Frontend
    API -->|First-PR Checklist & Draft PR| Frontend
```

---

## 2. Core Architectural Principles

1. **Epistemic Discipline (Facts vs. Inference):**
   - Direct repository data (timestamps, assignees, commit logs, file paths) is verified and immutable.
   - Model assessments (fit score, estimated hours, checklist steps) are strictly labeled as inferences.
   - Incomplete checks are explicitly labeled `unknown` or `none_detected`. An unverified check is never converted into a verified negative.
2. **Strictly Non-Agentic & Read-Only:**
   - PatchLoom acts solely as an advisor. It has zero tools, zero code execution, and zero write privileges.
   - It never clones repositories, executes shell scripts, creates branches, or opens pull requests.
3. **Defense-in-Depth Against Prompt Injection:**
   - Repository descriptions, issue titles, issue comments, and documentation are untrusted user input.
   - All untrusted content is structurally wrapped within `<untrusted_issue_data>` XML delimiters.
   - System prompts instruct Gemma 4 to disregard instructions embedded within untrusted content.
4. **Hermetic Offline Capability:**
   - The application can be evaluated with zero external network connectivity using committed fixtures (`DEMO_MODE=1` or `demo=true`).

---

## 3. Scalability & Large-Repository Handling

Handling large open-source repositories (e.g. `kubernetes/kubernetes` or `torvalds/linux`) requires aggressive bounding at every layer:

### A. Bounded Model Calls
- **Single Batched Fit Call:** PatchLoom never makes $N$ individual model calls for $N$ issues. Up to 12 candidate issues are evaluated in **exactly 1 batched prompt**.
- **Single Plan Call:** When a user selects an issue, exactly **1 plan call** is executed.
- **Strict Budget Hard Cap:** Prompts are restricted to a **60,000-character hard cap**. If context exceeds this budget, file trees and issue descriptions are conservatively truncated.

### B. Bounded Tree & Issue Ingestion
- **File Tree Bounding:** GitHub's git tree API is fetched with recursive mode, but the local client caps the retained tree at **400 relevant paths**, excluding binary assets, vendor files, and lockfiles. Truncation flags are explicitly returned in the API payload.
- **Issue Bounding:** Issue pagination is strictly bounded to the top 60 open issues across at most 2 pages. PRs are excluded upstream via GitHub issue payload inspection.

### C. Stateless Design
- The backend maintains zero database state and no persistent user sessions.
- In-memory short-lived caching (5 minutes) avoids redundant GitHub requests for repeated analyses during exploration.

---

## 4. Extending PatchLoom

### A. How to Add a New Viability Signal
All deterministic viability heuristics are centralized in [`backend/app/signals.py`](file:///c:/Users/User/OneDrive/Desktop/Projects/PatchLoom/backend/app/signals.py):

1. **Define the Signal Function:**
   Implement a pure function calculating the penalty or score based on GitHub data:
   ```python
   def evaluate_has_reproduction_steps(body: str) -> SignalEvidence:
       has_repro = any(k in body.lower() for k in ("steps to reproduce", "reproduction", "repro:"))
       return SignalEvidence(
           status="verified",
           source="issue_body_heuristic",
           value="Reproduction steps documented" if has_repro else "No explicit reproduction steps",
       )
   ```
2. **Register in `compute_viability_signals`:**
   Add the signal to the candidate's signals dictionary and adjust the viability penalty if applicable.
3. **Clamp and Test:**
   Add a unit test in [`backend/tests/test_signals.py`](file:///c:/Users/User/OneDrive/Desktop/Projects/PatchLoom/backend/tests/test_signals.py) verifying that the score remains clamped in $[0, 100]$ and maps to the appropriate band (`high`, `medium`, `low`).

### B. How to Add a New Model Provider
Model providers implement the abstract interface in [`backend/app/providers/base.py`](file:///c:/Users/User/OneDrive/Desktop/Projects/PatchLoom/backend/app/providers/base.py):

1. **Implement `ModelProvider`:**
   ```python
   from app.providers.base import ModelProvider

   class LocalOllamaProvider(ModelProvider):
       async def generate_json(self, prompt: str, schema: type[BaseModel], system_instruction: str = "") -> BaseModel:
           # Call local endpoint, handle timeouts, and parse response into schema
           ...
   ```
2. **Handle Errors Safely:**
   Map provider exceptions to PatchLoom's standard errors (`QuotaExceededError`, `AuthenticationError`, `ModelTimeoutError`, `InvalidModelOutputError`).
3. **Register Provider:**
   Instantiate the provider in `analysis.py` and `planner.py` when `provider_name="ollama"`.

---

## 5. Realistic 100× Scaling Discussion (Future Work)

At 100× active users or high concurrent traffic, PatchLoom's architecture would encounter specific upstream bottlenecks. Below is an honest engineering analysis of these limits and the planned future architecture:

### Upstream Bottlenecks

1. **GitHub REST Rate Limits:**
   - *Current Status:* Unauthenticated requests are limited to 60/hr per IP; personal tokens provide 5,000/hr.
   - *At 100× Scale:* Shared personal tokens or IP pools will hit rate limits under multi-user concurrency.
   - *Future Work Solution:* Transition to a **GitHub App installation** model. GitHub Apps receive 15,000 requests/hr per installation and distribute rate limits across user organizations rather than a single server token.

2. **Model Provider Quotas & Latency:**
   - *Current Status:* Gemini API tier quotas limit requests per minute (RPM) and tokens per minute (TPM).
   - *At 100× Scale:* Bursts of concurrent users clicking "Analyze" or "Plan" will encounter `429 QuotaExceededError`.
   - *Future Work Solution:* Deploy a **multi-provider load balancer with fallback routing** (e.g., routing to self-hosted Gemma 4 instances on vLLM or secondary API keys when primary quota thresholds are approached).

3. **Synchronous Request-Response Lifecycle:**
   - *Current Status:* A live analysis request takes ~2–4 seconds (GitHub fetching + Gemma batched fit reasoning).
   - *At 100× Scale:* Holding open HTTP connections during AI generation can exhaust ASGI worker pools (e.g. Uvicorn worker starvation).
   - *Future Work Solution:*
     - **Asynchronous Task Queue:** Move repository ingestion and model reasoning into background workers using Celery or RQ backed by Redis.
     - **Real-Time Updates:** Deliver progress steps (ingestion -> signals -> AI fit) to the frontend via WebSockets or Server-Sent Events (SSE).
     - **Distributed Cache:** Replace the in-memory cache with an edge-tier Redis cluster storing repository tree snapshots and precomputed candidate signals.

> **Clarification:** These architectural enhancements represent planned future work for production-scale deployment. The P0 MVP deliberately employs a stateless, single-service FastAPI architecture to ensure complete local reproducibility and zero external infrastructure dependencies.
