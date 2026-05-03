"use client";

import { useEffect, useMemo, useState } from "react";
import {
  cancelRun,
  createRun,
  fetchFlows,
  fetchRunLog,
  fetchRuns,
  type RunCreateRequest,
  type RunRow
} from "../lib/api";

const DEFAULT_FORM: RunCreateRequest = {
  flow: "doctor",
  plan: "sim_actors.json",
  timing: "fast",
  store_id: "",
  phone: "",
  all_users: false,
  no_auto_provision: false,
  post_order_actions: false,
  extra_args: []
};

export default function Page() {
  const [flows, setFlows] = useState<string[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [logText, setLogText] = useState<string>("");
  const [form, setForm] = useState<RunCreateRequest>(DEFAULT_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    fetchFlows().then(setFlows).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    const refreshRuns = () => {
      fetchRuns()
        .then((items) => {
          setRuns(items);
          if (!selectedRunId && items[0]) {
            setSelectedRunId(items[0].id);
          }
        })
        .catch((err: Error) => setError(err.message));
    };
    refreshRuns();
    const timer = window.setInterval(refreshRuns, 3000);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setLogText("");
      return;
    }
    const refreshLog = () => {
      fetchRunLog(selectedRunId)
        .then(setLogText)
        .catch((err: Error) => setError(err.message));
    };
    refreshLog();
    const timer = window.setInterval(refreshLog, 2000);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  async function onStartRun() {
    setError("");
    setIsSubmitting(true);
    try {
      const created = await createRun({
        ...form,
        store_id: form.store_id || undefined,
        phone: form.phone || undefined
      });
      setSelectedRunId(created.id);
      const refreshed = await fetchRuns();
      setRuns(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function onCancelSelected() {
    if (!selectedRunId) return;
    setError("");
    try {
      await cancelRun(selectedRunId);
      const refreshed = await fetchRuns();
      setRuns(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel run.");
    }
  }

  return (
    <main className="grid" style={{ gap: 16 }}>
      <div className="panel grid" style={{ gap: 8 }}>
        <h1>Fainzy Simulator Web Control</h1>
        <div className="muted">
          Run simulator flows, monitor progress, and inspect logs without CLI usage.
        </div>
      </div>

      {error ? (
        <div className="panel" style={{ borderColor: "#ef4444", color: "#b91c1c" }}>
          {error}
        </div>
      ) : null}

      <section className="grid two" style={{ alignItems: "start" }}>
        <div className="panel grid" style={{ gap: 12 }}>
          <h2>Start Run</h2>
          <div className="grid three">
            <label>
              Flow
              <select
                value={form.flow}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, flow: event.target.value }))
                }
              >
                {(flows.length ? flows : ["doctor"]).map((flow) => (
                  <option value={flow} key={flow}>
                    {flow}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Timing
              <select
                value={form.timing}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    timing: event.target.value as "fast" | "realistic"
                  }))
                }
              >
                <option value="fast">fast</option>
                <option value="realistic">realistic</option>
              </select>
            </label>
            <label>
              Plan
              <input
                value={form.plan}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, plan: event.target.value }))
                }
              />
            </label>
          </div>
          <div className="grid two">
            <label>
              Store ID (optional)
              <input
                value={form.store_id || ""}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, store_id: event.target.value }))
                }
              />
            </label>
            <label>
              Phone (optional)
              <input
                value={form.phone || ""}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, phone: event.target.value }))
                }
              />
            </label>
          </div>
          <div className="grid two">
            <label>
              <input
                type="checkbox"
                checked={Boolean(form.all_users)}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, all_users: event.target.checked }))
                }
              />
              {" "}Run all users
            </label>
            <label>
              <input
                type="checkbox"
                checked={Boolean(form.no_auto_provision)}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    no_auto_provision: event.target.checked
                  }))
                }
              />
              {" "}Disable auto-provision
            </label>
          </div>
          <div className="grid two">
            <button disabled={isSubmitting} onClick={onStartRun}>
              {isSubmitting ? "Starting..." : "Start Simulation"}
            </button>
            <button className="secondary" onClick={onCancelSelected} disabled={!selectedRunId}>
              Cancel Selected Run
            </button>
          </div>
        </div>

        <div className="panel grid" style={{ gap: 12 }}>
          <h2>Live Console</h2>
          {selectedRun ? (
            <div className="muted">
              Run #{selectedRun.id} ({selectedRun.status}) | {selectedRun.flow} |{" "}
              {selectedRun.store_id || "auto-store"}
            </div>
          ) : (
            <div className="muted">No run selected.</div>
          )}
          <pre className="log">{logText || "No log output yet."}</pre>
        </div>
      </section>

      <section className="panel">
        <h2 style={{ marginBottom: 12 }}>Recent Runs</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Flow</th>
              <th>Store</th>
              <th>Phone</th>
              <th>Created</th>
              <th>Exit</th>
              <th>Report</th>
              <th>Story</th>
              <th>Events</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                style={{
                  cursor: "pointer",
                  background: run.id === selectedRunId ? "#eef2ff" : "transparent"
                }}
              >
                <td>{run.id}</td>
                <td>{run.status}</td>
                <td>{run.flow}</td>
                <td>{run.store_id || "-"}</td>
                <td>{run.phone || "-"}</td>
                <td>{run.created_at}</td>
                <td>{run.exit_code ?? "-"}</td>
                <td>{run.report_path || "-"}</td>
                <td>{run.story_path || "-"}</td>
                <td>{run.events_path || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}

