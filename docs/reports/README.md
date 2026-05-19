# Simulator reports

## Flow reliability

After running `./scripts/run_named_flow_regression.sh` from the repo root, summary artifacts are written to:

- `runs/flow-reliability-<date>.json` — machine-readable matrix
- `runs/flow-reliability-<date>.md` — operator table (exit code, verdict, `failure_class` counts)

Copy or archive those files here when you want a dated snapshot under version control.
