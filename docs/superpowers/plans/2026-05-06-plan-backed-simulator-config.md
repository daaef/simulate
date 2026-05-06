# Plan-Backed Simulator Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move non-sensitive simulator defaults into validated JSON plans while preserving CLI command syntax and adding GUI plan management.

**Architecture:** Extend `run_plan.py` and `config.py` so plan files can carry additional non-sensitive sections, with CLI flags still taking precedence. Add a small FastAPI plan-store surface backed by `runs/gui-plans/`, then add a protected Next.js configuration page for editing those plan files.

**Tech Stack:** Python 3, FastAPI, Pydantic, unittest, Next.js 14, React 18, TypeScript.

---

### Task 1: Plan Schema And Config Precedence

**Files:**
- Modify: `run_plan.py`
- Modify: `config.py`
- Modify: `__main__.py`
- Test: `tests/test_simulate.py`

- [ ] Add failing tests proving extended plan sections are retained and applied to config.
- [ ] Add failing tests proving sensitive keys are rejected from plan JSON.
- [ ] Add failing tests proving explicit CLI flags can preserve values over plan defaults.
- [ ] Extend `RunPlan` with additive non-sensitive sections.
- [ ] Add plan default application in `config.py`.
- [ ] Update CLI argument application so plan defaults sit between CLI flags and `.env`.
- [ ] Run focused simulator config tests.

### Task 2: GUI Plan Store API

**Files:**
- Create: `api/app/simulation_plans/__init__.py`
- Create: `api/app/simulation_plans/models.py`
- Create: `api/app/simulation_plans/routes.py`
- Create: `api/app/simulation_plans/service.py`
- Modify: `api/app/main.py`
- Test: `tests/test_web_api.py`

- [ ] Add failing API tests for create/list/read/update/delete plan behavior.
- [ ] Add failing API test proving viewer users cannot write plans.
- [ ] Implement file-backed plan storage under `runs/gui-plans/`.
- [ ] Validate plan content through `run_plan.py` before write.
- [ ] Return launchable relative paths such as `runs/gui-plans/<id>.json`.
- [ ] Run focused web API tests.

### Task 3: GUI Configuration Page

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/app/(app)/layout.tsx`
- Create: `web/src/app/(app)/config/page.tsx`

- [ ] Add API client types and functions for simulation plans.
- [ ] Add a protected `Config` navigation item.
- [ ] Build a plan list plus JSON editor with load, new, save, and delete actions.
- [ ] Surface server validation errors clearly without exposing secrets.
- [ ] Run the web build.

### Task 4: Docs And Validation

**Files:**
- Modify: `README.md`
- Modify: `SIMULATOR_GUIDE.md`
- Modify: `ARCHITECTURE.md`
- Modify: `implementation/tracker/*`

- [ ] Document the `.env` versus plan split.
- [ ] Document the new plan sections and GUI plan workflow.
- [ ] Run focused tests, full API/simulator tests as feasible, compile checks, web build, and whitespace checks.
- [ ] Record results and blockers in the tracker.
