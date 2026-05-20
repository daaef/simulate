"use client";

import { useEffect, useState } from "react";
import {
  ApiRequestError,
  createIntegrationWebhookProject,
  deleteIntegrationWebhookProject,
  fetchIntegrationWebhookProjects,
  rotateIntegrationWebhookProjectSecret,
  updateIntegrationWebhookProjectRepositories,
  type IntegrationWebhookProject,
  type IntegrationWebhookProjectMutationResponse,
  type WebhookGithubSyncCommands,
} from "../../lib/api";

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

function parseRepositoriesInput(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function copyText(value: string): Promise<boolean> {
  if (!value) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

function applyMutationFeedback(
  payload: IntegrationWebhookProjectMutationResponse,
  setters: {
    setRevealedSecret: (v: string | null) => void;
    setRevealedProject: (v: string | null) => void;
    setMessage: (v: string | null) => void;
    setSyncStatus: (v: string | null) => void;
    setSyncError: (v: string | null) => void;
    setSyncCommands: (v: WebhookGithubSyncCommands | null) => void;
    setShowFallback: (v: boolean) => void;
  }
) {
  if (payload.project.secret) {
    setters.setRevealedSecret(payload.project.secret);
    setters.setRevealedProject(payload.project.project);
  }
  setters.setSyncStatus(payload.sync_status ?? null);
  setters.setSyncError(payload.sync_error ?? null);
  setters.setSyncCommands(payload.sync_commands ?? null);
  setters.setShowFallback(payload.sync_status !== "ok");
  if (payload.sync_message) {
    setters.setMessage(payload.sync_message);
  } else if (payload.sync_status === "ok") {
    setters.setMessage("Synced to GitHub. Webhooks use the local config file immediately.");
  } else if (payload.sync_status === "skipped") {
    setters.setMessage("Saved locally. Configure SIMULATOR_GITHUB_CONFIG_TOKEN on the server for automatic GitHub sync.");
  }
}

export default function IntegrationWebhookProjectsPanel() {
  const [projects, setProjects] = useState<IntegrationWebhookProject[]>([]);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [projectName, setProjectName] = useState("");
  const [repositoriesInput, setRepositoriesInput] = useState("");
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);
  const [revealedProject, setRevealedProject] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncCommands, setSyncCommands] = useState<WebhookGithubSyncCommands | null>(null);
  const [showFallback, setShowFallback] = useState(false);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutationSetters = {
    setRevealedSecret,
    setRevealedProject,
    setMessage,
    setSyncStatus,
    setSyncError,
    setSyncCommands,
    setShowFallback,
  };

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchIntegrationWebhookProjects();
      setProjects(payload.projects ?? []);
      setWebhookUrl(payload.webhook_url ?? "");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  async function handleGenerate() {
    const normalizedProject = projectName.trim().toLowerCase();
    if (!normalizedProject) {
      setError("Project name is required.");
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);
    setCopyMessage(null);
    setSyncStatus(null);
    setSyncError(null);

    try {
      const payload = await createIntegrationWebhookProject({
        project: normalizedProject,
        repositories: parseRepositoriesInput(repositoriesInput),
      });
      applyMutationFeedback(payload, mutationSetters);
      if (payload.project.secret) {
        setMessage(
          (payload.sync_message ?? "") +
            (payload.project.secret
              ? ` Copy the signing secret now — it will not be shown again. Paste it into the upstream repo webhook secret.`
              : "")
        );
      }
      setProjectName("");
      setRepositoriesInput("");
      await loadProjects();
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleCopySecret() {
    if (!revealedSecret) return;
    const copied = await copyText(revealedSecret);
    setCopyMessage(copied ? "Secret copied to clipboard." : "Could not copy automatically. Select and copy manually.");
  }

  async function handleCopyWebhookUrl() {
    if (!webhookUrl) return;
    const copied = await copyText(webhookUrl);
    setCopyMessage(copied ? "Webhook URL copied." : "Could not copy webhook URL.");
  }

  async function handleCopyCommand(command: string, label: string) {
    const copied = await copyText(command);
    setCopyMessage(copied ? `${label} command copied.` : `Could not copy ${label} command.`);
  }

  async function handleRotate(project: string) {
    if (!window.confirm(`Rotate webhook secret for "${project}"? Update the upstream GitHub webhook afterward.`)) {
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);
    setCopyMessage(null);

    try {
      const payload = await rotateIntegrationWebhookProjectSecret(project);
      applyMutationFeedback(payload, mutationSetters);
      setMessage(
        `New secret for "${payload.project.project}". Copy it now and update the upstream webhook.` +
          (payload.sync_message ? ` ${payload.sync_message}` : "")
      );
      await loadProjects();
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(project: string) {
    if (
      !window.confirm(
        `Delete webhook project "${project}"? This removes it from the config file and re-syncs GitHub maps.`
      )
    ) {
      return;
    }

    setBusy(true);
    setError(null);
    setMessage(null);

    try {
      const payload = await deleteIntegrationWebhookProject(project);
      applyMutationFeedback(payload, mutationSetters);
      if (revealedProject === project) {
        setRevealedSecret(null);
        setRevealedProject(null);
      }
      setMessage(`Deleted project "${project}".`);
      await loadProjects();
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
          <div className="status-pill status-info">GitHub webhook projects</div>
          <h2 style={{ margin: 0, fontSize: 28 }}>Webhook Projects</h2>
          <p className="muted" style={{ margin: 0, lineHeight: 1.6, maxWidth: 780 }}>
            Manage signing secrets and repository allowlists in a persistent config file. Changes auto-sync to{" "}
            <code>SIMULATOR_WEBHOOK_PROJECT_SECRETS</code> and <code>SIMULATOR_WEBHOOK_REPO_ALLOWLIST</code> on this
            simulator repo when <code>SIMULATOR_GITHUB_CONFIG_TOKEN</code> is configured. Webhooks verify against the
            file immediately; deploy refreshes host <code>.env</code> from GitHub.
          </p>
        </div>

        <button type="button" className="secondary" style={{ width: "auto" }} onClick={() => void loadProjects()}>
          Refresh
        </button>
      </div>

      {webhookUrl ? (
        <div className="panel" style={{ background: "var(--bg-tertiary)", gap: 8 }}>
          <div className="muted" style={{ fontSize: 13 }}>
            Webhook endpoint URL
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <code style={{ wordBreak: "break-all" }}>{webhookUrl}</code>
            <button type="button" className="secondary" style={{ width: "auto" }} onClick={() => void handleCopyWebhookUrl()}>
              Copy URL
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="error-banner" style={{ padding: "12px 14px" }}>
          {error}
        </div>
      ) : null}

      {message ? (
        <div className="status-pill status-success" style={{ padding: "12px 14px", whiteSpace: "pre-wrap" }}>
          {message}
        </div>
      ) : null}

      {syncStatus === "failed" && syncError ? (
        <div className="error-banner" style={{ padding: "12px 14px" }}>
          GitHub sync failed: {syncError}
        </div>
      ) : null}

      {copyMessage ? <div className="muted">{copyMessage}</div> : null}

      {revealedSecret ? (
        <div className="panel" style={{ background: "var(--bg-tertiary)", gap: 10 }}>
          <div className="muted" style={{ fontSize: 13 }}>
            Signing secret for <strong>{revealedProject}</strong> (shown once)
          </div>
          <code
            style={{
              display: "block",
              padding: "12px 14px",
              borderRadius: 8,
              background: "var(--bg-primary)",
              wordBreak: "break-all",
            }}
          >
            {revealedSecret}
          </code>
          <button type="button" style={{ width: "auto" }} onClick={() => void handleCopySecret()}>
            Copy secret
          </button>
        </div>
      ) : null}

      {showFallback && syncCommands ? (
        <details className="panel" style={{ background: "var(--bg-tertiary)" }} open>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Manual GitHub sync (fallback)</summary>
          <p className="muted" style={{ margin: "10px 0", fontSize: 13 }}>
            Run on a machine with <code>gh auth login</code> if auto-sync is unavailable.
          </p>
          <div className="grid" style={{ gap: 10 }}>
            <div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
                Secrets map
              </div>
              <code style={{ display: "block", wordBreak: "break-all", fontSize: 12 }}>{syncCommands.secret}</code>
              <button
                type="button"
                className="secondary"
                style={{ width: "auto", marginTop: 8 }}
                onClick={() => void handleCopyCommand(syncCommands.secret, "Secret")}
              >
                Copy command
              </button>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
                Repository allowlist
              </div>
              <code style={{ display: "block", wordBreak: "break-all", fontSize: 12 }}>{syncCommands.allowlist}</code>
              <button
                type="button"
                className="secondary"
                style={{ width: "auto", marginTop: 8 }}
                onClick={() => void handleCopyCommand(syncCommands.allowlist, "Allowlist")}
              >
                Copy command
              </button>
            </div>
          </div>
        </details>
      ) : null}

      <div className="panel grid" style={{ gap: 14 }}>
        <h3 style={{ margin: 0 }}>Add project</h3>
        <p className="form-help" style={{ margin: 0 }}>
          Example project name: <code>dashboard</code>. Repositories: one <code>owner/repo</code> per line.
        </p>

        <label className="grid" style={{ gap: 6 }}>
          <span className="muted">Project key</span>
          <input
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
            placeholder="dashboard"
            autoComplete="off"
          />
        </label>

        <label className="grid" style={{ gap: 6 }}>
          <span className="muted">Allowed repositories</span>
          <textarea
            value={repositoriesInput}
            onChange={(event) => setRepositoriesInput(event.target.value)}
            placeholder={"Fainzy-Technologies/my-app\norg/another-repo"}
            rows={4}
          />
        </label>

        <button type="button" disabled={busy} onClick={() => void handleGenerate()}>
          {busy ? "Saving…" : "Generate webhook secret"}
        </button>
      </div>

      <div className="panel grid" style={{ gap: 12 }}>
        <h3 style={{ margin: 0 }}>Saved projects</h3>
        {loading ? <p className="muted">Loading…</p> : null}
        {!loading && projects.length === 0 ? (
          <p className="muted">No webhook projects yet. Generate one above.</p>
        ) : null}

        {projects.map((item) => (
          <div
            key={item.project}
            className="panel"
            style={{
              background: "var(--bg-tertiary)",
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div>
                <strong>{item.project}</strong>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  Secret hint: <code>{item.secret_hint}</code> · Updated {formatDate(item.updated_at)}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="secondary"
                  style={{ width: "auto" }}
                  disabled={busy}
                  onClick={() => void handleRotate(item.project)}
                >
                  Rotate secret
                </button>
                <button
                  type="button"
                  className="secondary"
                  style={{ width: "auto" }}
                  disabled={busy}
                  onClick={() => void handleDelete(item.project)}
                >
                  Delete
                </button>
              </div>
            </div>

            {item.repositories?.length ? (
              <div className="muted" style={{ fontSize: 13 }}>
                Repositories:{" "}
                {item.repositories.map((repo) => (
                  <code key={repo} style={{ marginRight: 8 }}>
                    {repo}
                  </code>
                ))}
              </div>
            ) : (
              <div className="muted" style={{ fontSize: 13 }}>
                No repositories configured for this project yet.
              </div>
            )}

            <RepositoryEditor
              project={item.project}
              initial={item.repositories ?? []}
              disabled={busy}
              onSaved={(payload) => {
                applyMutationFeedback(payload, mutationSetters);
                void loadProjects();
              }}
              onError={setError}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function RepositoryEditor({
  project,
  initial,
  disabled,
  onSaved,
  onError,
}: {
  project: string;
  initial: string[];
  disabled: boolean;
  onSaved: (payload: IntegrationWebhookProjectMutationResponse) => void;
  onError: (value: string) => void;
}) {
  const [value, setValue] = useState(initial.join("\n"));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValue(initial.join("\n"));
  }, [initial]);

  async function save() {
    setSaving(true);
    onError("");
    try {
      const payload = await updateIntegrationWebhookProjectRepositories(project, parseRepositoriesInput(value));
      onSaved(payload);
    } catch (caught) {
      onError(formatError(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <label className="grid" style={{ gap: 6 }}>
      <span className="muted" style={{ fontSize: 13 }}>
        Edit repositories
      </span>
      <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={3} disabled={disabled || saving} />
      <button type="button" className="secondary" style={{ width: "auto" }} disabled={disabled || saving} onClick={() => void save()}>
        {saving ? "Saving…" : "Save repositories"}
      </button>
    </label>
  );
}
