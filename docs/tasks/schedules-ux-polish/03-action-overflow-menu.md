# Sub-task 03 — Action overflow menu (⋯)

## Concept
A *kebab menu* (named for the ⋮ vertical dots that look like a skewer) groups
secondary actions behind a toggle button. It's the same pattern used in Gmail,
GitHub, and Notion for row-level actions.

The key engineering concept is **local UI state** — a piece of state that tracks
which row's menu is currently open. Only one menu can be open at a time, so we
store the `id` of the open row (or `null` if none is open):

```tsx
const [openMenuId, setOpenMenuId] = useState<number | null>(null);
```

We also need to **close the menu when the user clicks outside it** — this is
done with a `useEffect` that attaches a click listener to the document and
clears the open ID when a click lands outside the menu.

## What to change

### `web/src/app/(app)/schedules/page.tsx`

**1. Add state** (near the other `useState` declarations):
```tsx
const [openMenuId, setOpenMenuId] = useState<number | null>(null);
```

**2. Add close-on-outside-click effect** (near the other `useEffect` calls):
```tsx
useEffect(() => {
  if (openMenuId === null) return;
  const close = (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    if (!target.closest(".action-menu")) setOpenMenuId(null);
  };
  document.addEventListener("mousedown", close);
  return () => document.removeEventListener("mousedown", close);
}, [openMenuId]);
```

**3. Replace the `row-actions` div** inside the table's `<td>` with:
```tsx
<td>
  <div className="row-actions">
    <button
      className="small"
      disabled={busy || !canTrigger}
      onClick={() => runAction("trigger schedule", () => triggerSchedule(schedule.id))}
    >
      Trigger
    </button>
    <button
      className="secondary small"
      disabled={busy}
      onClick={() => { startEditSchedule(schedule); }}
    >
      Edit
    </button>
    <div className="action-menu">
      <button
        className="secondary small"
        type="button"
        aria-label="More actions"
        onClick={() => setOpenMenuId(openMenuId === schedule.id ? null : schedule.id)}
      >
        ···
      </button>
      {openMenuId === schedule.id ? (
        <div className="action-menu__dropdown">
          {isPaused ? (
            <button type="button" onClick={() => { setOpenMenuId(null); runAction("resume schedule", () => setScheduleStatus(schedule.id, "resume")); }}>Resume</button>
          ) : null}
          {canPause ? (
            <button type="button" onClick={() => { setOpenMenuId(null); runAction("pause schedule", () => setScheduleStatus(schedule.id, "pause")); }}>Pause</button>
          ) : null}
          {canEnable ? (
            <button type="button" onClick={() => { setOpenMenuId(null); runAction("enable schedule", () => setScheduleStatus(schedule.id, "resume")); }}>Enable</button>
          ) : null}
          {canDisable ? (
            <button type="button" onClick={() => { setOpenMenuId(null); runAction("disable schedule", () => setScheduleStatus(schedule.id, "disable")); }}>Disable</button>
          ) : null}
          <button
            type="button"
            className="danger"
            onClick={() => { setOpenMenuId(null); runAction("delete schedule", () => setScheduleStatus(schedule.id, "delete")); }}
          >
            Delete
          </button>
        </div>
      ) : null}
    </div>
  </div>
</td>
```

### `web/src/app/globals.css`

```css
/* Overflow action menu */
.action-menu {
  position: relative;
  display: inline-block;
}

.action-menu__dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 50;
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  box-shadow: 0 4px 16px color-mix(in srgb, var(--text-primary) 12%, transparent);
  min-width: 140px;
  overflow: hidden;
}

.action-menu__dropdown button {
  display: block;
  width: 100%;
  padding: 9px 14px;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 0;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background-color 0.15s ease;
  min-width: unset;
}

.action-menu__dropdown button:hover {
  background: var(--surface-hover);
}

.action-menu__dropdown button.danger {
  color: var(--chart-danger);
}

.action-menu__dropdown button.danger:hover {
  background: var(--status-danger-bg);
}
```

## Done criteria
- Table rows show Trigger + Edit + ⋯ (three items max).
- Clicking ⋯ opens a dropdown with the contextual secondary actions.
- Clicking outside the dropdown or pressing Escape closes it.
- Delete is styled in red to signal destructive intent.
- The dropdown is clipped to the viewport (doesn't overflow the page edge).
