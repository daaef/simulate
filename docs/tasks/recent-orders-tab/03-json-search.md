# Sub-task 03 — JSON search

## What
Add a search input to `OrderJsonViewer` that filters the displayed JSON in real time.

## How
- Add `jsonSearch` state (string) inside `OrderJsonViewer`
- When empty: render full `JSON.stringify(order, null, 2)` as before
- When non-empty: split JSON string by line, keep only lines whose text includes the search term (case-insensitive), rejoin and render
- Search input sits in the panel header bar next to the "Order JSON" label

## Done when
Typing in the search box filters JSON lines to only those matching the query; clearing restores full JSON.
