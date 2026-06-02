# Sub-task 02 — Panel heights + execution card text colors

## Concept A: Panel heights
CSS Grid by default makes all cells in a row the **same height** as the tallest
one — like a spreadsheet row. We want each panel to be only as tall as its own
content. One property fixes this:

```css
align-items: start;
```

`align-items` controls how grid children position themselves vertically inside
their cell. `start` means "stick to the top and grow only as far as your content
needs" — the opposite of the default `stretch`.

## Concept B: CSS custom properties (theme-aware colours)
A CSS custom property is a variable you define once at the top of your stylesheet:
```css
:root { --text-primary: #111827; }
[data-theme="dark"] { --text-primary: #f8fafc; }
```
When you use `var(--text-primary)` in a component it automatically resolves to
the right value for the active theme. Hard-coded hex values (`#f8fafc`) always
resolve to one specific colour regardless of theme — that's why the execution
card text is invisible in light mode.

## What to change

### `web/src/app/globals.css`

**1. Give the activity row a named class and align-items:**
Find the two-column grid wrapping Upcoming Triggers and Recent Executions.
It currently uses the generic `.grid.two` class. In `globals.css`, add:

```css
.schedules-activity-row {
  align-items: start;
}
```

**2. Fix hard-coded colours in execution cards:**
Find and replace:
```css
/* BEFORE */
.schedule-execution-card-main strong {
  color: #f8fafc;
}
.schedule-execution-primary {
  color: #e2e8f0;
  font-weight: 500;
}

/* AFTER */
.schedule-execution-card-main strong {
  color: var(--text-primary);
}
.schedule-execution-primary {
  color: var(--text-secondary);
  font-weight: 500;
}
```

### `web/src/app/(app)/schedules/page.tsx`
Add the `schedules-activity-row` class to the section wrapping Upcoming + Recent:

```tsx
<section className="grid two schedules-activity-row">
```

## Done criteria
- Upcoming Triggers panel is only as tall as its content (no stretching to match Recent Executions).
- Execution card schedule names and trigger times are readable in both light and dark mode.
