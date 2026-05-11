"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiRequestError,
  deleteGitHubIntegrationMapping,
  fetchGitHubIntegrationMappings,
  fetchGitHubIntegrationTriggers,
  fetchRunProfiles,
  upsertGitHubIntegrationMapping,
  type GitHubIntegrationTrigger,
  type IntegrationMapping,
  type RunProfile,
} from "../../lib/api";

const PROJECT_OPTIONS = ["backend", "mobile", "store", "robot", "dashboard", "website"];
const ENVIRONMENT_OPTIONS = ["production", "staging", "development", "preview"];

function formatError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";

  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function normalizeStatus(value?: string | null): "success" | "warning" | "danger" | "info" {
  const lower = (value ?? "").toLowerCase();

  if (["accepted", "queued", "started", "launched", "success", "succeeded"].includes(lower)) return "success";
  if (["ignored", "skipped", "disabled", "pending"].includes(lower)) return "warning";
  if (["failed", "error", "rejected"].includes(lower) || lower.includes("invalid") || lower.includes("not_found")) {
    return "danger";
  }

  return "info";
}

function triggerLabel(trigger: GitHubIntegrationTrigger): string {
  return trigger.reason || trigger.status || "—";
}

function profileLabel(profile?: RunProfile): string {
  if (!profile) return "Unknown profile";
  return `${profile.name} · ${profile.flow}${profile.mode ? `/${profile.mode}` : ""}`;
}

function shortJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

