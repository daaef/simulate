"use client";

import { memo, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  cancelRun,
  createRun,
  fetchDashboardSummary,
  fetchFlows,
  fetchRunArtifactEvents,
  fetchRunArtifactText,
  fetchRunLog,
  fetchRunMetrics,
  fetchRuns,
  type DashboardSummary,
  type RunCreateRequest,
  type RunMetrics,
  type RunRow
} from "../lib/api";
import {
  GUIDE_COMBO_RULES,
  GUIDE_COMMAND_ROWS,
  GUIDE_FAILURE_HINTS,
  GUIDE_FLAG_ROWS,
  GUIDE_FLOW_MATRIX,
  PLAN_TEMPLATE,
  TIMING_REFERENCE
} from "../lib/command-guide";

type InspectorTab = "summary" | "report" | "story" | "events";
type GuideTab = "flows" | "commands" | "flags" | "plan" | "rules" | "failures";
type EventRow = Record<string, unknown>;
const EVENTS_PAGE_SIZE = 120;
const REPORT_PAGE_SIZE = 120000;

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

const EMPTY_SUMMARY: DashboardSummary = {
  total_runs: 0,
  success_rate: 0,
  status_breakdown: {
    queued: 0,
    running: 0,
    cancelling: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0
  },
  flow_breakdown: {}
};

const EMPTY_METRICS: RunMetrics = {
  total_events: 0,
  failed_events: 0,
  http_calls: 0,
  websocket_events: 0,
  avg_http_latency_ms: 0,
  top_actors: {},
  top_actions: {}
};

function isActiveStatus(status: string): boolean {
  return ["queued", "running", "cancelling"].includes(status.toLowerCase());
}

function logClassForLine(line: string): string {
  const lowered = line.toLowerCase();
  if (lowered.includes("failed") || lowered.includes("error")) return "log-line-error";
  if (lowered.includes("rejected")) return "log-line-warn";
  if (lowered.startsWith("store:")) return "log-line-store";
  if (lowered.startsWith("user")) return "log-line-user";
  if (lowered.startsWith("robot")) return "log-line-robot";
  if (lowered.startsWith("trace:")) return "log-line-trace";
  if (lowered.startsWith("websocket:")) return "log-line-websocket";
  if (lowered.startsWith("main:")) return "log-line-main";
  return "log-line-default";
}

function comboClass(verdict: string): string {
  if (verdict === "valid") return "chip chip-valid";
  if (verdict === "invalid") return "chip chip-invalid";
  return "chip chip-conditional";
}

