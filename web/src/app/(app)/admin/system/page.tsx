"use client";

import { useEffect, useMemo, useState } from "react";
import AdminSubNav from "../../../../components/AdminSubNav";
import {
  ApiRequestError,
  fetchRetentionPolicy,
  fetchSystemTimezones,
  updateRetentionPolicy,
  updateSystemTimezones,
  type RetentionPolicySettings,
  type SystemTimezonesPolicy,
  type TimezonePolicyMode,
} from "../../../../lib/api";

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

function groupLabel(value: string): string {
  const [prefix] = value.split("/", 1);
  return prefix || "Other";
}

export default function AdminSystemPage() {
  // Timezone policy
  const [policy, setPolicy] = useState<SystemTimezonesPolicy | null>(null);
  const [mode, setMode] = useState<TimezonePolicyMode>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Retention policy
  const [retentionPolicy, setRetentionPolicy] = useState<RetentionPolicySettings | null>(null);
  const [activeDays, setActiveDays] = useState<string>("30");
  const [archiveDays, setArchiveDays] = useState<string>("180");
  const [retentionBusy, setRetentionBusy] = useState(false);
  const [retentionError, setRetentionError] = useState<string | null>(null);
  const [retentionSavedAt, setRetentionSavedAt] = useState<number | null>(null);

  const available = policy?.available_timezones ?? [];

  useEffect(() => {
    let active = true;
    void fetchSystemTimezones()
      .then((payload) => {
        if (!active) return;
        setPolicy(payload);
        setMode(payload.mode);
        setSelected(new Set(payload.allowed_timezones ?? []));
      })
      .catch((caught) => {
        if (!active) return;
        setError(toMessage(caught, "Failed to load system settings"));
      });
    void fetchRetentionPolicy()
      .then((payload) => {
        if (!active) return;
        setRetentionPolicy(payload);
        setActiveDays(String(payload.active_days));
        setArchiveDays(String(payload.archive_days));
      })
      .catch(() => {
        // non-fatal — retention section will show inline error on save
      });
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return available;
    return available.filter((tz) => tz.toLowerCase().includes(q));
  }, [available, filter]);

  const grouped = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const tz of filtered) {
      const label = groupLabel(tz);
      const bucket = groups.get(label) ?? [];
      bucket.push(tz);
      groups.set(label, bucket);
    }
    return Array.from(groups.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const dirty = useMemo(() => {
    if (!policy) return false;
    if (mode !== policy.mode) return true;
    const current = new Set(policy.allowed_timezones ?? []);
    if (current.size !== selected.size) return true;
    for (const item of selected) if (!current.has(item)) return true;
    return false;
  }, [mode, policy, selected]);

  const toggleSelected = (tz: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(tz)) next.delete(tz);
      else next.add(tz);
      return next;
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      const payload =
        mode === "all"
          ? await updateSystemTimezones({ mode: "all" })
          : await updateSystemTimezones({ mode: "allowlist", allowed_timezones: Array.from(selected).sort() });
      setPolicy(payload);
      setMode(payload.mode);
      setSelected(new Set(payload.allowed_timezones ?? []));
      setSavedAt(Date.now());
      setError(null);
    } catch (caught) {
      setError(toMessage(caught, "Failed to save system settings"));
    } finally {
      setBusy(false);
    }
  };

  const retentionActiveParsed = parseInt(activeDays, 10);
  const retentionArchiveParsed = parseInt(archiveDays, 10);
  const retentionValidationError =
    isNaN(retentionActiveParsed) || retentionActiveParsed < 1
      ? "Active days must be a number ≥ 1."
      : isNaN(retentionArchiveParsed) || retentionArchiveParsed < 1
      ? "Archive days must be a number ≥ 1."
      : retentionArchiveParsed < retentionActiveParsed
      ? "Archive days must be greater than or equal to active days."
      : null;

  const retentionDirty =
    retentionPolicy !== null &&
    (retentionActiveParsed !== retentionPolicy.active_days ||
      retentionArchiveParsed !== retentionPolicy.archive_days);

  const saveRetention = async () => {
    if (retentionValidationError) return;
    setRetentionBusy(true);
    try {
      const payload = await updateRetentionPolicy({
        active_days: retentionActiveParsed,
        archive_days: retentionArchiveParsed,
      });
      setRetentionPolicy(payload);
      setActiveDays(String(payload.active_days));
      setArchiveDays(String(payload.archive_days));
      setRetentionSavedAt(Date.now());
      setRetentionError(null);
    } catch (caught) {
      setRetentionError(toMessage(caught, "Failed to save retention policy"));
    } finally {
      setRetentionBusy(false);
    }
  };

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Admin</h1>
        <p className="page-subtitle">System-level configuration and policy enforcement.</p>
      </section>

      <AdminSubNav />

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      {/* ── Retention Policy ──────────────────────────────────────────── */}
      <section className="panel grid" style={{ gap: 16 }}>
        <div className="grid" style={{ gap: 8 }}>
          <h2 className="section-title">Retention Policy</h2>
          <p className="muted" style={{ margin: 0, fontSize: "13px" }}>
            Controls how long run records stay visible before being auto-archived, and how long
            archived records are kept before being permanently deleted.
          </p>
        </div>

        {retentionError ? (
          <div className="error-banner" style={{ padding: "8px 12px", fontSize: "13px" }}>
            {retentionError}
          </div>
        ) : null}

        <div className="grid two" style={{ gap: 16 }}>
          <label className="grid" style={{ gap: 6 }}>
            <span style={{ fontWeight: 500, fontSize: "14px" }}>Active window (days)</span>
            <span className="muted" style={{ fontSize: "12px" }}>
              Runs stay on the Runs page for this many days. After this they are auto-archived.
              Default: {retentionPolicy?.active_days_default ?? 30}.
            </span>
            <input
              type="number"
              min={1}
              max={3650}
              value={activeDays}
              onChange={(e) => setActiveDays(e.target.value)}
              style={{ width: "120px" }}
            />
          </label>
          <label className="grid" style={{ gap: 6 }}>
            <span style={{ fontWeight: 500, fontSize: "14px" }}>Archive window (days)</span>
            <span className="muted" style={{ fontSize: "12px" }}>
              Archived runs are kept for this many days before being permanently deleted.
              Default: {retentionPolicy?.archive_days_default ?? 180}.
            </span>
            <input
              type="number"
              min={1}
              max={3650}
              value={archiveDays}
              onChange={(e) => setArchiveDays(e.target.value)}
              style={{ width: "120px" }}
            />
          </label>
        </div>

        {retentionValidationError ? (
          <div className="muted" style={{ color: "var(--color-danger, #e53e3e)", fontSize: "13px" }}>
            {retentionValidationError}
          </div>
        ) : null}

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            className="secondary"
            disabled={retentionBusy || !retentionDirty || !!retentionValidationError}
            onClick={saveRetention}
          >
            Save
          </button>
          {retentionSavedAt ? (
            <span className="muted" style={{ fontSize: "12px" }}>Saved</span>
          ) : null}
        </div>
      </section>

      {/* ── Timezone Policy ───────────────────────────────────────────── */}
      <section className="panel grid" style={{ gap: 16 }}>
        <div className="grid" style={{ gap: 8 }}>
          <h2 className="section-title">Timezone Policy</h2>
          <div className="grid two" style={{ alignItems: "end" }}>
            <div className="grid" style={{ gap: 8 }}>
              <div className="muted">Scheduling timezones</div>
              <div className="inline-choice">
                <label className="choice">
                  <input
                    type="radio"
                    name="tz-mode"
                    value="all"
                    checked={mode === "all"}
                    onChange={() => setMode("all")}
                  />
                  <span>Allow all</span>
                </label>
                <label className="choice">
                  <input
                    type="radio"
                    name="tz-mode"
                    value="allowlist"
                    checked={mode === "allowlist"}
                    onChange={() => setMode("allowlist")}
                  />
                  <span>Allowlist</span>
                </label>
              </div>
              <div className="muted">
                {mode === "all"
                  ? "All valid IANA timezones are available in schedules."
                  : `${selected.size} timezone${selected.size === 1 ? "" : "s"} allowed.`}
              </div>
            </div>
            <div className="grid" style={{ justifyItems: "end", gap: 6 }}>
              <button className="secondary" disabled={busy || !dirty || !policy} onClick={save}>
                Save
              </button>
              {savedAt ? <div className="muted" style={{ fontSize: 12 }}>Saved</div> : null}
            </div>
          </div>
        </div>

        {mode === "allowlist" ? (
          <div className="grid" style={{ gap: 12 }}>
            <label className="grid">
              <span className="muted">Search</span>
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter timezones (e.g. Africa/, New_York)" />
            </label>
            <div className="timezone-checklist">
              {grouped.map(([label, items]) => (
                <div key={label} className="timezone-group">
                  <div className="timezone-group-label">{label}</div>
                  <div className="timezone-group-items">
                    {items.map((tz) => (
                      <label key={tz} className="timezone-item">
                        <input
                          type="checkbox"
                          checked={selected.has(tz)}
                          onChange={() => toggleSelected(tz)}
                        />
                        <span>{tz}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              {!grouped.length ? <div className="chart-empty">No matching timezones.</div> : null}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

