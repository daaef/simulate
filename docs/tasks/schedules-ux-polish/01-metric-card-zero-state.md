# Sub-task 01 — Metric card 0-state

## Concept
This is **conditional styling** — changing the visual based on a data value.
Think of it like a traffic light: the same object (a card) shows a different
colour depending on what the number says.

In React, we do this by conditionally adding a CSS class:
```tsx
className={`metric-card${count === 0 ? " metric-card--zero" : ""}`}
```
That extra class is added *only when the count is zero*, and the CSS for
`.metric-card--zero` makes the card look muted.

## What to change

### `web/src/app/(app)/schedules/page.tsx`
Each metric card `<button>` already has variant classes like `metric-card--active`.
Add `metric-card--zero` when the count is 0:

```tsx
// Example for the Active card:
<button
  type="button"
  className={`metric-card metric-card--active${(summary?.health.active ?? 0) === 0 ? " metric-card--zero" : ""}`}
  onClick={() => goToList("active")}
>
```
Apply the same pattern to Total, Paused, Disabled, and Degraded cards.

### `web/src/app/globals.css`
Add below the existing `.metric-card--degraded` rule:

```css
.metric-card--zero {
  opacity: 0.48;
  border-top-color: var(--border-primary) !important;
  pointer-events: none;   /* non-zero cards are clickable; zero cards have nothing to show */
}
```

## Done criteria
- A metric card whose value is 0 appears noticeably dimmer than a card with a real count.
- The colored top border disappears on zero cards.
- Zero cards are not clickable (nothing useful to filter to).
- Non-zero cards are unchanged.
