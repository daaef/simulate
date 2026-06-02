# Sub-task 05: Real Store Mode — UI checkbox + API plumbing

## What this does
Adds the "Wait for real store action" checkbox to the run launcher panel and wires it
through the API to the CLI.

## Files (in order of data flow)
1. `web/src/lib/api.ts` — add field to `RunCreateRequest`
2. `web/src/lib/run-launcher-config.ts` — register field  
3. `web/src/components/runs/RunLaunchPanel.tsx` — add checkbox (trace-mode only, unchecked by default)
4. `api/app/runs/models.py` — add to run request model + CLI arg builder

## api.ts change
Add to `RunCreateRequest`:
```ts
wait_for_store_action?: boolean;
```

## run-launcher-config.ts change
Add `"wait_for_store_action"` to the `LauncherFieldId` union type.

## RunLaunchPanel.tsx change
Add a new checkbox inside the `className="grid three"` checkbox group, visible only in trace mode:
```tsx
{isTraceMode ? (
  <div className="launcher-field-group" {...focus("wait_for_store_action")}>
    <label className="checkbox">
      <input
        type="checkbox"
        checked={form.wait_for_store_action || false}
        onChange={(event) => {
          touch("wait_for_store_action");
          onFormChange((prev) => ({ ...prev, wait_for_store_action: event.target.checked }));
        }}
      />
      Wait for real store action
    </label>
  </div>
) : null}
```

## models.py change
Add to the Pydantic run create model:
```python
wait_for_store_action: bool = False
```

Add to the CLI arg builder (wherever `extra_args` or boolean flags are assembled):
```python
if self.wait_for_store_action:
    args.append("--wait-for-store-action")
```

## Done when
- The checkbox appears in the UI when trace mode is active
- It is unchecked by default
- Checking it and launching a run includes `--wait-for-store-action` in the command preview
