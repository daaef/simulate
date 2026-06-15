# Stand-Up Summary: Fri–Sun (Jun 13–15, 2026)

> Completed: 2026-06-15  
> Projects: simulate, last_mile_store  
> Format: stand-up / progress report

---

## What happened (Layman)

Over the weekend, two main systems got updates. The simulator tool that mimics
real delivery-app users now labels its one-time password (OTP) requests so the
server knows they came from the simulator — not an actual person — making it
easier to handle them differently. The store app also got smarter about
choosing which store or driver to simulate: it now picks them in a shuffled
order with no repeats in a session. On the mobile side, the app learned to
periodically check for order updates over a live connection (WebSocket
polling), and the day/night theme toggle was rebuilt to look cleaner with
labelled icons.

---

## How it works (Pseudocode)

### simulate — OTP action field (Sat Jun 14)
1. When the simulator sends an OTP request, attach `action: "simulator"` to
   the request body.
2. Server reads the `action` field and routes the request differently from a
   real-user OTP.

### simulate — Plan-default actor selection (Fri Jun 13)
1. Mark stores and phones with `store_is_plan_default` / `phone_is_plan_default`
   flags in the API and TypeScript models.
2. Build a shuffle pool of all eligible actors at session start.
3. Each time a "Plan default" is selected, pop the next actor from the pool
   without replacement — no repeats until the pool is exhausted.
4. Log all HTTP requests and WebSocket connections so actor selection is
   fully traceable.

### last_mile_store — WebSocket polling (Thu/Fri Jun 12–13)
1. On connection, start three polling timers: pending orders, active orders,
   normal orders — intervals configurable via `.env`.
2. Each timer fires a `FetchPolicy.fresh` fetch through `CachedOrderRepository`.
3. Results flow into `OrdersBloc` and update the UI in real time.
4. A debug-only toggle lets developers manually connect/disconnect the socket.

### last_mile_store — Theme toggle refactor (Sat Jun 14)
1. Replace the single animated toggle with a segmented icon control.
2. Each segment (light / dark) shows an icon; the active segment is visually
   highlighted; a label sits beside it.
3. Tapping a segment calls the existing theme provider — no new state layer.

---

## The implementation (Code-level)

### simulate

**OTP action field**
- `otp-simulator-action-README.md` documents the change (already written Sat).
- Request body gains `{ action: "simulator" }` — server differentiates from real OTP.

**Plan-default actor selection**
- `docs/tasks/20260611_plan-default-actor-selection/` — full plan on file.
- New flags: `store_is_plan_default`, `phone_is_plan_default` in API model + TS types.
- Shuffle pool replaces `.env`-driven actor lookup; pool resets per session.
- Logging added to HTTP client and WS connection setup.

### last_mile_store

**WebSocket polling**
- `OrdersBloc` — three new polling strategies added.
- `CachedOrderRepository` — `FetchPolicy` enum controls fresh-vs-cache.
- `AppBloc` — `OrdersService` reset on logout.
- `.env` — `WS_POLL_PENDING_MS`, `WS_POLL_ACTIVE_MS`, `WS_POLL_NORMAL_MS` constants.

**Theme toggle**
- `AnimatedThemeToggle` removed; replaced with `SegmentedThemeToggle` widget.
- Active/inactive icon states rendered from theme provider value.
- Unnecessary Android `.cxx` build files deleted.

---

## Why this way (Advanced)

**OTP action field** — Tagging simulator traffic at the payload level is the
minimal non-breaking contract change. A header or query-param alternative was
rejected because the OTP endpoint is already shared; a body field keeps the
diff isolated to the simulator caller and the server handler with zero impact
on the mobile client.

**Shuffle pool for actor selection** — True randomness with `Math.random` would
allow repeats, skewing test runs toward popular actors. A shuffle-without-
replacement pool guarantees uniform coverage across all actors per session —
the standard approach for simulation fairness. Removing `.env` coupling makes
the selection deterministic and reproducible across UI and CLI invocations.

**WebSocket polling via FetchPolicy** — Polling over an open socket is cheaper
than opening a new HTTP connection per interval; `FetchPolicy` keeps the fetch
strategy decision out of the UI layer (SRP). Configuring intervals via `.env`
avoids hardcoded magic numbers and lets QA adjust without a rebuild.

**Segmented theme toggle** — The animated single-button toggle encoded state
as motion, which is inaccessible to users with reduced-motion preferences. A
segmented control makes the active state visible at rest, passes WCAG 1.4.3
(contrast) without animation, and is trivially keyboard-navigable.

---

## Verification

- [ ] `simulate`: OTP flow — send an OTP via the simulator and confirm the
  server receives `action: "simulator"` in the request body (check server logs).
- [ ] `simulate`: Actor selection — run two plan-default selections and confirm
  no actor repeats appear in the session log.
- [ ] `last_mile_store`: Place a new order and confirm the `OrdersBloc` receives
  a fresh update within the configured polling interval without a manual refresh.
- [ ] `last_mile_store`: Toggle theme in the store app — confirm both segments
  render correct icons and the active segment is visually distinct.
