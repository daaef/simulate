# Sub-task 04 — Move Create/Edit form into a slide-over drawer

## Concept
A *drawer* (also called a *side panel* or *slide-over*) is a panel that lives
off-screen to the right and slides into view when you need it, then slides back
out. It's the same pattern used in GitHub's "new issue" sidebar or the Stripe
dashboard's detail panels.

The drawer sits at a *fixed* position relative to the viewport (not the page
content), so it overlays everything else. An *overlay* (a semi-transparent dark
layer) covers the page behind it so the user knows the drawer is "modal" — i.e.,
they should finish what they're doing before interacting with the page.

The key engineering pieces:
1. **State**: a boolean `showForm` that controls whether the drawer is open.
2. **CSS**: `position: fixed; right: 0; top: 0; height: 100vh` + a `transform`
   transition that slides between `translateX(100%)` (hidden) and `translateX(0)` (visible).
3. **Accessibility**: when the drawer opens, focus moves inside it; when it closes,
   focus returns to the button that triggered it.

## What to change

### `web/src/app/(app)/schedules/page.tsx`

**1. Add state** (near the other `useState` declarations):
```tsx
const [showForm, setShowForm] = useState(false);
```

**2. Update `startEditSchedule`** — open the drawer when editing:
```tsx
const startEditSchedule = (schedule: Schedule) => {
  // ... existing field-setting code unchanged ...
  setShowForm(true);  // ← add this line at the end
  setError(null);
};
```

**3. Update `cancelEditSchedule`** — close the drawer on cancel:
```tsx
const cancelEditSchedule = () => {
  // ... existing reset code unchanged ...
  setShowForm(false);  // ← add this line at the end
  setError(null);
};
```

**4. Update `submit`** — close the drawer after a successful save:
```tsx
// Inside the try block, just before `await load()`:
setShowForm(false);
```

**5. Add "New Schedule" button** to the `schedule-list-header`:
```tsx
<div className="schedule-list-header">
  <h2 className="section-title">Schedule List</h2>
  <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
    <div className="filter-tabs">
      {/* existing filter tabs unchanged */}
    </div>
    <button type="button" onClick={() => { setEditingScheduleId(null); setShowForm(true); }}>
      + New Schedule
    </button>
  </div>
</div>
```

**6. Wrap the form in a drawer** — replace:
```tsx
<form className="panel grid" onSubmit={submit}>
  ...
</form>
```
with:
```tsx
{showForm ? (
  <div className="drawer-overlay" onClick={(e) => { if (e.target === e.currentTarget) { cancelEditSchedule(); } }} aria-hidden="true" />
) : null}
<div className={`drawer${showForm ? " drawer--open" : ""}`} role="dialog" aria-modal="true" aria-label={editingScheduleId ? "Edit Schedule" : "Create Schedule"}>
  <div className="drawer__header">
    <h2 className="section-title">{editingScheduleId ? `Edit Schedule #${editingScheduleId}` : "Create Schedule"}</h2>
    <button type="button" className="drawer__close secondary small" onClick={cancelEditSchedule} aria-label="Close">×</button>
  </div>
  <form className="drawer__body grid" onSubmit={submit}>
    {/* all existing form fields, unchanged */}
  </form>
</div>
```

Note: remove the `<h2>` that was at the top of the old form — it's now in `drawer__header`.

### `web/src/app/globals.css`

```css
/* Drawer */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--text-primary) 40%, transparent);
  z-index: 40;
  animation: overlay-in 0.2s ease;
}

@keyframes overlay-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  height: 100dvh;
  width: min(520px, 100vw);
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-primary);
  z-index: 50;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: -4px 0 24px color-mix(in srgb, var(--text-primary) 10%, transparent);
}

.drawer--open {
  transform: translateX(0);
}

.drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-primary);
  flex-shrink: 0;
}

.drawer__close {
  width: 32px;
  height: 32px;
  font-size: 18px;
  line-height: 1;
  padding: 0;
  min-width: unset;
}

.drawer__body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  gap: 14px;
}
```

## Done criteria
- Default page has no form visible — just the New Schedule button in the list header.
- Clicking "New Schedule" slides the drawer in from the right.
- Clicking a row's "Edit" button also opens the drawer, pre-filled with that schedule's data.
- Clicking the × button, the backdrop, or pressing Escape closes the drawer.
- After a successful save the drawer closes automatically.
- The drawer is scrollable if the form is taller than the screen.
- The page behind the drawer is dimmed by the overlay.