export default function IntegrationMappingsPanel() {
  const [mappings, setMappings] = useState<IntegrationMapping[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [triggers, setTriggers] = useState<GitHubIntegrationTrigger[]>([]);

  const [project, setProject] = useState("backend");
  const [environment, setEnvironment] = useState("production");
  const [profileId, setProfileId] = useState("");
  const [enabled, setEnabled] = useState(true);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const profileById = useMemo(() => {
    const map = new Map<number, RunProfile>();
    for (const profile of profiles) map.set(profile.id, profile);
    return map;
  }, [profiles]);

  const enabledCount = mappings.filter((mapping) => mapping.enabled).length;
  const disabledCount = mappings.length - enabledCount;
  const acceptedTriggerCount = triggers.filter((trigger) => normalizeStatus(trigger.status) === "success").length;

  async function loadAll() {
    setLoading(true);
    setError(null);

    try {
      const [nextMappings, nextProfiles, triggerPayload] = await Promise.all([
        fetchGitHubIntegrationMappings(),
        fetchRunProfiles(),
        fetchGitHubIntegrationTriggers(25, 0),
      ]);

      setMappings(nextMappings);
      setProfiles(nextProfiles);
      setTriggers(triggerPayload.triggers);

      if (!profileId && nextProfiles[0]) {
        setProfileId(String(nextProfiles[0].id));
      }
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  function resetForm() {
    setEditingId(null);
    setProject("backend");
    setEnvironment("production");
    setProfileId(profiles[0] ? String(profiles[0].id) : "");
    setEnabled(true);
    setMessage(null);
    setError(null);
  }

  function editMapping(mapping: IntegrationMapping) {
    setEditingId(mapping.id);
    setProject(mapping.project);
    setEnvironment(mapping.environment);
    setProfileId(String(mapping.profile_id));
    setEnabled(mapping.enabled);
    setMessage(null);
    setError(null);
  }

  async function saveMapping() {
    const normalizedProject = project.trim();
    const normalizedEnvironment = environment.trim();
    const parsedProfileId = Number(profileId);

    if (!normalizedProject || !normalizedEnvironment || !Number.isInteger(parsedProfileId) || parsedProfileId < 1) {
      setError("Project, environment, and run profile are required.");
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);

    try {
      await upsertGitHubIntegrationMapping({
        project: normalizedProject,
        environment: normalizedEnvironment,
        profile_id: parsedProfileId,
        enabled,
      });

      setMessage(editingId ? "Mapping updated." : "Mapping saved.");
      setEditingId(null);

      const [nextMappings, triggerPayload] = await Promise.all([
        fetchGitHubIntegrationMappings(),
        fetchGitHubIntegrationTriggers(25, 0),
      ]);

      setMappings(nextMappings);
      setTriggers(triggerPayload.triggers);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function removeMapping(mappingId: number) {
    setBusy(true);
    setError(null);
    setMessage(null);

    try {
      await deleteGitHubIntegrationMapping(mappingId);
      setMessage("Mapping deleted.");

      if (editingId === mappingId) resetForm();

      const nextMappings = await fetchGitHubIntegrationMappings();
      setMappings(nextMappings);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel grid" style={{ gap: 18 }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div className="grid" style={{ gap: 6 }}>
          <div className="status-pill status-info">GitHub deployment automation</div>
          <h2 style={{ margin: 0, fontSize: 28 }}>Integration Mappings</h2>
          <p className="muted" style={{ margin: 0, lineHeight: 1.6, maxWidth: 780 }}>
            Route successful GitHub deployments to saved simulator run profiles. Secrets, repository allowlists,
            and webhook signing remain in the server environment file.
          </p>
        </div>

        <button type="button" className="secondary" style={{ width: "auto" }} onClick={() => void loadAll()}>
          Refresh
        </button>
      </div>

      <div className="grid three">
        <div className="panel" style={{ background: "var(--bg-tertiary)" }}>
          <div className="stat">
            <div className="stat-label">Total mappings</div>
            <div className="stat-value">{mappings.length}</div>
          </div>
        </div>
        <div className="panel" style={{ background: "var(--bg-tertiary)" }}>
          <div className="stat">
            <div className="stat-label">Enabled</div>
            <div className="stat-value">{enabledCount}</div>
          </div>
        </div>
        <div className="panel" style={{ background: "var(--bg-tertiary)" }}>
          <div className="stat">
            <div className="stat-label">Recent accepted triggers</div>
            <div className="stat-value">{acceptedTriggerCount}</div>
          </div>
        </div>
      </div>

      {error ? (
        <div className="error-banner" style={{ padding: "12px 14px" }}>
          {error}
        </div>
      ) : null}

      {message ? (
        <div
          className="status-pill status-success"
          style={{ borderRadius: 8, padding: "10px 12px", width: "fit-content" }}
        >
          {message}
        </div>
      ) : null}

      <div className="grid two" style={{ alignItems: "start", gap: 18 }}>
        <section className="panel grid" style={{ gap: 14, borderRadius: 12 }}>
          <div>
            <h3 className="section-title" style={{ marginBottom: 4 }}>
              {editingId ? "Edit deployment route" : "Create deployment route"}
            </h3>
            <p className="form-help">
              Match the GitHub webhook project and deployment environment, then choose the simulator profile to run.
            </p>
          </div>

          <div className="grid two">
            <label className="grid" style={{ gap: 6 }}>
              <span className="muted">Project</span>
              <input
                list="github-project-options"
                value={project}
                onChange={(event) => setProject(event.target.value)}
                placeholder="backend"
                disabled={busy}
              />
              <datalist id="github-project-options">
                {PROJECT_OPTIONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </label>

            <label className="grid" style={{ gap: 6 }}>
              <span className="muted">Environment</span>
              <input
                list="github-environment-options"
                value={environment}
                onChange={(event) => setEnvironment(event.target.value)}
                placeholder="production"
                disabled={busy}
              />
              <datalist id="github-environment-options">
                {ENVIRONMENT_OPTIONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </label>
          </div>

          <label className="grid" style={{ gap: 6 }}>
            <span className="muted">Run Profile</span>
            <select value={profileId} onChange={(event) => setProfileId(event.target.value)} disabled={busy}>
              <option value="">Select run profile</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profileLabel(profile)}
                </option>
              ))}
            </select>
          </label>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              border: "1px solid var(--border-primary)",
              borderRadius: 10,
              padding: 12,
              background: "var(--bg-tertiary)",
            }}
          >
            <span className="grid" style={{ gap: 4 }}>
              <strong>Enable automatic verification</strong>
              <span className="muted" style={{ fontSize: 13 }}>
                Disabled mappings remain saved but will not launch simulator runs.
              </span>
            </span>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
              disabled={busy}
            />
          </label>

          <div
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <button type="button" onClick={() => void saveMapping()} disabled={busy || loading} style={{ width: "auto" }}>
              {busy ? "Saving..." : editingId ? "Update Mapping" : "Save Mapping"}
            </button>

            <button type="button" className="secondary" onClick={resetForm} disabled={busy} style={{ width: "auto" }}>
              Reset
            </button>
          </div>
        </section>

        <section className="panel grid" style={{ gap: 14, borderRadius: 12 }}>
          <div>
            <h3 className="section-title" style={{ marginBottom: 4 }}>Active Routes</h3>
            <p className="form-help">Configured project/environment pairs and their target run profiles.</p>
          </div>

          {loading ? (
            <div className="chart-empty">Loading mappings...</div>
          ) : mappings.length ? (
            <div className="grid" style={{ gap: 10 }}>
              {mappings.map((mapping) => {
                const profile = profileById.get(mapping.profile_id);

                return (
                  <article key={mapping.id} className="list-row grid" style={{ gap: 10 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 12,
                        alignItems: "flex-start",
                      }}
                    >
                      <div className="grid" style={{ gap: 6 }}>
                        <strong style={{ fontSize: 16 }}>
                          {mapping.project} → {mapping.environment}
                        </strong>
                        <span className="muted">{profile?.name ?? mapping.profile_name ?? `Profile #${mapping.profile_id}`}</span>
                      </div>

                      <span className={`status-pill ${mapping.enabled ? "status-success" : "status-warning"}`}>
                        {mapping.enabled ? "enabled" : "disabled"}
                      </span>
                    </div>

                    <div className="pill-list">
                      <span className="chip">project: {mapping.project}</span>
                      <span className="chip">env: {mapping.environment}</span>
                      <span className="chip">profile: #{mapping.profile_id}</span>
                    </div>

                    <div className="row-actions">
                      <button type="button" className="secondary small" onClick={() => editMapping(mapping)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => void removeMapping(mapping.id)}
                        disabled={busy}
                      >
                        Delete
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="chart-empty">No integration mappings configured yet.</div>
          )}

          {disabledCount ? (
            <p className="form-help">{disabledCount} mapping{disabledCount === 1 ? "" : "s"} currently disabled.</p>
          ) : null}
        </section>
      </div>

      <section className="panel grid" style={{ gap: 14, borderRadius: 12 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div>
            <h3 className="section-title" style={{ marginBottom: 4 }}>Recent GitHub Triggers</h3>
            <p className="form-help">Audit trail for webhook delivery, matching, rejection reasons, and launched runs.</p>
          </div>
          <button type="button" className="secondary small" onClick={() => void loadAll()} disabled={busy || loading}>
            Refresh History
          </button>
        </div>

        {triggers.length ? (
          <div className="responsive-table">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Repository</th>
                  <th>Route</th>
                  <th>Status</th>
                  <th>Run</th>
                  <th>Meta</th>
                </tr>
              </thead>
              <tbody>
                {triggers.map((trigger) => {
                  const status = normalizeStatus(trigger.reason || trigger.status);

                  return (
                    <tr key={trigger.id}>
                      <td>{formatDate(trigger.created_at)}</td>
                      <td>{trigger.repository ?? "—"}</td>
                      <td>
                        <div className="grid" style={{ gap: 2 }}>
                          <strong>{trigger.project ?? "—"}</strong>
                          <span className="muted">{trigger.environment ?? "—"}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill status-${status}`}>{triggerLabel(trigger)}</span>
                      </td>
                      <td>
                        {trigger.run_id ? (
                          <a href={`/runs/${trigger.run_id}`}>Run #{trigger.run_id}</a>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <details>
                          <summary className="muted" style={{ cursor: "pointer" }}>View</summary>
                          <pre
                            style={{
                              marginTop: 8,
                              maxHeight: 180,
                              overflow: "auto",
                              background: "var(--bg-log)",
                              color: "var(--text-log)",
                              borderRadius: 8,
                              padding: 10,
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {shortJson(trigger.meta)}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="chart-empty">No GitHub deployment triggers recorded yet.</div>
        )}
      </section>
    </section>
  );
}