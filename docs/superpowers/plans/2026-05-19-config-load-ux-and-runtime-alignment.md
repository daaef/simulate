# Config Load UX and Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved Config/load UX behavior, deterministic load worker assignment, and per-flow operator documentation without breaking existing API contracts.

**Architecture:** Keep the public run-create and profile/schedule API contract unchanged, then apply focused internal fixes in three layers: backend plan loading, frontend launcher/config UX, and simulator load-runtime assignment. Add pure helper modules for testability, back changes with targeted TDD, and merge operator docs so `SIMULATOR_GUIDE.md` is canonical while `README.md` stays quickstart-first.

**Tech Stack:** Python 3 (`unittest`, FastAPI backend, simulator runtime), TypeScript/React (Next.js + Vitest), Markdown docs.

---

## File Structure and Responsibilities

- `api/app/main.py`: simulation plan read behavior (`sim-actors` default id handling) and API parity.
- `tests/test_web_api.py`: API regression tests for default-plan load behavior.
- `web/src/lib/config-plan-draft.ts` (new): pure functions for `New` draft cloning from loaded editor/plan.
- `web/src/lib/config-plan-draft.test.ts` (new): unit tests for draft-clone semantics.
- `web/src/app/(app)/config/page.tsx`: tabbed Config UX (`Plans`, `Email`, `Integration mappings`) and draft behavior wiring.
- `web/src/lib/load-mode-controls.ts` (new): load-only UI helpers (field visibility + pace presets).
- `web/src/lib/load-mode-controls.test.ts` (new): pace preset + visibility unit tests.
- `web/src/components/runs/RunLaunchPanel.tsx`: hide trace controls in load mode, add pace selector, keep command truth.
- `load_worker_assignment.py` (new): deterministic user assignment mapping for load workers.
- `tests/test_load_worker_assignment.py` (new): first-`N` and round-robin worker assignment tests.
- `user_sim.py`: add optional `worker_count` parameter to avoid implicit `N_USERS` multiplication per session.
- `__main__.py`: integrate assignment mapping and launch exactly `N_USERS` workers across selected sessions.
- `docs/flows/README.md` (new): flow-doc index and usage conventions.
- `docs/flows/<flow>.md` (new, one per flow): comprehensive operator docs for every GUI flow option.
- `scripts/check_flow_docs.py` (new): parity check between `FLOW_PRESETS` and `docs/flows/*.md`.
- `README.md`: reduce to quickstart + links.
- `SIMULATOR_GUIDE.md`: canonical operator semantics + links to per-flow docs.

---

### Task 1: Backend default `sim_actors` load path support

**Files:**
- Modify: `api/app/main.py`
- Modify: `tests/test_web_api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing API tests for default plan id**

```python
# tests/test_web_api.py (inside SimulationPlansApiTests)
def test_get_default_sim_actors_plan_by_id(self) -> None:
    response = self.client.get("/api/v1/simulation-plans/sim-actors")
    self.assertEqual(response.status_code, 200)
    plan = response.json()["plan"]
    self.assertEqual(plan["id"], "sim-actors")
    self.assertEqual(plan["path"], "sim_actors.json")
    self.assertIn("content", plan)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_web_api.SimulationPlansApiTests.test_get_default_sim_actors_plan_by_id -v`  
Expected: FAIL with HTTP 404 or missing default-plan handling.

- [ ] **Step 3: Implement default plan branch in simulation-plan getter**

```python
# api/app/main.py

def _get_simulation_plan_payload(plan_id: str) -> dict[str, Any]:
    if plan_id == "sim-actors":
        default_plan = _default_sim_actors_plan_payload()
        if default_plan is None:
            raise HTTPException(status_code=404, detail="Simulation plan 'sim-actors' not found.")
        return {"plan": default_plan}
    return {"plan": _simulation_plan_payload(_simulation_plan_path(plan_id))}
```

- [ ] **Step 4: Run test + nearby suite to verify pass**

Run: `python3 -m unittest tests.test_web_api.SimulationPlansApiTests -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/main.py tests/test_web_api.py
git commit -m "fix: support loading default sim_actors plan by id"
```

---

### Task 2: Add pure draft-clone helpers for Config `New`

**Files:**
- Create: `web/src/lib/config-plan-draft.ts`
- Create: `web/src/lib/config-plan-draft.test.ts`
- Test: `web/src/lib/config-plan-draft.test.ts`

- [ ] **Step 1: Write failing tests for clone behavior**

```ts
// web/src/lib/config-plan-draft.test.ts
import { describe, expect, it } from "vitest";
import { buildNewPlanDraft } from "./config-plan-draft";

