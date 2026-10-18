# PatchLoom Demo Fixtures

This directory contains committed, sanitized repository snapshots used for:
1. Automated offline testing without live GitHub or Gemini network calls.
2. The zero-network live demo fallback when `DEMO_MODE=1` or `demo=true`.

Each fixture case contains:
- Ingested repository metadata
- Filtered candidate issues
- Extracted documentation excerpts (README, CONTRIBUTING)
- Canonical file tree subset (capped at 400 paths)
- Pre-computed viability signals and validated response payloads
