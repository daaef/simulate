import type { RunRow } from "./api";

export function canStopRun(run: RunRow): boolean {
  if (run.control) {
    return run.control.can_stop;
  }
  return run.status.toLowerCase() === "running";
}

export function canDeleteRun(run: RunRow): boolean {
  if (run.control) {
    return run.control.can_delete;
  }
  return !canStopRun(run);
}

export function shouldPollRunLog(run: RunRow): boolean {
  if (run.control?.actively_running) {
    return true;
  }
  return run.status.toLowerCase() === "running";
}