function eventField(event: EventRow, key: string): string {
  const value = event[key];
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function eventTimestamp(event: EventRow): string {
  return eventField(event, "ts") || eventField(event, "timestamp");
}

function eventStatus(event: EventRow): string {
  const explicit = eventField(event, "status");
  if (explicit) return explicit;
  const ok = event["ok"];
  if (typeof ok === "boolean") return ok ? "ok" : "failed";
  return "";
}

function eventMessage(event: EventRow): string {
  return (
    eventField(event, "message") ||
    eventField(event, "details") ||
    eventField(event, "detail") ||
    eventField(event, "response_preview")
  );
}

const MarkdownPane = memo(function MarkdownPane({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>;
});

export default function Page() {
  const [flows, setFlows] = useState<string[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [summary, setSummary] = useState<DashboardSummary>(EMPTY_SUMMARY);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedTab, setSelectedTab] = useState<InspectorTab>("summary");
  const [guideTab, setGuideTab] = useState<GuideTab>("flows");
  const [eventFilter, setEventFilter] = useState("");
  const [logText, setLogText] = useState("");
  const [reportText, setReportText] = useState("");
  const [storyText, setStoryText] = useState("");
  const [events, setEvents] = useState<EventRow[]>([]);
  const [eventsOffset, setEventsOffset] = useState(0);
  const [eventsTotalCount, setEventsTotalCount] = useState(0);
  const [reportPage, setReportPage] = useState(1);
  const [metrics, setMetrics] = useState<RunMetrics>(EMPTY_METRICS);
  const [reportLoading, setReportLoading] = useState(false);
  const [storyLoading, setStoryLoading] = useState(false);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [reportLoadedRunId, setReportLoadedRunId] = useState<number | null>(null);
  const [storyLoadedRunId, setStoryLoadedRunId] = useState<number | null>(null);
  const [metricsLoadedRunId, setMetricsLoadedRunId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState<RunCreateRequest>(DEFAULT_FORM);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchFlows().then(setFlows).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    const refreshRunsAndSummary = () => {
      Promise.all([fetchRuns(), fetchDashboardSummary()])
        .then(([runsPayload, summaryPayload]) => {
          setRuns(runsPayload);
          setSummary(summaryPayload);
          if (!selectedRunId && runsPayload[0]) {
            setSelectedRunId(runsPayload[0].id);
          }
        })
        .catch((err: Error) => setError(err.message));
    };
    refreshRunsAndSummary();
    const timer = window.setInterval(refreshRunsAndSummary, 5000);
    return () => window.clearInterval(timer);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setLogText("");
      return;
    }
    const status = (runs.find((run) => run.id === selectedRunId)?.status || "").toLowerCase();
    const shouldPoll = isActiveStatus(status);
    const refreshLog = () => {
      fetchRunLog(selectedRunId)
        .then(setLogText)
        .catch((err: Error) => setError(err.message));
    };
    refreshLog();
    if (!shouldPoll) return;
    const timer = window.setInterval(refreshLog, 1000);
    return () => window.clearInterval(timer);
  }, [selectedRunId, runs]);

  useEffect(() => {
    setReportText("");
    setStoryText("");
    setEvents([]);
    setEventsOffset(0);
    setEventsTotalCount(0);
    setReportPage(1);
    setMetrics(EMPTY_METRICS);
    setReportLoadedRunId(null);
    setStoryLoadedRunId(null);
    setMetricsLoadedRunId(null);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || selectedTab !== "summary") return;
    const status = (runs.find((run) => run.id === selectedRunId)?.status || "").toLowerCase();
    const shouldPoll = isActiveStatus(status);
    const refreshMetrics = () => {
      setMetricsLoading(true);
      fetchRunMetrics(selectedRunId)
        .then((payload) => {
          setMetrics(payload.metrics);
          setMetricsLoadedRunId(selectedRunId);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setMetricsLoading(false));
    };
    refreshMetrics();
    if (!shouldPoll) return;
    const timer = window.setInterval(refreshMetrics, 5000);
    return () => window.clearInterval(timer);
  }, [selectedRunId, selectedTab, runs]);

  useEffect(() => {
    if (!selectedRunId || selectedTab !== "report") return;
    if (reportLoadedRunId === selectedRunId) return;
    setReportLoading(true);
    fetchRunArtifactText(selectedRunId, "report")
      .then((payload) => {
        setReportText(payload.available && payload.content ? payload.content : "");
        setReportLoadedRunId(selectedRunId);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setReportLoading(false));
  }, [selectedRunId, selectedTab, reportLoadedRunId]);

  useEffect(() => {
    if (!selectedRunId || selectedTab !== "story") return;
    if (storyLoadedRunId === selectedRunId) return;
    setStoryLoading(true);
    fetchRunArtifactText(selectedRunId, "story")
      .then((payload) => {
        setStoryText(payload.available && payload.content ? payload.content : "");
        setStoryLoadedRunId(selectedRunId);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setStoryLoading(false));
  }, [selectedRunId, selectedTab, storyLoadedRunId]);

  useEffect(() => {
    if (!selectedRunId || selectedTab !== "events") return;
    const status = (runs.find((run) => run.id === selectedRunId)?.status || "").toLowerCase();
    const shouldPoll = isActiveStatus(status);
    const refreshEvents = () => {
      setEventsLoading(true);
      fetchRunArtifactEvents(selectedRunId, {
        offset: eventsOffset,
        limit: EVENTS_PAGE_SIZE,
        compact: true
      })
        .then((payload) => {
          const content = payload.available && payload.content ? payload.content : [];
          setEvents(content);
          setEventsTotalCount(payload.total_count ?? content.length);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setEventsLoading(false));
    };
    refreshEvents();
    if (!shouldPoll) return;
    const timer = window.setInterval(refreshEvents, 5000);
    return () => window.clearInterval(timer);
  }, [selectedRunId, selectedTab, runs, eventsOffset]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  const filteredEvents = useMemo(() => {
    if (!eventFilter.trim()) return events;
    const needle = eventFilter.toLowerCase();
    return events.filter((event) => JSON.stringify(event).toLowerCase().includes(needle));
  }, [events, eventFilter]);

  const apiEvents = useMemo(
    () =>
      filteredEvents.filter(
        (event) =>
          typeof event["method"] === "string" &&
          String(event["method"]).length > 0 &&
          typeof event["endpoint"] === "string"
      ),
    [filteredEvents]
  );

  const maxFlowCount = useMemo(() => {
    const values = Object.values(summary.flow_breakdown);
    return values.length ? Math.max(...values) : 1;
  }, [summary.flow_breakdown]);

  const maxStatusCount = useMemo(() => {
    const values = Object.values(summary.status_breakdown);
    return values.length ? Math.max(...values) : 1;
  }, [summary.status_breakdown]);

  const reportRuns = useMemo(
    () => runs.filter((run) => Boolean(run.report_path)),
    [runs]
  );

  const commandPreview = useMemo(() => {
    const parts: string[] = [
      "python3",
      "-m",
      "simulate",
      form.flow || "doctor",
      "--plan",
      form.plan || "sim_actors.json",
      "--timing",
      form.timing
    ];
    if (form.store_id && form.store_id.trim()) {
      parts.push("--store", form.store_id.trim());
    }
    if (form.phone && form.phone.trim()) {
      parts.push("--phone", form.phone.trim());
    }
    if (form.all_users) parts.push("--all-users");
    if (form.no_auto_provision) parts.push("--no-auto-provision");
    if (form.post_order_actions) parts.push("--post-order-actions");
    if (form.extra_args && form.extra_args.length) {
      parts.push(...form.extra_args);
    }
    return parts.join(" ");
  }, [form]);

  const reportTotalPages = Math.max(1, Math.ceil(reportText.length / REPORT_PAGE_SIZE));
  const safeReportPage = Math.min(reportPage, reportTotalPages);
  const reportSlice = reportText.slice(
    (safeReportPage - 1) * REPORT_PAGE_SIZE,
    safeReportPage * REPORT_PAGE_SIZE
  );

  const eventsPageCount = Math.max(1, Math.ceil(eventsTotalCount / EVENTS_PAGE_SIZE));
  const eventsCurrentPage = Math.floor(eventsOffset / EVENTS_PAGE_SIZE) + 1;

  useEffect(() => {
    if (reportPage > reportTotalPages) {
      setReportPage(reportTotalPages);
    }
  }, [reportPage, reportTotalPages]);

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
      const [runsPayload, summaryPayload] = await Promise.all([fetchRuns(), fetchDashboardSummary()]);
      setRuns(runsPayload);
      setSummary(summaryPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function onCancelRun(runId: number) {
    setError("");
    try {
      await cancelRun(runId);
      const [runsPayload, summaryPayload] = await Promise.all([fetchRuns(), fetchDashboardSummary()]);
      setRuns(runsPayload);
      setSummary(summaryPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel run.");
    }
  }

  const logLines = logText.split("\n").filter((line) => line.length > 0);

  return (
    <main className="grid" style={{ gap: 16 }}>
      <div className="panel grid" style={{ gap: 8 }}>
        <h1>Fainzy Simulator Web Control</h1>
        <div className="muted">
          Run simulator flows, monitor progress, inspect stories/reports/events, and track system health.
        </div>
      </div>

      {error ? (
        <div className="panel" style={{ borderColor: "#ef4444", color: "#b91c1c" }}>
          {error}
        </div>
      ) : null}

      <section className="grid three">
        <div className="panel stat">
          <div className="stat-label">Total Runs</div>
          <div className="stat-value">{summary.total_runs}</div>
        </div>
        <div className="panel stat">
          <div className="stat-label">Success Rate</div>
          <div className="stat-value">{summary.success_rate}%</div>
        </div>
        <div className="panel stat">
          <div className="stat-label">Running</div>
          <div className="stat-value">{summary.status_breakdown.running || 0}</div>
        </div>
      </section>

      <section className="grid two" style={{ alignItems: "start" }}>
        <div className="panel grid" style={{ gap: 12 }}>
          <h2>Start Run</h2>
          <div className="grid three">
            <label>
              Flow
              <select
                value={form.flow}
                onChange={(event) => setForm((prev) => ({ ...prev, flow: event.target.value }))}
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
                  setForm((prev) => ({ ...prev, timing: event.target.value as "fast" | "realistic" }))
                }
              >
                <option value="fast">fast</option>
                <option value="realistic">realistic</option>
              </select>
            </label>
            <label>
              Plan
              <input value={form.plan} onChange={(event) => setForm((prev) => ({ ...prev, plan: event.target.value }))} />
            </label>
          </div>
          <div className="grid two">
            <label>
              Store ID (optional)
              <input
                value={form.store_id || ""}
                onChange={(event) => setForm((prev) => ({ ...prev, store_id: event.target.value }))}
              />
            </label>
            <label>
              Phone (optional)
              <input value={form.phone || ""} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} />
            </label>
          </div>
          <div className="grid two">
            <label>
              <input
                type="checkbox"
                checked={Boolean(form.all_users)}
                onChange={(event) => setForm((prev) => ({ ...prev, all_users: event.target.checked }))}
              />{" "}
              Run all users
            </label>
            <label>
              <input
                type="checkbox"
                checked={Boolean(form.no_auto_provision)}
                onChange={(event) => setForm((prev) => ({ ...prev, no_auto_provision: event.target.checked }))}
              />{" "}
              Disable auto-provision
            </label>
          </div>
          <div className="grid two">
            <button disabled={isSubmitting} onClick={onStartRun}>
              {isSubmitting ? "Starting..." : "Start Simulation"}
            </button>
            <button
              className="secondary"
              disabled={!selectedRun || !isActiveStatus(selectedRun.status)}
              onClick={() => selectedRun && onCancelRun(selectedRun.id)}
            >
              Stop Selected Run
            </button>
          </div>
          <div className="muted">Resolved command preview</div>
          <pre className="artifact command-preview">
            <code>{commandPreview}</code>
          </pre>
        </div>

        <div className="panel grid" style={{ gap: 12 }}>
          <h2>Live Console</h2>
          {selectedRun ? (
            <div className="muted">
              Run #{selectedRun.id} ({selectedRun.status}) | {selectedRun.flow} | {selectedRun.store_id || "auto-store"}
            </div>
          ) : (
            <div className="muted">No run selected.</div>
          )}
          <pre className="log">
            {logLines.length ? (
              logLines.map((line, index) => (
                <span key={`${index}-${line}`} className={logClassForLine(line)}>
                  {line}
                  {"\n"}
                </span>
              ))
            ) : (
              <span className="log-line-default">No log output yet.</span>
            )}
          </pre>
        </div>
      </section>

      <section className="panel grid" style={{ gap: 12 }}>
        <h2>Flow Planner & Command Guide</h2>
        <div className="muted">
          Use this reference to choose the right flow, flags, and command combinations without leaving the GUI.
        </div>
        <div className="tabs">
          {(
            [
              ["flows", "Flow Matrix"],
              ["commands", "Commands"],
              ["flags", "Flags"],
              ["plan", "Plan JSON"],
              ["rules", "Combo Rules"],
              ["failures", "Failure Hints"]
            ] as Array<[GuideTab, string]>
          ).map(([value, label]) => (
            <button
              key={value}
              className={guideTab === value ? "" : "secondary"}
              onClick={() => setGuideTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {guideTab === "flows" ? (
          <div className="events-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Flow</th>
                  <th>Mode</th>
                  <th>Suite/Scenarios</th>
                  <th>What It Tests</th>
                  <th>Prerequisites</th>
                  <th>Optional Flags</th>
                  <th>Artifacts</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_FLOW_MATRIX.map((row) => (
                  <tr key={row.flow}>
                    <td>
                      <code>{row.flow}</code>
                    </td>
                    <td>{row.resolved_mode}</td>
                    <td>{row.suite_or_scenarios}</td>
                    <td>{row.what_it_tests}</td>
                    <td>{row.prerequisites}</td>
                    <td>{row.optional_flags}</td>
                    <td>{row.artifacts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {guideTab === "commands" ? (
          <div className="events-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Command Pattern</th>
                  <th>Purpose</th>
                  <th>When To Use</th>
                  <th>Expected Result</th>
                  <th>Common Failure Signature</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_COMMAND_ROWS.map((row) => (
                  <tr key={row.command}>
                    <td>
                      <code>{row.command}</code>
                    </td>
                    <td>{row.purpose}</td>
                    <td>{row.when_to_use}</td>
                    <td>{row.expected_result}</td>
                    <td>{row.common_failure}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {guideTab === "flags" ? (
          <div className="events-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Flag</th>
                  <th>Type</th>
                  <th>Default</th>
                  <th>Effect</th>
                  <th>Constraints</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_FLAG_ROWS.map((row) => (
                  <tr key={row.flag}>
                    <td>
                      <code>{row.flag}</code>
                    </td>
                    <td>{row.type}</td>
                    <td>{row.default_value}</td>
                    <td>{row.effect}</td>
                    <td>{row.constraints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {guideTab === "plan" ? (
          <div className="grid" style={{ gap: 10 }}>
            <div className="muted">
              Minimum plan data: users with phone + GPS and stores with store_id. Simulator handles onboarding, provisioning, ordering, post-order actions, and report generation from this input.
            </div>
            <pre className="artifact command-preview">
              <code>{PLAN_TEMPLATE}</code>
            </pre>
            <div className="events-table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Timing</th>
                    <th>Store Decision Delay</th>
                    <th>Store Prep Delay</th>
                    <th>Robot Progression Delay</th>
                    <th>Auto-Cancel Wait</th>
                  </tr>
                </thead>
                <tbody>
                  {TIMING_REFERENCE.map((row) => (
                    <tr key={row.profile}>
                      <td>
                        <code>{row.profile}</code>
                      </td>
                      <td>{row.store_decision_delay}</td>
                      <td>{row.store_prep_delay}</td>
                      <td>{row.robot_progression_delay}</td>
                      <td>{row.auto_cancel_wait}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
        {guideTab === "rules" ? (
          <div className="events-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Combination</th>
                  <th>Verdict</th>
                  <th>Why</th>
                  <th>Fix</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_COMBO_RULES.map((row) => (
                  <tr key={row.combination}>
                    <td>{row.combination}</td>
                    <td>
                      <span className={comboClass(row.verdict)}>{row.verdict}</span>
                    </td>
                    <td>{row.explanation}</td>
                    <td>{row.fix}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {guideTab === "failures" ? (
          <div className="events-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Failure Signature</th>
                  <th>Likely Cause</th>
                  <th>Next Action</th>
                </tr>
              </thead>
              <tbody>
                {GUIDE_FAILURE_HINTS.map((row) => (
                  <tr key={row.signature}>
                    <td>{row.signature}</td>
                    <td>{row.likely_cause}</td>
                    <td>{row.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
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
              <th>Actions</th>
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
                <td>
                  <div className="row-actions">
                    <button className="secondary small" onClick={() => setSelectedRunId(run.id)}>
                      Select
                    </button>
                    <button
                      className="small"
                      disabled={!isActiveStatus(run.status)}
                      onClick={(event) => {
                        event.stopPropagation();
                        onCancelRun(run.id);
                      }}
                    >
                      Stop
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="grid two" style={{ alignItems: "start" }}>
        <div className="panel grid" style={{ gap: 10 }}>
          <h2>Status Chart</h2>
          {Object.entries(summary.status_breakdown).map(([key, value]) => (
            <div key={key} className="bar-row">
              <div className="bar-label">{key}</div>
              <div className="bar-track">
                <div
                  className="bar-fill status"
                  style={{ width: `${Math.max(6, (value / Math.max(1, maxStatusCount)) * 100)}%` }}
                />
              </div>
              <div className="bar-value">{value}</div>
            </div>
          ))}
        </div>
        <div className="panel grid" style={{ gap: 10 }}>
          <h2>Flow Chart</h2>
          {Object.entries(summary.flow_breakdown).length ? (
            Object.entries(summary.flow_breakdown).map(([key, value]) => (
              <div key={key} className="bar-row">
                <div className="bar-label">{key}</div>
                <div className="bar-track">
                  <div
                    className="bar-fill flow"
                    style={{ width: `${Math.max(6, (value / Math.max(1, maxFlowCount)) * 100)}%` }}
                  />
                </div>
                <div className="bar-value">{value}</div>
              </div>
            ))
          ) : (
            <div className="muted">No completed runs yet.</div>
          )}
        </div>
      </section>

      <section className="panel grid" style={{ gap: 12 }}>
        <h2>Run Inspector</h2>
        <div className="tabs">
          {(["summary", "report", "story", "events"] as InspectorTab[]).map((tab) => (
            <button key={tab} className={selectedTab === tab ? "" : "secondary"} onClick={() => setSelectedTab(tab)}>
              {tab}
            </button>
          ))}
        </div>
        {selectedRun ? (
          <div className="muted">
            Selected Run #{selectedRun.id} ({selectedRun.status}) | command: <code>{selectedRun.command}</code>
          </div>
        ) : (
          <div className="muted">Select a run from the table below.</div>
        )}
        {selectedTab === "summary" ? (
          <div className="grid" style={{ gap: 12 }}>
            {metricsLoading ? <div className="muted">Loading summary metrics...</div> : null}
            <div className="grid two">
              <div className="panel">
                <div className="stat-label">Total Events</div>
                <div className="stat-value">{metrics.total_events}</div>
              </div>
              <div className="panel">
                <div className="stat-label">Failed Events</div>
                <div className="stat-value">{metrics.failed_events}</div>
              </div>
              <div className="panel">
                <div className="stat-label">HTTP Calls</div>
                <div className="stat-value">{metrics.http_calls}</div>
              </div>
              <div className="panel">
                <div className="stat-label">WebSocket Events</div>
                <div className="stat-value">{metrics.websocket_events}</div>
              </div>
              <div className="panel">
                <div className="stat-label">Avg HTTP Latency (ms)</div>
                <div className="stat-value">{metrics.avg_http_latency_ms ?? 0}</div>
              </div>
            </div>
            {metrics.total_events === 0 ? (
              <div className="muted">No event metrics for this run yet.</div>
            ) : (
              <div className="grid two">
                <div className="panel">
                  <div className="stat-label">Top Actors</div>
                  <table>
                    <thead>
                      <tr>
                        <th>Actor</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(metrics.top_actors || {}).map(([actor, count]) => (
                        <tr key={`actor-${actor}`}>
                          <td>{actor}</td>
                          <td>{count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="panel">
                  <div className="stat-label">Top Actions</div>
                  <table>
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(metrics.top_actions || {}).map(([action, count]) => (
                        <tr key={`action-${action}`}>
                          <td>{action}</td>
                          <td>{count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : null}
        {selectedTab === "report" ? (
          <div className="grid" style={{ gap: 10 }}>
            <div className="muted">Available Reports ({reportRuns.length})</div>
            {reportRuns.length ? (
              <div className="events-table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Flow</th>
                      <th>Store</th>
                      <th>Created</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportRuns.map((run) => (
                      <tr key={`report-run-${run.id}`}>
                        <td>#{run.id}</td>
                        <td>{run.flow}</td>
                        <td>{run.store_id || "-"}</td>
                        <td>{run.created_at}</td>
                        <td>{run.status}</td>
                        <td>
                          <button
                            className="secondary small"
                            onClick={() => {
                              setSelectedRunId(run.id);
                              setSelectedTab("report");
                            }}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="muted">No reports captured yet.</div>
            )}
            {reportLoading ? <div className="muted">Loading report...</div> : null}
            {reportText ? (
              <div className="row-actions">
                <button
                  className="secondary small"
                  disabled={safeReportPage <= 1}
                  onClick={() => setReportPage((page) => Math.max(1, page - 1))}
                >
                  Prev Chunk
                </button>
                <div className="muted">
                  Chunk {safeReportPage}/{reportTotalPages}
                </div>
                <button
                  className="secondary small"
                  disabled={safeReportPage >= reportTotalPages}
                  onClick={() => setReportPage((page) => Math.min(reportTotalPages, page + 1))}
                >
                  Next Chunk
                </button>
              </div>
            ) : null}
            <div className="artifact markdown-view">
              {reportText ? (
                <MarkdownPane text={reportSlice} />
              ) : (
                <div className="muted">Report artifact is not available yet.</div>
              )}
            </div>
          </div>
        ) : null}
        {selectedTab === "story" ? (
          <div className="artifact markdown-view">
            {storyLoading ? <div className="muted">Loading story...</div> : null}
            {storyText ? (
              <MarkdownPane text={storyText} />
            ) : (
              <div className="muted">Story artifact is not available yet.</div>
            )}
          </div>
        ) : null}
        {selectedTab === "events" ? (
          <div className="grid" style={{ gap: 10 }}>
            <input placeholder="Filter events..." value={eventFilter} onChange={(event) => setEventFilter(event.target.value)} />
            {eventsLoading ? <div className="muted">Loading events...</div> : null}
            <div className="row-actions">
              <button
                className="secondary small"
                disabled={eventsCurrentPage <= 1}
                onClick={() => setEventsOffset((offset) => Math.max(0, offset - EVENTS_PAGE_SIZE))}
              >
                Prev Page
              </button>
              <div className="muted">
                Page {eventsCurrentPage}/{eventsPageCount} ({eventsTotalCount} total)
              </div>
              <button
                className="secondary small"
                disabled={eventsCurrentPage >= eventsPageCount}
                onClick={() =>
                  setEventsOffset((offset) =>
                    Math.min((eventsPageCount - 1) * EVENTS_PAGE_SIZE, offset + EVENTS_PAGE_SIZE)
                  )
                }
              >
                Next Page
              </button>
            </div>
            <div className="muted">API Calls ({apiEvents.length})</div>
            {apiEvents.length ? (
              <div className="events-table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Method</th>
                      <th>Endpoint</th>
                      <th>HTTP</th>
                      <th>Latency (ms)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiEvents.slice(0, 250).map((event, index) => (
                      <tr key={`api-${index}-${eventField(event, "action")}`}>
                        <td>{eventTimestamp(event)}</td>
                        <td>
                          <span className={`method method-${String(event["method"] || "").toLowerCase()}`}>
                            {eventField(event, "method")}
                          </span>
                        </td>
                        <td>{eventField(event, "endpoint") || eventField(event, "full_url")}</td>
                        <td>{eventField(event, "http_status")}</td>
                        <td>{eventField(event, "latency_ms")}</td>
                        <td>{eventStatus(event)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="muted">No API call events for this run.</div>
            )}
            <div className="muted">Event Stream ({filteredEvents.length})</div>
            <div className="events-table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Status</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.slice(0, 400).map((event, index) => (
                    <tr key={`${index}-${eventField(event, "action")}`}>
                      <td>{eventTimestamp(event)}</td>
                      <td>{eventField(event, "actor")}</td>
                      <td>{eventField(event, "action")}</td>
                      <td>{eventStatus(event)}</td>
                      <td>{eventMessage(event)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
