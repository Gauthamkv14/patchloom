# PatchLoom Pitch Notes & Hackathon Presentation Guide

> **Theme:** AI for Open Innovation  
> **Tagline:** From "I want to contribute" to a repo-grounded plan for a first PR.

---

## 1. The Problem & Target User (15 Seconds)

**The Problem:** Aspiring open-source contributors face a wall of uncertainty. Over 60% of beginners abandon their first contribution attempt because issues labeled "good first issue" are frequently stale, already silently claimed, lacking reproduction steps, or require deep internal codebase knowledge. Contributors waste hours trying to set up broken environments or working on issues someone else already solved.

**The Target User:** Students, bootcamp grads, and software engineers seeking to make their first meaningful open-source contribution within a realistic, constrained time budget (e.g. 2–5 hours).

---

## 2. Why AI — And Where AI Must NOT Be Used (30 Seconds)

- **Where AI Shines:** Gemma 4 acts as an empathetic technical mentor. It bridges the semantic gap between a contributor's skills (e.g., Python + testing) and an issue's actual scope, estimating realistic effort and drafting a conservative first-PR checklist.
- **Where AI Must NOT Be Used:** AI must never guess objective facts. PatchLoom uses deterministic Python code to verify whether an issue has assignees, whether PRs are linked, when it was last updated, and whether setup/test guides exist. 
- **Epistemic Discipline:** Every fact in the UI is badged: **Verified Fact**, **AI Assessment / Inference**, or **Unknown / Not Checked**. We never hallucinate certainty.

---

## 3. Live Demo Flow (2 Minutes)

Follow this precise sequence during the demo (or use the one-click Demo Presets for zero-network reliability):

1. **The Hook (15s):**  
   *"Every developer wants to contribute to open source during Hacktoberfest, but finding a viable first issue is like finding a needle in a haystack. PatchLoom changes that."*
2. **Enter Profile & Analyze (15s):**  
   - Enter `https://github.com/psf/requests`.
   - Contributor Profile: Python, documentation, beginner experience, 3 hours available.
   - Click **Analyze Repository**.
3. **Compare Candidates & Viability Signals (30s):**  
   - Show the ranked cards. Issue #6542 ranks #1 (Final Score 93.8) combining high viability (92) and AI skill fit (95).
   - Point to the **Evidence Legend**: green for verified facts, yellow for AI inferences, gray for unknowns.
   - Expand the signals: show that "Unassigned", "No linked PR", and "Docs present" were checked deterministically from GitHub.
4. **Demonstrate Warning Transparency (20s):**  
   - Switch to **Scenario B (`expressjs/express`)**. Show how issue #5102 displays a medium viability warning because the issue is stale (>90 days) and the linked PR check is unverified.
   - Highlight: *"PatchLoom warns you before you waste your weekend on an unviable issue."*
5. **Grounded First-PR Plan (30s):**  
   - Click **Plan First PR** on Issue #6542.
   - Show the 3-step checklist, grounded specifically in `docs/user/advanced.rst`.
   - Show that setup & test commands are validated against the repository docs.
   - Click **Copy Checklist** and **Copy PR Draft** (showing visual "Copied!" feedback).
   - Point out the non-agentic disclaimer: *"PatchLoom guides you; it doesn't pretend to write code for you."*
6. **Zero-Network Demo Fallback:**  
   - If the conference Wi-Fi fails or GitHub rate limits trigger, toggle **"Use Offline Demo / Fixture Mode"**. The app immediately runs from committed hermetic snapshots with zero dropped frames.

---

## 4. The 100× Scaling Answer (30 Seconds)

*"What happens when 10,000 developers use PatchLoom simultaneously?"*

- **The Real Bottlenecks:** GitHub REST rate limits (60/hr unauthenticated, 5,000/hr personal token) and model concurrency quotas.
- **Our Scalable Foundation:**
  1. **Stateless Backend:** Zero database dependencies; can scale horizontally across serverless containers.
  2. **Bounded Compute:** Exactly 1 batched model call per analysis (never $N$ calls), with a strict 60k character prompt cap and 400-path tree ceiling.
- **Future Production Architecture:**
  - Transition from personal tokens to a **GitHub App** (15,000 requests/hr per installation).
  - Offload ingestion and reasoning to an asynchronous **Redis/Celery task queue** with WebSockets.
  - Distribute model requests across a self-hosted Gemma 4 vLLM cluster with automatic Gemini API fallback.

---

## 5. How Others Install and Extend PatchLoom (15 Seconds)

- **Get Started in 60 Seconds:** Clean, single-command startup for FastAPI and Vite with zero required secrets or external services.
- **Adding a Signal:** Write a pure Python heuristic function in `backend/app/signals.py` and register it in `compute_viability_signals()`.
- **Adding a Provider:** Implement the typed `ModelProvider` abstract class in `backend/app/providers/base.py` for Ollama, vLLM, or Anthropic.

---

## 6. Closing Statement

> *"PatchLoom doesn't try to replace human contributors with autonomous bots. It gives human contributors the grounded confidence, repository facts, and step-by-step clarity they need to submit their very first pull request."*
