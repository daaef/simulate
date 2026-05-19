"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ApiRequestError,
  fetchArchivedProfiles,
  fetchArchivedSchedules,
  fetchArchivedIntegrationMappings,
  fetchArchiveRuns,
  fetchArchiveSummary,
  restoreRun,
  restoreRunProfile,
  restoreGitHubIntegrationMapping,
  setScheduleStatus,
  type IntegrationMapping,
  type RunProfile,
  type Schedule,
  type ArchiveRun,
  type ArchiveSummary,
} from "../../../lib/api";

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

function lifecycleLabel(run: ArchiveRun): string {
  if (run.lifecycle_state === "archived") return "archived";
  if (run.lifecycle_state === "raw_purge_candidate") return "raw purge";
  if (run.lifecycle_state === "archive_candidate") return "archive";
  return "active";
}

export default function ArchivesPage() {
  const [summary, setSummary] = useState<ArchiveSummary | null>(null);
  const [runs, setRuns] = useState<ArchiveRun[]>([]);
  const [archivedProfiles, setArchivedProfiles] = useState<RunProfile[]>([]);
  const [archivedSchedules, setArchivedSchedules] = useState<Schedule[]>([]);
  const [archivedMappings, setArchivedMappings] = useState<IntegrationMapping[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [summaryPayload, runsPayload, profilesPayload, schedulesPayload, mappingsPayload] = await Promise.all([
          fetchArchiveSummary(),
          fetchArchiveRuns(100, 0),
          fetchArchivedProfiles(),
          fetchArchivedSchedules(),
          fetchArchivedIntegrationMappings(),
        ]);
        if (!active) return;
        setSummary(summaryPayload);
        setRuns(runsPayload.runs);
        setArchivedProfiles(profilesPayload);
        setArchivedSchedules(schedulesPayload);
        setArchivedMappings(mappingsPayload);
        setError(null);
      } catch (caughtError) {
        if (active) setError(toMessage(caughtError));
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return runs;
    return runs.filter((run) => {
      const haystack = [
        run.id,
        run.flow,
        run.status,
        run.store_id,
        run.phone,
        run.store_name,
        run.user_name,
        run.lifecycle_state,
        run.retained_summary?.narrative,
      ].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }, [query, runs]);

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
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Archives</h1>
        <p className="page-subtitle">Archive candidates, raw-purge candidates, and retained summaries.</p>
      </section>

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      <section className="grid four">
        <article className="panel stat">
          <span className="stat-label">Active Policy</span>
          <strong className="stat-value">{summary?.policy_days.active ?? "--"}d</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archive Policy</span>
          <strong className="stat-value">{summary?.policy_days.archive ?? "--"}d</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Archive Ready</span>
          <strong className="stat-value">{summary?.counts.archive_ready ?? 0}</strong>
        </article>
        <article className="panel stat">
          <span className="stat-label">Raw Purge Ready</span>
          <strong className="stat-value">{summary?.counts.purge_ready ?? 0}</strong>
        </article>
      </section>

      <section className="panel grid">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
          <h2 className="section-title" style={{ margin: 0 }}>Archived Runs</h2>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search id, flow, actor, status"
            style={{ maxWidth: "360px" }}
          />
        </div>
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Lifecycle</th>
                <th>Status</th>
                <th>Actors</th>
                <th>Age</th>
                <th>Retained Summary</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link href={`/runs/${run.id}`}>Run #{run.id}</Link>
                    <div className="muted">{run.flow} / {run.timing}</div>
                  </td>
                  <td>{lifecycleLabel(run)}</td>
                  <td><span className={`status-pill ${statusClass(run.status)}`}>{run.status}</span></td>
                  <td>
                    <div>{run.store_id || "auto-store"}</div>
                    <div className="muted">{run.phone || "auto-user"}</div>
                  </td>
                  <td>{run.age_days ?? "--"} days</td>
                  <td>
                    <div>{run.retained_summary?.narrative ?? "Summary pending"}</div>
                    <div className="muted">
                      Artifact: {run.retained_summary?.audit_attribution.artifact_available ? "available" : "not captured"}
                    </div>
                  </td>
                  <td>
                    <button className="secondary small" disabled={busy} onClick={() => restoreArchivedRun(run.id)}>
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
              {!filteredRuns.length ? (
                <tr><td colSpan={7} className="muted">No archived runs match the current search.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid two">
        <article className="panel">
          <h2 className="section-title">Archived Profiles</h2>
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Flow</th>
                  <th>Archived</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {archivedProfiles.map((profile) => (
                  <tr key={profile.id}>
                    <td>{profile.name}</td>
                    <td>{profile.flow}</td>
                    <td>{profile.archived_at ?? profile.updated_at}</td>
                    <td>
                      <button className="secondary small" disabled={busy} onClick={() => restoreProfile(profile.id)}>
                        Restore
                      </button>
                    </td>
                  </tr>
                ))}
                {!archivedProfiles.length ? (
                  <tr><td colSpan={4} className="muted">No archived profiles.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel">
          <h2 className="section-title">Archived Schedules</h2>
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Timezone</th>
                  <th>Archived</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {archivedSchedules.map((schedule) => (
                  <tr key={schedule.id}>
                    <td>{schedule.name}</td>
                    <td>{schedule.timezone}</td>
                    <td>{schedule.updated_at}</td>
                    <td>
                      <button className="secondary small" disabled={busy} onClick={() => restoreSchedule(schedule.id)}>
                        Restore
                      </button>
                    </td>
                  </tr>
                ))}
                {!archivedSchedules.length ? (
                  <tr><td colSpan={4} className="muted">No archived schedules.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="panel">
        <h2 className="section-title">Archived Integration Mappings</h2>
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Route Key</th>
                <th>Profile</th>
                <th>Archived</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {archivedMappings.map((mapping) => (
                <tr key={mapping.id}>
                  <td>{mapping.project}</td>
                  <td>{mapping.environment}</td>
                  <td>{mapping.profile_name ?? `#${mapping.profile_id}`}</td>
                  <td>{mapping.archived_at ?? mapping.updated_at ?? "—"}</td>
                  <td>
                    <button className="secondary small" disabled={busy} onClick={() => restoreMapping(mapping.id)}>
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
              {!archivedMappings.length ? (
                <tr><td colSpan={5} className="muted">No archived integration mappings.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
