"use client";

import { useEffect, useMemo, useState } from "react";
import AdminSubNav from "../../../../components/AdminSubNav";
import {
  ApiRequestError,
  fetchSystemTimezones,
  updateSystemTimezones,
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
  const [policy, setPolicy] = useState<SystemTimezonesPolicy | null>(null);
  const [mode, setMode] = useState<TimezonePolicyMode>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

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

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Admin</h1>
        <p className="page-subtitle">System-level configuration and policy enforcement.</p>
      </section>

      <AdminSubNav />

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

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