describe("buildNewPlanDraft", () => {
  it("clones parsed editor JSON when editor is valid", () => {
    const draft = buildNewPlanDraft('{"name":"Loaded","users":[{"phone":"+1"}]}', { schema_version: 2 });
    expect(draft.content).toEqual({ name: "Loaded", users: [{ phone: "+1" }] });
  });

  it("falls back to selected content when editor JSON is invalid", () => {
    const draft = buildNewPlanDraft("{bad", { schema_version: 2, users: [{ phone: "+2" }] });
    expect(draft.content).toEqual({ schema_version: 2, users: [{ phone: "+2" }] });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- src/lib/config-plan-draft.test.ts`  
Expected: FAIL (`Cannot find module './config-plan-draft'`).

- [ ] **Step 3: Implement helper module**

```ts
// web/src/lib/config-plan-draft.ts
import type { SimulationPlanContent } from "./api";

export type PlanDraft = {
  name: string;
  content: SimulationPlanContent;
};

export function buildNewPlanDraft(
  editorValue: string,
  fallbackContent: SimulationPlanContent,
  nextName = "Plan Copy",
): PlanDraft {
  try {
    const parsed = JSON.parse(editorValue) as SimulationPlanContent;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { name: nextName, content: parsed };
    }
  } catch {
    // fall through to fallback content
  }
  return { name: nextName, content: fallbackContent };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd web && npm run test -- src/lib/config-plan-draft.test.ts`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/config-plan-draft.ts web/src/lib/config-plan-draft.test.ts
git commit -m "test: add config draft clone helper coverage"
```

---

### Task 3: Convert Config page to tabs and wire clone-from-loaded `New`

**Files:**
- Modify: `web/src/app/(app)/config/page.tsx`
- Modify: `web/src/components/config/IntegrationMappingsPanel.tsx` (only if props/composition needed)
- Test: `web/src/lib/config-plan-draft.test.ts`

- [ ] **Step 1: Add a failing behavior assertion around new draft naming/content helper usage**

```ts
// web/src/lib/config-plan-draft.test.ts
it("returns a predictable draft name for UI new flow", () => {
  const draft = buildNewPlanDraft('{"schema_version":2}', { schema_version: 2 }, "Daily Doctor Plan (Copy)");
  expect(draft.name).toBe("Daily Doctor Plan (Copy)");
});
```

- [ ] **Step 2: Run the test to verify fail state**

Run: `cd web && npm run test -- src/lib/config-plan-draft.test.ts`  
Expected: FAIL if helper/new-name behavior is not wired.

- [ ] **Step 3: Implement tabs + `New` draft wiring in Config page**

```tsx
// web/src/app/(app)/config/page.tsx (core intent)
type ConfigTab = "plans" | "email" | "integrations";
const [activeTab, setActiveTab] = useState<ConfigTab>("plans");

function startNewPlan() {
  const fallback = selectedPlan?.content ?? PLAN_TEMPLATE;
  const nextName = selectedPlan ? `${selectedPlan.name} (Copy)` : "Daily Doctor Plan";
  const draft = buildNewPlanDraft(editorValue, fallback, nextName);
  setSelectedPlanId(null);
  setPlanName(draft.name);
  setEditorValue(JSON.stringify(draft.content, null, 2));
  setMessage(null);
  setError(null);
}

// render tab buttons and tab panels
```

- [ ] **Step 4: Run web tests + build**

Run: `cd web && npm run test -- src/lib/config-plan-draft.test.ts && npm run build`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/(app)/config/page.tsx web/src/components/config/IntegrationMappingsPanel.tsx web/src/lib/config-plan-draft.test.ts
git commit -m "feat: add tabbed config page and clone-from-loaded new plan flow"
```

---

### Task 4: Add load-only control visibility and pace presets

**Files:**
- Create: `web/src/lib/load-mode-controls.ts`
- Create: `web/src/lib/load-mode-controls.test.ts`
- Modify: `web/src/components/runs/RunLaunchPanel.tsx`
- Modify: `web/src/lib/run-launcher-config.ts`
- Test: `web/src/lib/load-mode-controls.test.ts`

- [ ] **Step 1: Write failing tests for pace mapping and load visibility**

```ts
// web/src/lib/load-mode-controls.test.ts
import { describe, expect, it } from "vitest";
import { LOAD_PACE_PRESETS, resolveLoadIntervalFromPreset, shouldShowTraceControls } from "./load-mode-controls";

describe("load mode controls", () => {
  it("maps pace presets", () => {
    expect(LOAD_PACE_PRESETS.slow).toBe(10);
    expect(LOAD_PACE_PRESETS.normal).toBe(3);
    expect(LOAD_PACE_PRESETS.fast).toBe(1);
  });

  it("keeps manual interval override", () => {
    expect(resolveLoadIntervalFromPreset("fast", 2.5)).toBe(2.5);
  });

  it("hides trace controls in load mode", () => {
    expect(shouldShowTraceControls("load")).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- src/lib/load-mode-controls.test.ts`  
Expected: FAIL (`Cannot find module './load-mode-controls'`).

- [ ] **Step 3: Implement helper and launcher usage**

```ts
// web/src/lib/load-mode-controls.ts
export const LOAD_PACE_PRESETS = { slow: 10, normal: 3, fast: 1 } as const;
export type LoadPace = keyof typeof LOAD_PACE_PRESETS;

export function shouldShowTraceControls(resolvedMode: "trace" | "load"): boolean {
  return resolvedMode === "trace";
}

export function resolveLoadIntervalFromPreset(pace: LoadPace, manualInterval?: number): number {
  if (manualInterval !== undefined && manualInterval !== null) return manualInterval;
  return LOAD_PACE_PRESETS[pace];
}
```

```tsx
// web/src/components/runs/RunLaunchPanel.tsx (core intent)
const showTraceControls = shouldShowTraceControls(resolvedMode);
// hide Mode Override, Suite, Scenarios when !showTraceControls
// add <select> for Load pace and write form.interval when chosen
```

- [ ] **Step 4: Run tests and build**

Run: `cd web && npm run test -- src/lib/load-mode-controls.test.ts src/lib/run-launcher-config.test.ts && npm run build`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/load-mode-controls.ts web/src/lib/load-mode-controls.test.ts web/src/components/runs/RunLaunchPanel.tsx web/src/lib/run-launcher-config.ts
git commit -m "feat: add load-only launcher controls and pace presets"
```

---

### Task 5: Add deterministic load worker assignment helper

**Files:**
- Create: `load_worker_assignment.py`
- Create: `tests/test_load_worker_assignment.py`
- Test: `tests/test_load_worker_assignment.py`

- [ ] **Step 1: Write failing assignment tests (first-N and round-robin)**

```python
# tests/test_load_worker_assignment.py
import unittest
from load_worker_assignment import build_worker_user_indexes

class LoadWorkerAssignmentTests(unittest.TestCase):
    def test_all_users_false_reuses_single_user(self) -> None:
        self.assertEqual(build_worker_user_indexes(3, 5, all_users=False), [0, 0, 0, 0, 0])

    def test_all_users_true_uses_first_n_when_workers_lte_users(self) -> None:
        self.assertEqual(build_worker_user_indexes(5, 3, all_users=True), [0, 1, 2])

    def test_all_users_true_round_robin_when_workers_gt_users(self) -> None:
        self.assertEqual(build_worker_user_indexes(3, 8, all_users=True), [0, 1, 2, 0, 1, 2, 0, 1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_load_worker_assignment -v`  
Expected: FAIL (`ModuleNotFoundError: load_worker_assignment`).

- [ ] **Step 3: Implement assignment helper**

```python
# load_worker_assignment.py
from __future__ import annotations


def build_worker_user_indexes(plan_user_count: int, worker_count: int, *, all_users: bool) -> list[int]:
    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")
    if plan_user_count < 1:
        raise ValueError("plan_user_count must be >= 1")

    if not all_users:
        return [0 for _ in range(worker_count)]

    if worker_count <= plan_user_count:
        return list(range(worker_count))

    return [i % plan_user_count for i in range(worker_count)]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m unittest tests.test_load_worker_assignment -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add load_worker_assignment.py tests/test_load_worker_assignment.py
git commit -m "test: cover deterministic load worker-user assignment"
```

---

### Task 6: Integrate worker assignment into load runtime

**Files:**
- Modify: `__main__.py`
- Modify: `user_sim.py`
- Modify: `tests/test_simulate.py`
- Test: `tests/test_simulate.py`, `tests/test_load_worker_assignment.py`

- [ ] **Step 1: Write failing runtime test for exact worker count distribution**

```python
# tests/test_simulate.py (new focused unit)
def test_worker_counts_for_all_users_round_robin_distribution(self) -> None:
    from __main__ import _worker_counts_by_user_index
    counts = _worker_counts_by_user_index(plan_user_count=3, worker_count=8, all_users=True)
    self.assertEqual(counts, {0: 3, 1: 3, 2: 2})
```

- [ ] **Step 2: Run targeted tests to confirm fail**

Run: `python3 -m unittest tests.test_simulate -k worker_counts -v`  
Expected: FAIL (`AttributeError` / missing helper).

- [ ] **Step 3: Implement runtime wiring with explicit `worker_count`**

```python
# user_sim.py
async def run(..., worker_count: int | None = None) -> None:
    effective_workers = worker_count if worker_count is not None else config.N_USERS
    ...
    workers = [
        asyncio.create_task(_worker(..., i + 1, ...))
        for i in range(effective_workers)
    ]
```

```python
# __main__.py (core intent)
from load_worker_assignment import build_worker_user_indexes

indexes = build_worker_user_indexes(len(user_bundles), config.N_USERS, all_users=config.ALL_USERS)
counts: dict[int, int] = {}
for idx in indexes:
    counts[idx] = counts.get(idx, 0) + 1

for user_idx, count in counts.items():
    us, fixtures = user_bundles[user_idx]
    t = asyncio.create_task(
        user_sim.run(
            recorder=recorder,
            session=us,
            fixtures=fixtures,
            store_sessions=store_sessions,
            worker_count=count,
        )
    )
```

- [ ] **Step 4: Run runtime tests and full simulator suite**

Run: `python3 -m unittest tests.test_load_worker_assignment tests.test_simulate -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add __main__.py user_sim.py tests/test_simulate.py
git commit -m "feat: enforce deterministic load worker assignment semantics"
```

---

### Task 7: Add comprehensive per-flow docs and coverage checker

**Files:**
- Create: `docs/flows/README.md`
- Create: `docs/flows/audit.md`
- Create: `docs/flows/doctor.md`
- Create: `docs/flows/free-coupon.md`
- Create: `docs/flows/full.md`
- Create: `docs/flows/load.md`
- Create: `docs/flows/menus.md`
- Create: `docs/flows/new-user.md`
- Create: `docs/flows/paid-coupon.md`
- Create: `docs/flows/paid-no-coupon.md`
- Create: `docs/flows/payments.md`
- Create: `docs/flows/receipt-review.md`
- Create: `docs/flows/robot-complete.md`
- Create: `docs/flows/store-accept.md`
- Create: `docs/flows/store-dashboard.md`
- Create: `docs/flows/store-reject.md`
- Create: `docs/flows/store-setup.md`
- Create: `scripts/check_flow_docs.py`
- Test: `scripts/check_flow_docs.py`

- [ ] **Step 1: Write failing docs coverage check script expectation**

```python
# scripts/check_flow_docs.py (start with fail-first expectation)
from pathlib import Path
from flow_presets import FLOW_PRESETS

root = Path(__file__).resolve().parents[1]
flows_dir = root / "docs" / "flows"
missing = [flow for flow in sorted(FLOW_PRESETS) if not (flows_dir / f"{flow}.md").is_file()]
if missing:
    raise SystemExit(f"Missing flow docs: {', '.join(missing)}")
print(f"OK: {len(FLOW_PRESETS)} flow docs present")
```

- [ ] **Step 2: Run checker to verify fail before docs exist**

Run: `python3 scripts/check_flow_docs.py`  
Expected: FAIL with missing flow docs list.

- [ ] **Step 3: Add per-flow comprehensive docs using shared template**

```md
# docs/flows/<flow>.md template
# <Flow> Flow

## Purpose
## When to use
## Prerequisites
## GUI configuration
## CLI equivalents
## Optional flags and overrides
## Expected artifacts and pass signals
## Common failures
## Troubleshooting examples
## Escalation path
```

- [ ] **Step 4: Run checker to verify all flows covered**

Run: `python3 scripts/check_flow_docs.py`  
Expected: `OK: 16 flow docs present`.

- [ ] **Step 5: Commit**

```bash
git add docs/flows scripts/check_flow_docs.py
git commit -m "docs: add comprehensive operator docs for every gui flow"
```

---

### Task 8: Merge docs ownership (`SIMULATOR_GUIDE` canonical, `README` quickstart)

**Files:**
- Modify: `SIMULATOR_GUIDE.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-19-config-load-ux-and-runtime-alignment-design.md` (final accepted version only, if needed)

- [ ] **Step 1: Write failing docs parity checklist in session notes (manual fail-first gate)**

```md
- README still contains duplicated deep operator guidance -> fail
- SIMULATOR_GUIDE missing links to docs/flows/*.md -> fail
- Load semantics (first-N + round-robin) not stated -> fail
```

- [ ] **Step 2: Run docs checks before edits**

Run: `rg -n "Which simulation flow|load|all_users|interval" README.md SIMULATOR_GUIDE.md docs/flows/*.md`  
Expected: reveals duplicated or missing canonical references.

- [ ] **Step 3: Apply docs merge edits**

```md
# README.md (target)
- Quick start commands
- Minimal auth and run launch pointers
- Links to SIMULATOR_GUIDE and docs/flows index

# SIMULATOR_GUIDE.md (target)
- Canonical behavior sections
- explicit load semantics:
  - all_users=false -> single user reused
  - all_users=true and N<=users -> first N
  - all_users=true and N>users -> round-robin
- links to each docs/flows/<flow>.md
```

- [ ] **Step 4: Validate docs consistency**

Run: `python3 scripts/check_flow_docs.py && rg -n "docs/flows|SIMULATOR_GUIDE" README.md SIMULATOR_GUIDE.md`  
Expected: PASS with canonical links present.

- [ ] **Step 5: Commit**

```bash
git add README.md SIMULATOR_GUIDE.md
git commit -m "docs: make simulator guide canonical and link per-flow references"
```

---

### Task 9: Full verification and release-ready check

**Files:**
- Modify: `implementation/tracker/tasks.md`
- Modify: `implementation/tracker/session_log.md`
- Modify: `implementation/tracker/README.md` (status update)

- [ ] **Step 1: Run backend tests**

```bash
python3 -m unittest tests.test_web_api.SimulationPlansApiTests -v
python3 -m unittest tests.test_load_worker_assignment tests.test_simulate -v
```

- [ ] **Step 2: Run frontend tests and build**

```bash
cd web && npm run test -- src/lib/config-plan-draft.test.ts src/lib/load-mode-controls.test.ts src/lib/run-launcher-config.test.ts
cd web && npm run build
```

- [ ] **Step 3: Run docs coverage + whitespace checks**

```bash
python3 scripts/check_flow_docs.py
git diff --check
```

- [ ] **Step 4: Record verification evidence in tracker**

```md
# implementation/tracker/session_log.md
- commands
- pass/fail outputs
- changed files
- next steps
```

- [ ] **Step 5: Commit tracker completion updates**

```bash
git add implementation/tracker/README.md implementation/tracker/tasks.md implementation/tracker/session_log.md
git commit -m "chore: record verification evidence for config-load alignment rollout"
```

---

## Plan Self-Review

### 1. Spec coverage check

- Config tabs: covered in Task 3.
- Default `sim_actors` load: covered in Task 1 + Task 3 integration.
- `New` clone behavior: covered in Task 2 + Task 3.
- Load-mode trace-field suppression + mode override removal: covered in Task 4.
- Pace presets and manual interval override: covered in Task 4.
- Load semantics (`all_users` false/true, first-N, round-robin): covered in Task 5 + Task 6.
- Per-flow docs for every GUI flow: covered in Task 7.
- Canonical docs ownership (`SIMULATOR_GUIDE`, `README`): covered in Task 8.
- Verification evidence and restartability: covered in Task 9.

No requirement gaps found.

### 2. Placeholder scan

- No `TODO`, `TBD`, or deferred placeholders in task steps.
- Every code-edit step includes concrete code blocks and explicit commands.

### 3. Type/signature consistency

- `build_worker_user_indexes(plan_user_count, worker_count, all_users=...)` signature is consistent across Task 5 and Task 6.
- `buildNewPlanDraft(editorValue, fallbackContent, nextName)` is consistent across Task 2 and Task 3.
- Load preset mapping (`slow=10`, `normal=3`, `fast=1`) is consistent across tasks/docs.

