# Solution — Stop polling from clobbering open-form state

## Proposed approach
Establish the invariant: **the polled `load()` must never write form-input state while the form is open.**

1. Add a `showFormRef` (`useRef(false)`) kept in sync with `showForm` via a one-line effect. A ref is read at call-time, so the stale `setInterval` closure still sees the current open/closed status.
2. Wrap the default-seeding block in `load()` (profileId, stepProfileId, timezone — lines 288–298) in `if (!showFormRef.current) { … }`.

When the form is closed, seeding runs exactly as today (initial mount seeds a valid default; harmless re-seed on later polls). When the form is open (create OR edit), polls refresh only the list/summary/policy and leave every form field untouched.

## Alternatives rejected
- **Guard with the `showForm` state variable directly** — fails: the interval's captured `load` closure reads the first-render `showForm` (always `false`), so the guard never engages during editing.
- **Move seeding into a separate run-once effect** — larger refactor; would still need to re-derive a valid default when the policy arrives. The ref guard is smaller and equally correct.
- **Stop calling `setTimezone` in `load()` entirely** — breaks the create form's allowlist-valid default seeding on first load.

## Performance impact
Neutral-to-positive: removes 1 redundant `setTimezone` state write per 15s poll (and per focus/visibility event) while a form is open, avoiding needless re-renders of the form drawer. No new network calls, listeners, or allocations.

## Performance delta
- Before: `setTimezone` invoked on every `load()` (≥1 per 15s, plus on focus/visibility) regardless of form state → form re-render + lost user input.
- After: 0 form-state writes from `load()` while the form is open. List refresh cadence unchanged.

## Trade-offs
The one `load()` fired immediately after submit may still read `showFormRef.current === true` and skip re-seeding for that call — intentional and harmless (form is closing; next idle poll re-seeds the create default).

## Dead code audit
None. No code becomes unreachable; the seeding block is retained, only gated.
