---
description: 
alwaysApply: true
---

# Simulator Repo Instructions (Codex)

Keep project docs current:
- When a change affects user-facing behavior (Docker services/ports, auth/roles/default admin, CLI flows/flags, API routes, env vars, troubleshooting), update docs in the same patch.
- Primary docs to maintain: `README.md` (canonical overview) and `SIMULATOR_GUIDE.md` (deep operational reference).

Session-start habit for non-trivial work:
- Read `README.md`, `SIMULATOR_GUIDE.md`, and `ARCHITECTURE.md` before implementing.

Context hygiene:
- If a user prompt is clearly unrelated to this repo/problem context, advise moving to a new chat immediately and do not proceed.
