# Plan — Gate form-seeding in load() behind a form-open ref

## Steps
1. **Add `showFormRef`** next to the other refs (~line 207): `const showFormRef = useRef(false);`. _Complexity: trivial._ AC: ref declared, type `MutableRefObject<boolean>`.
2. **Sync ref to state** — add `useEffect(() => { showFormRef.current = showForm; }, [showForm]);` near the other effects. _Complexity: trivial._ AC: ref tracks every `showForm` change.
3. **Gate seeding block** in `load()` (lines 288–298) with `if (!showFormRef.current) { … }`, keeping the existing profileId/stepProfileId/timezone logic inside. _Complexity: low._ AC: no form-input setter runs in `load()` when the form is open.

## Untested path disclosure
No automated tests cover this page (manual verification only). Changed path: `load()` seeding branch + the new effect.

## Regression checklist (direct callers to verify)
- `load()` callers: mount effect (310), `refresh` poll (315), `submit` post-save (480), and every action handler that calls `load()` (pause/resume/delete/run-now). Verify: list still refreshes; create form still opens with a valid default tz; edit form retains user-selected tz across ≥2 poll cycles.
- `showForm` consumers: edit (551), create (752), submit (478), cancel (558), Escape effect (343–348) — verify open/close still behaves.

## Definition of Done
- [ ] App runs without new warnings or errors
- [ ] Edit tz → wait ≥30s (2+ polls) → value stays (AC for steps 1–3)
- [ ] Create form opens with a policy-valid default timezone
- [ ] Schedule list/summary still auto-refresh every 15s
- [ ] Regression checklist cleared
- [ ] Dead code audit complete (none)
- [ ] No new `any`/unsafe assertions
- [ ] No new dependencies
- [ ] Cross-file consistency — timezone is page-local; no other instances
