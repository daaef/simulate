# Simulator API Documentation — Stages 0–7 complete

**Status (2026-07-27):** Stages 0–7 complete. 106 use-case files (90 internal, 16 external); 76 internal + 14 external have real responses (11 live-captured directly against this project's own auth/store, 3 reused verbatim from `last_mile_user/api_docs`'s own real live capture of the same endpoints — see each file's `note` for exact provenance). Remaining 14 internal + 2 external are documented skeletons with a `note` explaining why they weren't captured (real-money/real-SMS/real-GitHub-write risk, or not yet approved). `index.html` viewer is live — open it directly (`file://`) or serve the folder.

## What's here

- **INTERNAL_USE_CASE_MAP.md** — Stage 1 output: grep-verified call-site trace for all 90 internal API routes, mapped to frontend trigger (page/component/action) and backend route (file:line).
- **EXTERNAL_USE_CASE_MAP.md** — Stage 2 output: grep-verified call-site trace for 16 external API endpoints (fainzy.tech / lastmile.fainzy.tech), mapped to simulator code (user_sim.py / store_sim.py / run_plan.py).
- **SCHEMA.md** — JSON schema all use-case files follow, adapted from `last_mile_user/api_docs/SCHEMA.md` with added `"part": "internal" | "external"` field.
- **internal/<group>/*.json** — 90 skeleton files (auth, admin, runs, archives, retention, schedules, subentities, alerts, simulation_plans, system, integrations, orders, overview) with `useCase`, `group`, `part`, `endpoint`, `usedIn`, `trigger`, `params`, `auth` filled from Stage 1; `response`/`capture.verifiedAt` are null (awaiting Stages 4–5).
- **external/<group>/*.json** — 16 skeleton files (auth, config, location, stores, menu, orders) with same shape, documenting calls to fainzy.tech/lastmile.fainzy.tech.
- **tools/build_docs.py** — validates every file against SCHEMA.md, regenerates manifest.json, aware of internal/external partition.
- **manifest.json** — generated index of all 106 use cases, grouped by (part, group).

## Quick verification

```bash
cd api_docs
python3 tools/build_docs.py            # should show: 106 files, 0 errors, 0 warnings
python3 tools/build_docs.py --strict   # should show: 106 "not yet captured" (expected for scaffolds)
python3 -m py_compile tools/build_docs.py  # syntax check
```

## Viewer (`index.html`, Stage 6)

Single self-contained file — inline CSS/JS, no CDN dependencies, works opened directly via `file://` or served (`python3 -m http.server` from inside `api_docs/`). Sidebar toggles between Internal/External, lists groups → use cases, and has a text filter across path/name/screen/trigger. Selecting a use case fetches its JSON on demand and shows endpoint, used-in chain, trigger, params, auth, response, and a freshness badge (verified / gated-see-note / expected-non-2xx / non-200 error).

**Redaction scope note:** the plan called for a per-field 👁 eye-toggle (mask individual `sensitivePaths` values within the response tree, reveal one field at a time). The implementation shipped instead uses a **simplified single section-level toggle**: everything a file's `sensitivePaths` array flags is masked by default, with one "Reveal all / Hide all" control per open use case rather than per-field. This was a deliberate fallback per the plan's Stage 6 note (the recursive JSON-tree-with-per-path-toggle renderer was judged not worth the extra iterations) — default-hidden-until-revealed still holds, it's just coarser-grained than originally specified. Upgrading to true per-field toggles is a reasonable follow-up if it matters later.

## What's still gated (by design, not a bug)

- **Internal** (14 of 90): GitHub-integration endpoints that would call the real GitHub API, and `orders/*` endpoints that call real `fainzy.tech`/`lastmile.fainzy.tech` — each has a `note` explaining why.
- **External** (2 of 16): `free_order_complete` (no real capture exists anywhere yet — not even in `last_mile_user/api_docs`, whose own copy of this file is also uncaptured) and `stores/store_update_status` (a real `PATCH` write against a live store — a capture script for this was written and then deliberately removed after a safety review flagged it as an unapproved production write; see `docs/API_DOCS_PLAN_2026-07-27.md` open item #2).

## Provenance of the `auth/*` and `orders/*` external captures (2026-07-27)

`otp_send`, `otp_verify`, `signup_create_user`, `login_authenticate_user`, and `menu/*` were captured live and directly, using a throwaway account (`+819081819999`, user id 49) created specifically for this documentation pass — the backend echoes the OTP in its own response rather than requiring a real SMS-capable number, so no real text message was involved. `checkout_place_order`, `order_details_poll`, and `order_cancel_update` were **not** captured fresh — placing a real order requires a nontrivial `restaurant`/`location`/`menu` payload shape that simulate's own discovery code builds, and hand-assembling it risked sending something malformed to a live backend. Instead, real captures of the identical endpoints already existed in `../last_mile_user/api_docs/orders/` (captured 2026-07-24, same backend, same store) and were reused verbatim, with each file's `note` field stating this explicitly. This intentionally avoided placing a second real order purely to produce documentation.

Re-run `python3 tools/capture_internal.py` / `python3 tools/capture_external.py` (from `api_docs/tools/`) any time to refresh captures; both are safe to re-run against the same local Docker stack / read-only external endpoints. The `auth`/`menu`/`orders` captures above were done manually (see chat history / `docs/API_DOCS_PLAN_2026-07-27.md`) rather than via a script, per the operator's requirement that all live commands be run by them, not by the assistant.

## Relationship to existing docs

- **`docs/last_mile_api_inventory.md`** (2026-06-12, narrative) — superseded by this scaffold for external calls; kept for reference, now carries a pointer banner back to `api_docs/`.
- **`last_mile_user/api_docs/`** (sibling project) — same pattern (use-case JSON, `build_docs.py` validator, eye-toggle viewer); this project's viewer mirrors that structure with an added internal/external toggle.
