"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ErrorBanner } from "../../../components/ErrorBanner";
import { LastUpdatedIndicator } from "../../../components/LastUpdatedIndicator";
import { useFocusTrap } from "../../../lib/useFocusTrap";
import { DistributionDonut } from "../../../components/charts/DistributionDonut";
import { HorizontalBarChart } from "../../../components/charts/HorizontalBarChart";
import {
  ApiRequestError,
  fetchArchivedProfiles,
  fetchArchivedSchedules,
  fetchArchivedIntegrationMappings,
  fetchArchiveRuns,
  fetchArchiveSummary,
  fetchRetentionSummary,
  restoreRun,
  restoreRunProfile,
  restoreGitHubIntegrationMapping,
  setScheduleStatus,
  purgeRun,
  purgeRunProfile,
  purgeSchedule,
  purgeIntegrationMapping,
  type IntegrationMapping,
  type RetentionSummary,
  type RunProfile,
  type Schedule,
  type ArchiveRun,
  type ArchiveSummary,
} from "../../../lib/api";

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function formatDate(d: Date): string {
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function toMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Failed to load archives";
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded") return "status-success";
  if (normalized === "failed") return "status-danger";
  if (normalized === "cancelled") return "status-warning";
  return "status-info";
}

type LifecycleState = "active" | "archive_candidate" | "raw_purge_candidate" | "archived";

function lifecyclePillClass(state: LifecycleState): string {
  if (state === "raw_purge_candidate") return "status-danger";
  if (state === "archive_candidate") return "status-warning";
  if (state === "active") return "status-success";
  return "status-info";
}

function lifecyclePillLabel(state: LifecycleState): string {
  if (state === "raw_purge_candidate") return "Purge-ready";
  if (state === "archive_candidate") return "Archive-ready";
  if (state === "active") return "Active";
  return "Archived";
}

function LifecyclePill({ state }: { state: LifecycleState }) {
  return (
    <span className={`status-pill ${lifecyclePillClass(state)}`} style={{ fontSize: "11px" }}>
      {lifecyclePillLabel(state)}
    </span>
  );
}

function archivedAtState(archivedAt: string | null | undefined, archiveDays: number): LifecycleState {
  if (!archivedAt) return "archived";
  const ageDays = (Date.now() - new Date(archivedAt).getTime()) / 86_400_000;
  return ageDays >= archiveDays ? "raw_purge_candidate" : "archived";
}

interface PurgeConfirmState {
  kind: "run" | "profile" | "schedule" | "mapping";
  ids: number[];
  label: string;
}

const PURGE_CONFIRM_PHRASE = "purge";

