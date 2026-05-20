# Simulator GUI — personal demo checklist

Use this as a **live walkthrough script** for presentations or acceptance smoke tests. Each item is a quick manual check you perform in the browser; tick `- [ ]` as you go.

**Setup (before you demo)**

- [ ] Stack is up (e.g. `docker compose up -d --build` from repo root).
- [ ] Web UI opens at `http://localhost:8080` (or your deployed URL).
- [ ] You can sign in (default admin: `admin` / `admin123` — change in production).
- [ ] You know which **role** you are demoing (`admin` vs `operator` vs read-only) so permission surprises are expected, not bugs.

**Reference:** For exhaustive field-by-field and API-aligned tests, use [GUI_TESTING.md](GUI_TESTING.md).

---

## 1) First impression — shell and auth

- [ ] **Login** (`/auth/login`): valid credentials land you on the dashboard (`/overview` or home).
- [ ] **Invalid login** shows a clear error; you are not dropped into the app.
- [ ] **Header**: brand links home; primary nav shows **Overview**, **Runs**, **Config**, **Schedules**, **Archives**, **Admin** (Admin may vary by role).
- [ ] **Active run indicator**: on **Runs**, if something is executing, the nav shows the live badge (green dot) and the count feels plausible.
- [ ] **Theme toggle**: light/dark switches and survives a full page refresh.
- [ ] **Profile / sign out**: sign out returns to login; hitting a protected URL while logged out redirects to login.

---

## 2) Overview — “is the system alive?”

- [ ] Page loads without a blocking error banner (or error is readable and actionable).
- [ ] **Summary cards / charts** populate when the API is healthy.
- [ ] **Latest run** (or hero row): links through to run detail when you click through.
- [ ] Optional: **last updated** or loading skeletons feel intentional, not a stuck blank screen.

---

## 3) Runs — launch pad

- [ ] **API / health** indicator matches reality (green when API is up).
- [ ] **Start Run** area: flow dropdown loads (no empty stuck state if flows exist).
- [ ] Pick a **low-risk flow** (e.g. `doctor`) and confirm **command preview** updates when you change timing, plan, or checkboxes.
- [ ] **Field help** / sidebar: selecting a flow shows relevant guidance; collapsing on narrow width still works.
- [ ] **Validation**: intentionally break rules (e.g. load-only fields in trace mode) and confirm the UI blocks launch with a readable message.
- [ ] **Start Simulation** (or equivalent): a new run appears in **Recent Runs** and you can open it.
- [ ] **Live console**: with a running job, log lines advance or refresh; switching selected active run updates the console context.
- [ ] **Stop / cancel**: stopping an active run completes without a silent failure (toast, inline error, or status change).
- [ ] **Saved profiles**: save → reload form from profile → launch from profile (at least one round trip).
- [ ] **Recent Runs**: pagination changes the page; **View** opens `/runs/{id}`.
- [ ] **Delete run** (if permitted): confirmation modal; run leaves the active list and is recoverable from **Archives** (archive-first behavior).

---

## 4) Run detail — deep dive on one run

Open any completed or failed run from **Recent Runs**.

- [ ] **Header**: status, run id, and navigation back to the list feel clear.
- [ ] **Overview** tab: metrics / findings / attention items render; timestamps on queue-style rows are readable.
- [ ] **Story** and **Report** tabs: markdown renders when artifacts exist; empty state is honest when missing.
- [ ] **Traffic** (events): table loads; paging or “load more” behaves; totals look consistent.
- [ ] **Console**: log tail loads; while running, updates feel live enough for a demo.
- [ ] **Execution** (if available): snapshot panel shows meaningful structure; **Replay** (if shown) kicks off a new run and you get a new id.
- [ ] **Keyboard / focus**: tab through tabs and modals without focus escaping visibly (no “lost” focus on drawers/dialogs).

---

## 5) Config — plans and operator settings

- [ ] Registered **simulation plans** list loads; selecting a plan shows details you expect.
- [ ] **Edit / save** (as permitted): success feedback; reload page and confirm persistence.
- [ ] Permission-sensitive controls: as a non-admin, restricted actions are hidden or fail with a clear message (not a blank 403 page).

---

## 6) Schedules — automation story

- [ ] List loads; create or open a **draft** schedule if your role allows it.
- [ ] **Preview** / validation path: schedule definition errors are visible before save.
- [ ] **Pause / resume / trigger** (as applicable): each action updates status in the UI.

---

## 7) Archives — restore and trust

- [ ] **Archived runs** (and profiles / schedules / mappings if present): list loads; filters or sections are understandable.
- [ ] **Restore** on one archived item returns it to the active world; you can find it again from **Runs** or **Config** as appropriate.
- [ ] Retention-style summaries on this page read coherently next to archive counts (backlog / purge-ready language).

---

## 8) Admin — users and system (admin role)

Skip this section if you are not logged in as **admin**.

- [ ] **Users** (`/admin/users`): list, create or edit a user, role change reflects on next login or refresh.
- [ ] **System** (`/admin/system`): timezone or global settings load; saving shows confirmation; invalid input is blocked before save.

---

## 9) Resilience — “what if something breaks?” (short)

- [ ] **API down**: stop the API container briefly — Runs page shows degraded health and errors do not brick the whole layout.
- [ ] **API back**: refresh or wait for polling — UI recovers without a hard refresh if that is the product intent.
- [ ] **Slow network** (throttle in devtools): loading skeletons or spinners appear; no duplicate submissions from double-clicking **Start** (best-effort check).

---

## 10) Wrap-up — demo exit criteria

- [ ] You showed **login → overview → launch → run detail → archives/restore** in one coherent story.
- [ ] You called out **roles** (who can delete, schedule, admin).
- [ ] You mentioned one **known GUI limitation** (e.g. `extra_args` is not in the form — see [GUI_TESTING.md](GUI_TESTING.md) §17) so technical viewers trust the demo.

---

## Notes

- Route `/retention` redirects to **Archives**; retention policy editing for admins lives under **Admin → System** and summaries appear on **Overview** / **Archives** as implemented.
- After changing operator-visible behavior, update [GUI_TESTING.md](GUI_TESTING.md) and this checklist together if the demo story shifts.
