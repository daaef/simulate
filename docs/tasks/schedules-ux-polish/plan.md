# Plan: Schedules Page UX Polish

## Context
The Schedules page (`web/src/app/(app)/schedules/page.tsx`) already has working
metric cards, filter tabs, an upcoming-triggers panel, and a filterable schedule list.
Four UX issues remain that make the page feel cluttered or incomplete:

1. The Create/Edit form is always visible — it dominates the page even when unused.
2. Each table row has up to 5 action buttons — too many to scan quickly.
3. The Upcoming Triggers and Recent Executions panels stretch to the same height,
   leaving a hollow void when there are few upcoming runs.
4. Metric cards for counts of 0 look identical to cards with meaningful counts —
   no visual hierarchy signals where attention is needed.

## Goal
A Schedules page where:
- The default state is clean: metrics → activity → list. No form in sight.
- The form appears on demand in a slide-over drawer.
- Each table row is compact: Trigger, Edit, and a ⋯ overflow menu.
- Panels size naturally to their content.
- Zero-count metric cards are visually muted; non-zero cards command attention.

## Files in scope
- `web/src/app/(app)/schedules/page.tsx` — component logic & JSX
- `web/src/app/globals.css` — shared styles

## Sub-tasks (do in order)
| # | File | What |
|---|------|------|
| 01 | `01-metric-card-zero-state.md` | Dim metric cards when count is 0 |
| 02 | `02-panel-heights-card-colors.md` | Fix panel stretch + execution card text colors |
| 03 | `03-action-overflow-menu.md` | ⋯ overflow menu for secondary table actions |
| 04 | `04-form-drawer.md` | Move Create/Edit form into a slide-over drawer |

## Concepts in play
| Term | Plain-English definition |
|------|--------------------------|
| Progressive disclosure | Show information only when the user asks for it — keeps the default view simple |
| CSS custom property | A variable in CSS (e.g. `--text-primary`) defined once, used everywhere — changes automatically when the theme switches |
| Conditional class | A CSS class applied only when a condition is true (e.g. `count === 0`) — lets data drive the visual |
| Drawer / side panel | A panel that slides in from the screen edge, overlaying content without navigating away |
| Kebab menu (⋯) | A small dropdown triggered by a vertical-dots button — groups secondary actions to reduce visual noise |
| align-items: start | A CSS grid/flex property that tells children to grow only as tall as their own content, not the tallest sibling |

## Verification checklist
- [x] Metric cards with count > 0 are fully styled; count === 0 cards are visually muted
- [x] Upcoming Triggers panel does not stretch taller than its content
- [x] Execution card text is readable in both light and dark mode
- [x] Schedule list table shows only Trigger + Edit inline; ⋯ opens a dropdown for the rest
- [x] ⋯ dropdown closes on outside click and on Escape key
- [x] "New Schedule" button opens the drawer; drawer closes on × button, backdrop click, or Escape
- [x] Editing a schedule from the list also opens the drawer (pre-populated)
- [x] Saving or cancelling closes the drawer and returns focus to the list

## Status: COMPLETE — implemented 2026-06-02