function PurgeConfirmModal({
  state,
  onConfirm,
  onCancel,
}: {
  state: PurgeConfirmState;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const count = state.ids.length;
  const [confirmText, setConfirmText] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(true, panelRef);
  const canConfirm = confirmText.trim().toLowerCase() === PURGE_CONFIRM_PHRASE;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      role="presentation"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="purge-confirm-title"
        style={{
          backgroundColor: "var(--bg-secondary)",
          padding: "24px",
          borderRadius: "8px",
          width: "420px",
          border: "1px solid var(--border-primary)",
        }}
      >
        <h3 id="purge-confirm-title" style={{ margin: "0 0 12px 0", color: "var(--text-primary)" }}>
          Permanently delete {count === 1 ? state.label : `${count} items`}?
        </h3>
        <p style={{ margin: "0 0 12px 0", color: "var(--text-secondary)", fontSize: "14px" }}>
          This permanently removes {count === 1 ? "this item" : "these items"} and all associated
          artifacts. It cannot be undone.
        </p>
        <label className="muted" style={{ fontSize: "13px", display: "block" }}>
          Type <strong>{PURGE_CONFIRM_PHRASE}</strong> to confirm
          <input
            className="purge-confirm-input"
            value={confirmText}
            onChange={(event) => setConfirmText(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <div style={{ display: "flex", gap: "12px", marginTop: 16 }}>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            style={{
              flex: 1,
              padding: "10px 16px",
              backgroundColor: "var(--method-delete-bg)",
              color: "var(--method-delete-text)",
              border: "1px solid var(--method-delete-border)",
              borderRadius: "6px",
              cursor: canConfirm ? "pointer" : "not-allowed",
              fontWeight: 500,
              opacity: canConfirm ? 1 : 0.55,
            }}
          >
            Delete permanently
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="secondary"
            style={{ flex: 1, padding: "10px 16px", borderRadius: "6px", cursor: "pointer", fontWeight: 500 }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function BulkActionBar({
  selectedCount,
  onPurge,
  onClear,
  busy,
}: {
  selectedCount: number;
  onPurge: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  if (selectedCount === 0) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "8px 12px",
        backgroundColor: "var(--bg-tertiary, var(--bg-secondary))",
        border: "1px solid var(--border-primary)",
        borderRadius: "6px",
        marginBottom: "8px",
      }}
    >
      <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
        {selectedCount} selected
      </span>
      <button
        className="small"
        disabled={busy}
        onClick={onPurge}
        style={{
          backgroundColor: "var(--method-delete-bg)",
          color: "var(--method-delete-text)",
          border: "1px solid var(--method-delete-border)",
          borderRadius: "4px",
          padding: "4px 12px",
          cursor: "pointer",
          fontSize: "13px",
        }}
      >
        Delete permanently ({selectedCount})
      </button>
      <button className="secondary small" disabled={busy} onClick={onClear}>
        Clear
      </button>
    </div>
  );
}

export default function ArchivesPage() {
  const [summary, setSummary] = useState<ArchiveSummary | null>(null);
  const [retentionSummary, setRetentionSummary] = useState<RetentionSummary | null>(null);
  const [runs, setRuns] = useState<ArchiveRun[]>([]);
  const [archivedProfiles, setArchivedProfiles] = useState<RunProfile[]>([]);
  const [archivedSchedules, setArchivedSchedules] = useState<Schedule[]>([]);
  const [archivedMappings, setArchivedMappings] = useState<IntegrationMapping[]>([]);

  // Search per section
  const [runQuery, setRunQuery] = useState("");
  const [profileQuery, setProfileQuery] = useState("");
  const [scheduleQuery, setScheduleQuery] = useState("");
  const [mappingQuery, setMappingQuery] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [purgeConfirm, setPurgeConfirm] = useState<PurgeConfirmState | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  // Selection state per section
  const [selectedRunIds, setSelectedRunIds] = useState<Set<number>>(new Set());
  const [selectedProfileIds, setSelectedProfileIds] = useState<Set<number>>(new Set());
  const [selectedScheduleIds, setSelectedScheduleIds] = useState<Set<number>>(new Set());
  const [selectedMappingIds, setSelectedMappingIds] = useState<Set<number>>(new Set());

  const loadArchives = useCallback(async () => {
    const [summaryPayload, retentionPayload, runsPayload, profilesPayload, schedulesPayload, mappingsPayload] =
      await Promise.all([
        fetchArchiveSummary(),
        fetchRetentionSummary(),
        fetchArchiveRuns(100, 0),
        fetchArchivedProfiles(),
        fetchArchivedSchedules(),
        fetchArchivedIntegrationMappings(),
      ]);
    setSummary(summaryPayload);
    setRetentionSummary(retentionPayload);
    setRuns(runsPayload.runs);
    setArchivedProfiles(profilesPayload);
    setArchivedSchedules(schedulesPayload);
    setArchivedMappings(mappingsPayload);
    setError(null);
    setLastUpdatedAt(new Date());
  }, []);

  useEffect(() => {
    void loadArchives().catch((caughtError) => setError(toMessage(caughtError)));
  }, [loadArchives]);

  // ── Filtered lists ────────────────────────────────────────────────────────

  const filteredRuns = useMemo(() => {
    const needle = runQuery.trim().toLowerCase();
    if (!needle) return runs;
    return runs.filter((run) =>
      [run.id, run.flow, run.status, run.store_id, run.phone, run.store_name, run.user_name,
       run.lifecycle_state, run.retained_summary?.narrative]
        .join(" ").toLowerCase().includes(needle)
    );
  }, [runQuery, runs]);

  const filteredProfiles = useMemo(() => {
    const needle = profileQuery.trim().toLowerCase();
    if (!needle) return archivedProfiles;
    return archivedProfiles.filter((p) =>
      [p.name, p.flow, p.description, p.archived_at].join(" ").toLowerCase().includes(needle)
    );
  }, [profileQuery, archivedProfiles]);

  const filteredSchedules = useMemo(() => {
    const needle = scheduleQuery.trim().toLowerCase();
    if (!needle) return archivedSchedules;
    return archivedSchedules.filter((s) =>
      [s.name, s.description, s.timezone, s.schedule_type, s.updated_at]
        .join(" ").toLowerCase().includes(needle)
    );
  }, [scheduleQuery, archivedSchedules]);

  const filteredMappings = useMemo(() => {
    const needle = mappingQuery.trim().toLowerCase();
    if (!needle) return archivedMappings;
    return archivedMappings.filter((m) =>
      [m.project, m.environment, m.profile_name, m.archived_at]
        .join(" ").toLowerCase().includes(needle)
    );
  }, [mappingQuery, archivedMappings]);

  // ── Checkbox helpers ──────────────────────────────────────────────────────

  function toggleId<T extends number>(set: Set<T>, id: T): Set<T> {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  }

  function allSelected(ids: number[], selected: Set<number>): boolean {
    return ids.length > 0 && ids.every((id) => selected.has(id));
  }

  function toggleAll(ids: number[], selected: Set<number>, set: (s: Set<number>) => void) {
    if (allSelected(ids, selected)) set(new Set());
    else set(new Set(ids));
  }

  // ── Restore actions ───────────────────────────────────────────────────────

  const restoreProfile = async (profileId: number) => {
    setBusy(true);
    try {
      await restoreRunProfile(profileId);
      const [profilesPayload, schedulesPayload, mappingsPayload] = await Promise.all([
        fetchArchivedProfiles(),
        fetchArchivedSchedules(),
        fetchArchivedIntegrationMappings(),
      ]);
      setArchivedProfiles(profilesPayload);
      setArchivedSchedules(schedulesPayload);
      setArchivedMappings(mappingsPayload);
      setSelectedProfileIds((s) => { const n = new Set(s); n.delete(profileId); return n; });
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
    }
  };

  const restoreSchedule = async (scheduleId: number) => {
    setBusy(true);
    try {
      await setScheduleStatus(scheduleId, "restore");
      const schedulesPayload = await fetchArchivedSchedules();
      setArchivedSchedules(schedulesPayload);
      setSelectedScheduleIds((s) => { const n = new Set(s); n.delete(scheduleId); return n; });
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
    }
  };

  const restoreArchivedRun = async (runId: number) => {
    setBusy(true);
    try {
      await restoreRun(runId);
      const runsPayload = await fetchArchiveRuns(100, 0);
      setRuns(runsPayload.runs);
      setSelectedRunIds((s) => { const n = new Set(s); n.delete(runId); return n; });
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
    }
  };

  const restoreMapping = async (mappingId: number) => {
    setBusy(true);
    try {
      await restoreGitHubIntegrationMapping(mappingId);
      const mappingsPayload = await fetchArchivedIntegrationMappings();
      setArchivedMappings(mappingsPayload);
      setSelectedMappingIds((s) => { const n = new Set(s); n.delete(mappingId); return n; });
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
    }
  };

  // ── Purge execution ───────────────────────────────────────────────────────

  const executePurge = async () => {
    if (!purgeConfirm) return;
    setBusy(true);
    try {
      const { kind, ids } = purgeConfirm;
      if (kind === "run") {
        await Promise.all(ids.map((id) => purgeRun(id)));
        const runsPayload = await fetchArchiveRuns(100, 0);
        setRuns(runsPayload.runs);
        setSelectedRunIds(new Set());
      } else if (kind === "profile") {
        await Promise.all(ids.map((id) => purgeRunProfile(id)));
        const profilesPayload = await fetchArchivedProfiles();
        setArchivedProfiles(profilesPayload);
        setSelectedProfileIds(new Set());
      } else if (kind === "schedule") {
        await Promise.all(ids.map((id) => purgeSchedule(id)));
        const schedulesPayload = await fetchArchivedSchedules();
        setArchivedSchedules(schedulesPayload);
        setSelectedScheduleIds(new Set());
      } else if (kind === "mapping") {
        await Promise.all(ids.map((id) => purgeIntegrationMapping(id)));
        const mappingsPayload = await fetchArchivedIntegrationMappings();
        setArchivedMappings(mappingsPayload);
        setSelectedMappingIds(new Set());
      }
      const summaryPayload = await fetchArchiveSummary();
      setSummary(summaryPayload);
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
      setPurgeConfirm(null);
    }
  };

  // ── Purge trigger helpers ─────────────────────────────────────────────────

  const confirmPurgeRun = (ids: number[], label: string) =>
    setPurgeConfirm({ kind: "run", ids, label });
  const confirmPurgeProfile = (ids: number[], label: string) =>
    setPurgeConfirm({ kind: "profile", ids, label });
  const confirmPurgeSchedule = (ids: number[], label: string) =>
    setPurgeConfirm({ kind: "schedule", ids, label });
  const confirmPurgeMapping = (ids: number[], label: string) =>
    setPurgeConfirm({ kind: "mapping", ids, label });

  const runIds = filteredRuns.map((r) => r.id);
  const profileIds = filteredProfiles.map((p) => p.id);
  const scheduleIds = filteredSchedules.map((s) => s.id);
  const mappingIds = filteredMappings.map((m) => m.id);

  const activeDays = summary?.policy_days.active ?? 30;
  const archiveDays = summary?.policy_days.archive ?? 180;

  const now = new Date();
  const archiveCutoff = addDays(now, -activeDays);
  const purgeCutoff = addDays(now, -archiveDays);

  const chartData = useMemo(() => ({
    lifecycle: [
      { label: "Active", value: summary?.counts.active ?? 0, color: "var(--chart-success)" },
      { label: "Archive-ready", value: summary?.counts.archive_ready ?? 0, color: "var(--chart-warning)" },
      { label: "Purge-ready", value: summary?.counts.purge_ready ?? 0, color: "var(--chart-danger)" },
    ],
    queue: [
      { label: "Archive ready", value: retentionSummary?.queue.archive_ready ?? summary?.counts.archive_ready ?? 0, color: "var(--chart-warning)" },
      { label: "Purge ready", value: retentionSummary?.queue.purge_ready ?? summary?.counts.purge_ready ?? 0, color: "var(--chart-danger)" },
      { label: "Artifact-backed", value: retentionSummary?.queue.artifact_backed_runs ?? 0, color: "var(--chart-info)" },
    ],
  }), [summary, retentionSummary]);

  return (
    <div className="page-shell">
      {purgeConfirm ? (
        <PurgeConfirmModal
          state={purgeConfirm}
          onConfirm={executePurge}
          onCancel={() => setPurgeConfirm(null)}
        />
      ) : null}

      <section className="page-header">
        <div className="page-header__meta">
          <h1 className="page-title">Archives</h1>
          <LastUpdatedIndicator updatedAt={lastUpdatedAt} onRefresh={() => void loadArchives()} />
        </div>
        <p className="page-subtitle">
          Items deleted from their main pages land here. Restore them to bring them back, or delete
          permanently to remove them forever.
        </p>
      </section>

      {error ? <ErrorBanner message={error} onRetry={() => void loadArchives()} /> : null}

      {/* Policy at a glance */}
      <section className="grid four">
        <article className="panel stat">
          <span className="stat-label">Runs stay visible for</span>
          <strong className="stat-value">{activeDays} days</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            After this, runs are auto-archived here
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archived runs kept for</span>
          <strong className="stat-value">{archiveDays} days</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            After this, they are permanently deleted
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Runs waiting to archive</span>
          <strong className="stat-value">{summary?.counts.archive_ready ?? 0}</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            Active runs older than {activeDays} days
          </span>
        </article>
        <article className="panel stat">
          <span className="stat-label">Runs waiting to delete</span>
          <strong className="stat-value">{summary?.counts.purge_ready ?? 0}</strong>
          <span className="stat-description muted" style={{ fontSize: "12px" }}>
            Archived runs older than {archiveDays} days
          </span>
        </article>
      </section>

      {/* ── Lifecycle health ──────────────────────────────────────────────── */}
      <section className="panel">
        <h2 className="section-title">Policy Timeline</h2>
        <div style={{ display: "grid", gap: "12px", fontSize: "14px" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", backgroundColor: "var(--chart-success)", flexShrink: 0 }} />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Active</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created within the last {activeDays} days (after <strong>{formatDate(archiveCutoff)}</strong>). Fully visible on the Runs page.
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", backgroundColor: "var(--chart-warning)", flexShrink: 0 }} />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Archive-ready</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created between {activeDays}–{archiveDays} days ago (between <strong>{formatDate(purgeCutoff)}</strong> and <strong>{formatDate(archiveCutoff)}</strong>). Auto-archived hourly — hidden from Runs but restorable here.
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", backgroundColor: "var(--chart-danger)", flexShrink: 0 }} />
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Purge-ready</span>
            <span style={{ color: "var(--text-secondary)" }}>
              Runs created more than {archiveDays} days ago (before <strong>{formatDate(purgeCutoff)}</strong>). Auto-purged hourly — permanently deleted including all on-disk artifacts.
            </span>
          </div>
        </div>
      </section>

      <section className="chart-grid">
        <article className="panel">
          <DistributionDonut
            title="Lifecycle Distribution"
            data={chartData.lifecycle}
            emptyLabel="No run lifecycle data"
          />
        </article>
        <article className="panel">
          <HorizontalBarChart
            title="Queue Pressure"
            data={chartData.queue}
            emptyLabel="No retention pressure"
          />
        </article>
      </section>

      {/* ── Archived Runs ─────────────────────────────────────────────────── */}
      <section className="panel grid">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "16px",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>Archived Runs</h2>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>
              {runs.length} run{runs.length === 1 ? "" : "s"} archived — hidden from the Runs
              page but still accessible here.
            </p>
          </div>
          <input
            value={runQuery}
            onChange={(e) => setRunQuery(e.target.value)}
            placeholder="Search by id, flow, status, actor…"
            style={{ maxWidth: "320px" }}
          />
        </div>

        <BulkActionBar
          selectedCount={selectedRunIds.size}
          onPurge={() =>
            confirmPurgeRun(
              Array.from(selectedRunIds),
              `${selectedRunIds.size} archived run${selectedRunIds.size === 1 ? "" : "s"}`
            )
          }
          onClear={() => setSelectedRunIds(new Set())}
          busy={busy}
        />

        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}>
                  <input
                    type="checkbox"
                    checked={allSelected(runIds, selectedRunIds)}
                    onChange={() => toggleAll(runIds, selectedRunIds, setSelectedRunIds)}
                    aria-label="Select all runs"
                  />
                </th>
                <th>Run</th>
                <th>Status</th>
                <th>Actors</th>
                <th>Age</th>
                <th>Summary</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedRunIds.has(run.id)}
                      onChange={() => setSelectedRunIds(toggleId(selectedRunIds, run.id))}
                      aria-label={`Select run #${run.id}`}
                    />
                  </td>
                  <td>
                    <Link href={`/runs/${run.id}`}>Run #{run.id}</Link>
                    <div className="muted">{run.flow} / {run.timing}</div>
                  </td>
                  <td>
                    <span className={`status-pill ${statusClass(run.status)}`}>{run.status}</span>
                  </td>
                  <td>
                    <div>{run.store_id || "auto-store"}</div>
                    <div className="muted">{run.phone || "auto-user"}</div>
                  </td>
                  <td>
                    <div>{run.age_days ?? "--"} days old</div>
                    {run.lifecycle_state ? (
                      <LifecyclePill state={run.lifecycle_state} />
                    ) : null}
                  </td>
                  <td>
                    <div>{run.retained_summary?.narrative ?? "Summary pending"}</div>
                    <div className="muted">
                      Artifacts:{" "}
                      {run.retained_summary?.audit_attribution.artifact_available
                        ? "saved"
                        : "not captured"}
                    </div>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="secondary small"
                        disabled={busy}
                        onClick={() => restoreArchivedRun(run.id)}
                      >
                        Restore
                      </button>
                      <button
                        className="small"
                        disabled={busy}
                        onClick={() => confirmPurgeRun([run.id], `Run #${run.id}`)}
                        style={{
                          backgroundColor: "var(--method-delete-bg)",
                          color: "var(--method-delete-text)",
                          border: "1px solid var(--method-delete-border)",
                        }}
                      >
                        Delete permanently
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!filteredRuns.length ? (
                <tr>
                  <td colSpan={7} className="muted">
                    {runQuery ? "No archived runs match your search." : "No archived runs."}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Archived Profiles + Schedules ─────────────────────────────────── */}
      <section className="grid two">

        {/* Profiles */}
        <article className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", flexWrap: "wrap", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title" style={{ margin: 0 }}>Archived Profiles</h2>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>
                Run configuration presets that were deleted.
              </p>
            </div>
            <input
              value={profileQuery}
              onChange={(e) => setProfileQuery(e.target.value)}
              placeholder="Search name, flow…"
              style={{ maxWidth: "200px", fontSize: "13px" }}
            />
          </div>
          <BulkActionBar
            selectedCount={selectedProfileIds.size}
            onPurge={() =>
              confirmPurgeProfile(
                Array.from(selectedProfileIds),
                `${selectedProfileIds.size} profile${selectedProfileIds.size === 1 ? "" : "s"}`
              )
            }
            onClear={() => setSelectedProfileIds(new Set())}
            busy={busy}
          />
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={allSelected(profileIds, selectedProfileIds)}
                      onChange={() =>
                        toggleAll(profileIds, selectedProfileIds, setSelectedProfileIds)
                      }
                      aria-label="Select all profiles"
                    />
                  </th>
                  <th>Name</th>
                  <th>Flow</th>
                  <th>Archived on</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredProfiles.map((profile) => (
                  <tr key={profile.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedProfileIds.has(profile.id)}
                        onChange={() =>
                          setSelectedProfileIds(toggleId(selectedProfileIds, profile.id))
                        }
                        aria-label={`Select profile ${profile.name}`}
                      />
                    </td>
                    <td>{profile.name}</td>
                    <td>{profile.flow}</td>
                    <td>
                      <div className="muted" style={{ fontSize: "13px" }}>
                        {profile.archived_at ?? profile.updated_at ?? "—"}
                      </div>
                      <LifecyclePill state={archivedAtState(profile.archived_at, archiveDays)} />
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="secondary small"
                          disabled={busy}
                          onClick={() => restoreProfile(profile.id)}
                        >
                          Restore
                        </button>
                        <button
                          className="small"
                          disabled={busy}
                          onClick={() =>
                            confirmPurgeProfile([profile.id], `profile "${profile.name}"`)
                          }
                          style={{
                            backgroundColor: "var(--method-delete-bg)",
                            color: "var(--method-delete-text)",
                            border: "1px solid var(--method-delete-border)",
                          }}
                        >
                          Delete permanently
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredProfiles.length ? (
                  <tr>
                    <td colSpan={5} className="muted">
                      {profileQuery ? "No profiles match your search." : "No archived profiles."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        {/* Schedules */}
        <article className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", flexWrap: "wrap", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title" style={{ margin: 0 }}>Archived Schedules</h2>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>
                Deleted schedules that no longer trigger runs.
              </p>
            </div>
            <input
              value={scheduleQuery}
              onChange={(e) => setScheduleQuery(e.target.value)}
              placeholder="Search name, timezone…"
              style={{ maxWidth: "200px", fontSize: "13px" }}
            />
          </div>
          <BulkActionBar
            selectedCount={selectedScheduleIds.size}
            onPurge={() =>
              confirmPurgeSchedule(
                Array.from(selectedScheduleIds),
                `${selectedScheduleIds.size} schedule${selectedScheduleIds.size === 1 ? "" : "s"}`
              )
            }
            onClear={() => setSelectedScheduleIds(new Set())}
            busy={busy}
          />
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={allSelected(scheduleIds, selectedScheduleIds)}
                      onChange={() =>
                        toggleAll(scheduleIds, selectedScheduleIds, setSelectedScheduleIds)
                      }
                      aria-label="Select all schedules"
                    />
                  </th>
                  <th>Name</th>
                  <th>Timezone</th>
                  <th>Archived on</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSchedules.map((schedule) => (
                  <tr key={schedule.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedScheduleIds.has(schedule.id)}
                        onChange={() =>
                          setSelectedScheduleIds(toggleId(selectedScheduleIds, schedule.id))
                        }
                        aria-label={`Select schedule ${schedule.name}`}
                      />
                    </td>
                    <td>{schedule.name}</td>
                    <td>{schedule.timezone}</td>
                    <td>
                      <div className="muted" style={{ fontSize: "13px" }}>{schedule.updated_at}</div>
                      <LifecyclePill state={archivedAtState(schedule.updated_at, archiveDays)} />
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="secondary small"
                          disabled={busy}
                          onClick={() => restoreSchedule(schedule.id)}
                        >
                          Restore
                        </button>
                        <button
                          className="small"
                          disabled={busy}
                          onClick={() =>
                            confirmPurgeSchedule([schedule.id], `schedule "${schedule.name}"`)
                          }
                          style={{
                            backgroundColor: "var(--method-delete-bg)",
                            color: "var(--method-delete-text)",
                            border: "1px solid var(--method-delete-border)",
                          }}
                        >
                          Delete permanently
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredSchedules.length ? (
                  <tr>
                    <td colSpan={5} className="muted">
                      {scheduleQuery ? "No schedules match your search." : "No archived schedules."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      {/* ── Archived Integration Mappings ─────────────────────────────────── */}
      <section className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", flexWrap: "wrap", marginBottom: "8px" }}>
          <div>
            <h2 className="section-title" style={{ margin: 0 }}>Archived Integration Mappings</h2>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: "13px" }}>
              Deleted GitHub–profile connections. Restoring re-enables the integration trigger.
            </p>
          </div>
          <input
            value={mappingQuery}
            onChange={(e) => setMappingQuery(e.target.value)}
            placeholder="Search project, route, profile…"
            style={{ maxWidth: "280px" }}
          />
        </div>
        <BulkActionBar
          selectedCount={selectedMappingIds.size}
          onPurge={() =>
            confirmPurgeMapping(
              Array.from(selectedMappingIds),
              `${selectedMappingIds.size} mapping${selectedMappingIds.size === 1 ? "" : "s"}`
            )
          }
          onClear={() => setSelectedMappingIds(new Set())}
          busy={busy}
        />
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}>
                  <input
                    type="checkbox"
                    checked={allSelected(mappingIds, selectedMappingIds)}
                    onChange={() =>
                      toggleAll(mappingIds, selectedMappingIds, setSelectedMappingIds)
                    }
                    aria-label="Select all mappings"
                  />
                </th>
                <th>Project</th>
                <th>Route / Environment</th>
                <th>Linked profile</th>
                <th>Archived on</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredMappings.map((mapping) => (
                <tr key={mapping.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedMappingIds.has(mapping.id)}
                      onChange={() =>
                        setSelectedMappingIds(toggleId(selectedMappingIds, mapping.id))
                      }
                      aria-label={`Select mapping ${mapping.project}`}
                    />
                  </td>
                  <td>{mapping.project}</td>
                  <td>{mapping.environment}</td>
                  <td>{mapping.profile_name ?? `#${mapping.profile_id}`}</td>
                  <td>
                    <div className="muted" style={{ fontSize: "13px" }}>
                      {mapping.archived_at ?? mapping.updated_at ?? "—"}
                    </div>
                    <LifecyclePill state={archivedAtState(mapping.archived_at ?? mapping.updated_at, archiveDays)} />
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="secondary small"
                        disabled={busy}
                        onClick={() => restoreMapping(mapping.id)}
                      >
                        Restore
                      </button>
                      <button
                        className="small"
                        disabled={busy}
                        onClick={() =>
                          confirmPurgeMapping(
                            [mapping.id],
                            `mapping "${mapping.project}/${mapping.environment}"`
                          )
                        }
                        style={{
                          backgroundColor: "var(--method-delete-bg)",
                          color: "var(--method-delete-text)",
                          border: "1px solid var(--method-delete-border)",
                        }}
                      >
                        Delete permanently
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!filteredMappings.length ? (
                <tr>
                  <td colSpan={6} className="muted">
                    {mappingQuery
                      ? "No integration mappings match your search."
                      : "No archived integration mappings."}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
