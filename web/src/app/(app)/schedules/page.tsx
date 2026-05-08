"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiRequestError,
  createSchedule,
  fetchRunProfiles,
  fetchScheduleSummary,
  fetchSchedules,
  fetchSystemTimezones,
  setScheduleStatus,
  triggerSchedule,
  type CampaignStep,
  type RunProfile,
  type Schedule,
  type SchedulePeriod,
  type ScheduleStopRule,
  type ScheduleSummary,
  type ScheduleType,
  type SystemTimezonesPolicy,
} from "../../../lib/api";
import { formatDateTime, formatTimeUntil, parseTimestamp } from "../../../lib/time-format";

const periodOptions: SchedulePeriod[] = ["hourly", "daily", "weekly", "monthly"];

function defaultScheduleTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

function statusClass(status: string): string {
  if (status === "active") return "status-success";
  if (status === "paused" || status === "disabled") return "status-warning";
  if (status === "deleted") return "status-danger";
  return "status-info";
}

function nextTriggerLabel(schedule: Schedule): string {
  if (schedule.next_run_at) return formatDateTime(schedule.next_run_at, { timeZone: schedule.timezone || "UTC" });
  if (schedule.status === "active" && schedule.execution_mode_label === "manual_only") return "Manual only";
  if (schedule.status === "paused") return "Paused";
  if (schedule.status === "disabled") return "Disabled";
  if (schedule.status === "deleted") return "Deleted";
  return "Not scheduled";
}

function nextTriggerMeta(schedule: Schedule): string {
  if (schedule.next_run_at) return `${formatTimeUntil(schedule.next_run_at)} - ${schedule.timezone || "UTC"}`;
  if (schedule.next_run_reason === "outside_active_range") return "No future run: outside active range.";
  if (schedule.next_run_reason === "outside_stop_range") return "No future run: outside stop range.";
  if (schedule.next_run_reason === "window_clipped") return "Next run clipped by run window constraints.";
  if (schedule.next_run_reason === "blackout_skipped") return "Next run skipped one or more blackout dates.";
  if (schedule.next_run_reason === "shifted_to_window_start") return "Next run shifted to window start.";
  if (schedule.status === "active" && schedule.execution_mode_label === "manual_only") return "Manual-only schedule.";
  if (schedule.status === "paused") return "Resume to recalculate the next trigger.";
  if (schedule.status === "disabled") return "Disabled schedules do not run automatically.";
  if (schedule.status === "deleted") return "Restore before automatic triggers run.";
  return "No automatic trigger available.";
}

function toScheduleDateTime(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString();
}

function formatActiveRange(schedule: Schedule): string {
  if (!schedule.active_from && !schedule.active_until) return "No active date range";
  const start = schedule.active_from
    ? formatDateTime(schedule.active_from, { timeZone: schedule.timezone || "UTC" })
    : "Immediate";
  const end = schedule.active_until
    ? formatDateTime(schedule.active_until, { timeZone: schedule.timezone || "UTC" })
    : "No end date";
  return `${start} to ${end}`;
}

export default function SchedulesPage() {
  const SCHEDULES_REFRESH_MS = 15000;
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [summary, setSummary] = useState<ScheduleSummary | null>(null);
  const [timezonePolicy, setTimezonePolicy] = useState<SystemTimezonesPolicy | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scheduleType, setScheduleType] = useState<ScheduleType>("simple");
  const [profileId, setProfileId] = useState("");
  const [period, setPeriod] = useState<SchedulePeriod>("daily");
  const [anchorStartAt, setAnchorStartAt] = useState("");
  const [stopRule, setStopRule] = useState<ScheduleStopRule>("never");
  const [endAt, setEndAt] = useState("");
  const [durationHours, setDurationHours] = useState(5);
  const [runsPerPeriod, setRunsPerPeriod] = useState(1);
  const [timezone, setTimezone] = useState(defaultScheduleTimezone);
  const [runWindowStart, setRunWindowStart] = useState("");
  const [runWindowEnd, setRunWindowEnd] = useState("");
  const [blackoutDates, setBlackoutDates] = useState<string[]>([]);
  const [blackoutDateInput, setBlackoutDateInput] = useState("");
  const [campaignSteps, setCampaignSteps] = useState<CampaignStep[]>([]);
  const [stepProfileId, setStepProfileId] = useState("");
  const [stepRepeatCount, setStepRepeatCount] = useState(1);
  const [stepSpacingSeconds, setStepSpacingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loadInFlightRef = useRef(false);

  const profileById = useMemo(() => new Map(profiles.map((profile) => [profile.id, profile])), [profiles]);
  const nextAutomaticSchedule = useMemo(() => {
    return schedules
      .filter((schedule) => parseTimestamp(schedule.next_run_at) != null)
      .sort((left, right) => {
        const leftTime = parseTimestamp(left.next_run_at) ?? Number.POSITIVE_INFINITY;
        const rightTime = parseTimestamp(right.next_run_at) ?? Number.POSITIVE_INFINITY;
        return leftTime - rightTime;
      })[0] ?? null;
  }, [schedules]);

  const timezoneOptions = useMemo(() => {
    if (!timezonePolicy) return ["UTC"];
    if (timezonePolicy.mode === "allowlist") {
      const allowed = timezonePolicy.allowed_timezones ?? [];
      return allowed.length ? allowed : ["UTC"];
    }
    return timezonePolicy.available_timezones.length ? timezonePolicy.available_timezones : ["UTC"];
  }, [timezonePolicy]);

  const schedulePreview = useMemo(() => {
    const mode = anchorStartAt ? "automatic" : "manual_only";
    if (mode === "manual_only") {
      return { mode, nextRunAt: null as string | null, reason: "Set Start At to enable automatic scheduling." };
    }
    const now = new Date();
    const anchor = new Date(anchorStartAt);
    let next = anchor;
    if (Number.isNaN(anchor.getTime())) {
      return { mode: "manual_only", nextRunAt: null as string | null, reason: "Set a valid Start At date and time." };
    }
    while (next.getTime() <= now.getTime()) {
      if (period === "hourly") {
        next = new Date(next.getTime() + 60 * 60 * 1000);
      } else if (period === "daily") {
        next = new Date(next.getTime() + 24 * 60 * 60 * 1000);
      } else if (period === "weekly") {
        next = new Date(next.getTime() + 7 * 24 * 60 * 60 * 1000);
      } else {
        next = new Date(next);
        next.setMonth(next.getMonth() + 1);
      }
    }
    return {
      mode,
      nextRunAt: next.toISOString(),
      reason: "Preview uses start, period, stop rule, window, and blackout constraints on submit.",
    };
  }, [period, anchorStartAt]);

  const load = async (options?: { silent?: boolean }) => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    try {
      const [profilePayload, schedulePayload, summaryPayload, timezonePayload] = await Promise.all([
        fetchRunProfiles(),
        fetchSchedules(true),
        fetchScheduleSummary(),
        fetchSystemTimezones(),
      ]);
      setProfiles(profilePayload);
      setSchedules(schedulePayload);
      setSummary(summaryPayload);
      setTimezonePolicy(timezonePayload);
      if (!profileId && profilePayload[0]) setProfileId(String(profilePayload[0].id));
      if (!stepProfileId && profilePayload[0]) setStepProfileId(String(profilePayload[0].id));
      if (timezonePayload) {
        const local = defaultScheduleTimezone();
        const options =
          timezonePayload.mode === "allowlist"
            ? (timezonePayload.allowed_timezones ?? [])
            : timezonePayload.available_timezones;
        const next = options.includes(local) ? local : (options[0] ?? "UTC");
        setTimezone(next);
      }
      if (!options?.silent) {
        setError(null);
      }
    } finally {
      loadInFlightRef.current = false;
    }
  };

  useEffect(() => {
    let active = true;
    void load().catch((caughtError) => {
      if (active) setError(toMessage(caughtError, "Failed to load schedules"));
    });
    const refresh = () => {
      if (!active) return;
      void load({ silent: true }).catch((caughtError) => {
        if (active) setError(toMessage(caughtError, "Failed to refresh schedules"));
      });
    };
    const intervalId = window.setInterval(refresh, SCHEDULES_REFRESH_MS);
    const onFocus = () => refresh();
    const onVisibility = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const addCampaignStep = () => {
    const parsedProfileId = Number(stepProfileId);
    if (!parsedProfileId) {
      setError("Choose a profile before adding a campaign step.");
      return;
    }
    setCampaignSteps((current) => [
      ...current,
      {
        profile_id: parsedProfileId,
        repeat_count: Math.max(1, stepRepeatCount),
        spacing_seconds: Math.max(0, stepSpacingSeconds),
        timeout_seconds: 900,
        failure_policy: "continue",
        execution_mode: "saved_profile",
      },
    ]);
    setError(null);
  };

  const addBlackoutDate = () => {
    if (!blackoutDateInput) return;
    setBlackoutDates((current) => Array.from(new Set([...current, blackoutDateInput])).sort());
    setBlackoutDateInput("");
    setError(null);
  };

  const removeBlackoutDate = (date: string) => {
    setBlackoutDates((current) => current.filter((item) => item !== date));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    try {
      const anchorMs = anchorStartAt ? new Date(anchorStartAt).getTime() : null;
      if (anchorMs == null || Number.isNaN(anchorMs)) {
        setError("Choose a valid start date and time.");
        return;
      }
      if (stopRule === "end_at") {
        const endMs = endAt ? new Date(endAt).getTime() : null;
        if (endMs == null || Number.isNaN(endMs)) {
          setError("Choose a valid end date and time.");
          return;
        }
        if (endMs <= anchorMs) {
          setError("End time must be after Start time.");
          return;
        }
      }
      if (stopRule === "duration" && durationHours <= 0) {
        setError("Duration must be greater than 0.");
        return;
      }

      const parsedProfileId = Number(profileId);
      await createSchedule({
        name,
        description,
        schedule_type: scheduleType,
        profile_id: scheduleType === "simple" && parsedProfileId ? parsedProfileId : undefined,
        anchor_start_at: toScheduleDateTime(anchorStartAt),
        period,
        stop_rule: stopRule,
        end_at: stopRule === "end_at" ? toScheduleDateTime(endAt) : undefined,
        duration_seconds: stopRule === "duration" ? Math.max(1, Math.round(durationHours * 3600)) : undefined,
        runs_per_period: Math.max(1, runsPerPeriod),
        cadence: period,
        timezone,
        active_from: undefined,
        active_until: undefined,
        run_window_start: runWindowStart || undefined,
        run_window_end: runWindowEnd || undefined,
        blackout_dates: blackoutDates,
        failure_policy: "continue",
        campaign_steps: scheduleType === "campaign" ? campaignSteps : [],
      });
      setName("");
      setDescription("");
      setAnchorStartAt("");
      setEndAt("");
      setRunsPerPeriod(1);
      setBlackoutDates([]);
      setBlackoutDateInput("");
      setCampaignSteps([]);
      await load();
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError, "Failed to create schedule"));
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (label: string, action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      await load();
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError, `Failed to ${label}`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Schedules</h1>
        <p className="page-subtitle">Profile-backed scheduled runs and campaign launches.</p>
      </section>

      {error ? <div className="error-banner" style={{ padding: "12px 16px" }}>{error}</div> : null}

      <section className="panel next-trigger-panel">
        <div className="next-trigger-copy">
          <span className="stat-label">Next Automatic Trigger</span>
          <strong className="next-trigger-time">
            {nextAutomaticSchedule
              ? formatDateTime(nextAutomaticSchedule.next_run_at, { timeZone: nextAutomaticSchedule.timezone || "UTC" })
              : "No automatic trigger scheduled"}
          </strong>
          <span className="muted">
            {nextAutomaticSchedule
              ? `${nextAutomaticSchedule.name} - ${formatTimeUntil(nextAutomaticSchedule.next_run_at)}`
              : "Create or resume an hourly, daily, weekday, weekly, or monthly schedule to see it here."}
          </span>
        </div>
        {nextAutomaticSchedule ? (
          <div className="next-trigger-context">
            <span className={`status-pill ${statusClass(nextAutomaticSchedule.status)}`}>{nextAutomaticSchedule.status}</span>
            <span className="muted">{(nextAutomaticSchedule.period ?? nextAutomaticSchedule.cadence)} / {nextAutomaticSchedule.timezone}</span>
          </div>
        ) : null}
      </section>

      <section className="grid two">
        <form className="panel grid" onSubmit={submit}>
          <h2 className="section-title">Create Schedule</h2>
          <label className="grid">
            <span className="muted">Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className="grid">
            <span className="muted">Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} />
          </label>
          <div className="grid three">
            <label className="grid">
              <span className="muted">Type</span>
              <select value={scheduleType} onChange={(event) => setScheduleType(event.target.value as ScheduleType)}>
                <option value="simple">Simple</option>
                <option value="campaign">Campaign</option>
              </select>
            </label>
            <label className="grid">
              <span className="muted">Period</span>
              <select value={period} onChange={(event) => setPeriod(event.target.value as SchedulePeriod)}>
                {periodOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="grid">
              <span className="muted">Runs Per Period</span>
              <input type="number" min={1} value={runsPerPeriod} onChange={(event) => setRunsPerPeriod(Math.max(1, Number(event.target.value) || 1))} />
            </label>
          </div>
          <div className="grid two">
            <label className="grid">
              <span className="muted">Start At</span>
              <input type="datetime-local" value={anchorStartAt} onChange={(event) => setAnchorStartAt(event.target.value)} required />
            </label>
            <label className="grid">
              <span className="muted">Timezone</span>
              <select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                {timezoneOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <fieldset className="field-group">
            <legend>Stop Rule</legend>
            <div className="grid three">
              <label className="grid">
                <span className="muted">Rule</span>
                <select value={stopRule} onChange={(event) => setStopRule(event.target.value as ScheduleStopRule)}>
                  <option value="never">Never</option>
                  <option value="end_at">End At</option>
                  <option value="duration">Duration</option>
                </select>
              </label>
              {stopRule === "end_at" ? (
                <label className="grid">
                  <span className="muted">End At</span>
                  <input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} required />
                </label>
              ) : null}
              {stopRule === "duration" ? (
                <label className="grid">
                  <span className="muted">Duration (Hours)</span>
                  <input type="number" min={1} value={durationHours} onChange={(event) => setDurationHours(Math.max(1, Number(event.target.value) || 1))} />
                </label>
              ) : null}
            </div>
          </fieldset>
          <div className="grid two">
            <label className="grid">
              <span className="muted">Window Start</span>
              <input type="time" value={runWindowStart} onChange={(event) => setRunWindowStart(event.target.value)} />
            </label>
            <label className="grid">
              <span className="muted">Window End</span>
              <input type="time" value={runWindowEnd} onChange={(event) => setRunWindowEnd(event.target.value)} />
            </label>
          </div>
          <section className="panel" style={{ padding: "12px 14px" }}>
            <div className="grid">
              <span className="muted">Before Submit Preview</span>
              <strong>{schedulePreview.mode === "automatic" ? "Automatic" : "Manual-only"}</strong>
              <span className="muted">
                {schedulePreview.nextRunAt ? formatDateTime(schedulePreview.nextRunAt, { timeZone: timezone }) : "No automatic trigger yet"}
              </span>
              <span className="muted">{schedulePreview.reason}</span>
            </div>
          </section>
          <p className="form-help">Scheduling precedence is Start/Period, Stop Rule, Run Window, then Blackout Dates.</p>
          <fieldset className="field-group">
            <legend>Blackout Dates</legend>
            <div className="grid two">
              <label className="grid">
                <span className="muted">Skip Date</span>
                <input type="date" value={blackoutDateInput} onChange={(event) => setBlackoutDateInput(event.target.value)} />
              </label>
              <button className="secondary" type="button" onClick={addBlackoutDate} disabled={!blackoutDateInput}>
                Add Blackout Date
              </button>
            </div>
            <p className="form-help">Blackout dates are full calendar days in the schedule timezone when automatic triggers are skipped. Manual Trigger still works.</p>
            {blackoutDates.length ? (
              <div className="pill-list" aria-label="Selected blackout dates">
                {blackoutDates.map((date) => (
                  <span className="chip" key={date}>
                    {date}
                    <button className="pill-remove" type="button" onClick={() => removeBlackoutDate(date)} aria-label={`Remove blackout date ${date}`}>
                      x
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
          </fieldset>

          {scheduleType === "simple" ? (
            <label className="grid">
              <span className="muted">Run Profile</span>
              <select value={profileId} onChange={(event) => setProfileId(event.target.value)} required>
                {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
              </select>
            </label>
          ) : (
            <div className="grid">
              <div className="grid three">
                <label className="grid">
                  <span className="muted">Step Profile</span>
                  <select value={stepProfileId} onChange={(event) => setStepProfileId(event.target.value)}>
                    {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                  </select>
                </label>
                <label className="grid">
                  <span className="muted">Repeat</span>
                  <input type="number" min={1} max={100} value={stepRepeatCount} onChange={(event) => setStepRepeatCount(Number(event.target.value))} />
                </label>
                <label className="grid">
                  <span className="muted">Spacing Seconds</span>
                  <input type="number" min={0} value={stepSpacingSeconds} onChange={(event) => setStepSpacingSeconds(Number(event.target.value))} />
                </label>
              </div>
              <button className="secondary" type="button" onClick={addCampaignStep}>Add Campaign Step</button>
              {campaignSteps.length ? (
                <div className="responsive-table">
                  <table>
                    <thead>
                      <tr><th>Step</th><th>Profile</th><th>Repeat</th><th>Spacing</th><th></th></tr>
                    </thead>
                    <tbody>
                      {campaignSteps.map((step, index) => (
                        <tr key={`${step.profile_id}-${index}`}>
                          <td>{index + 1}</td>
                          <td>{profileById.get(step.profile_id)?.name ?? step.profile_id}</td>
                          <td>{step.repeat_count}</td>
                          <td>{step.spacing_seconds}s</td>
                          <td>
                            <button className="secondary small" type="button" onClick={() => setCampaignSteps((current) => current.filter((_, itemIndex) => itemIndex !== index))}>
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          )}

          <button disabled={busy || !profiles.length}>{busy ? "Working..." : "Create Schedule"}</button>
        </form>

        <section className="panel">
          <h2 className="section-title">Health</h2>
          <div className="grid four">
            <div className="stat"><span className="stat-label">Total</span><strong className="stat-value">{summary?.total ?? 0}</strong></div>
            <div className="stat"><span className="stat-label">Active</span><strong className="stat-value">{summary?.health.active ?? 0}</strong></div>
            <div className="stat"><span className="stat-label">Paused</span><strong className="stat-value">{summary?.health.paused ?? 0}</strong></div>
            <div className="stat"><span className="stat-label">Disabled</span><strong className="stat-value">{summary?.health.disabled ?? 0}</strong></div>
          </div>
          <h2 className="section-title" style={{ marginTop: "20px" }}>Recent Executions</h2>
          {summary?.recent_executions.length ? (
            <div className="responsive-table">
              <table>
                <thead><tr><th>Schedule</th><th>Status</th><th>Run</th><th>Started</th></tr></thead>
                <tbody>
                  {summary.recent_executions.map((execution) => (
                    <tr key={execution.id}>
                      <td>{execution.schedule_id}</td>
                      <td><span className={`status-pill ${statusClass(execution.status)}`}>{execution.status}</span></td>
                      <td>{execution.run_id ?? "--"}</td>
                      <td>{formatDateTime(execution.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="chart-empty">No schedule executions yet.</div>
          )}
        </section>
      </section>

      <section className="panel">
        <h2 className="section-title">Schedule List</h2>
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Profile / Steps</th>
                <th>Cadence</th>
                <th>Next Trigger</th>
                <th>Last Trigger</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((schedule) => (
                <tr key={schedule.id}>
                  <td>
                    <strong>{schedule.name}</strong>
                    {schedule.description ? <div className="muted">{schedule.description}</div> : null}
                  </td>
                  <td>{schedule.schedule_type}</td>
                  <td><span className={`status-pill ${statusClass(schedule.status)}`}>{schedule.status}</span></td>
                  <td>
                    {schedule.schedule_type === "simple"
                      ? profileById.get(schedule.profile_id ?? 0)?.name ?? schedule.profile_id ?? "--"
                      : `${schedule.campaign_steps.length} steps`}
                  </td>
                  <td>
                    <div>{(schedule.period ?? schedule.cadence)} / {schedule.timezone}</div>
                    {schedule.anchor_start_at ? (
                      <div className="muted">Start: {formatDateTime(schedule.anchor_start_at, { timeZone: schedule.timezone || "UTC" })}</div>
                    ) : null}
                    {schedule.stop_rule ? (
                      <div className="muted">
                        Stop: {schedule.stop_rule === "end_at" ? `End at ${schedule.end_at ? formatDateTime(schedule.end_at, { timeZone: schedule.timezone || "UTC" }) : "--"}` : schedule.stop_rule === "duration" ? `After ${(schedule.duration_seconds ?? 0) / 3600}h` : "Never"}
                      </div>
                    ) : (
                      <div className="muted">{formatActiveRange(schedule)}</div>
                    )}
                    <div className="muted">Runs per period: {schedule.runs_per_period ?? 1}</div>
                    {schedule.blackout_dates.length ? (
                      <div className="muted">Blackouts: {schedule.blackout_dates.join(", ")}</div>
                    ) : null}
                  </td>
                  <td>
                    <strong>{nextTriggerLabel(schedule)}</strong>
                    <div className="muted">{nextTriggerMeta(schedule)}</div>
                    {schedule.current_period_runs?.length ? (
                      <div className="muted">Current period runs: {schedule.current_period_runs.length}</div>
                    ) : null}
                    <div className="muted">Mode: {schedule.execution_mode_label}</div>
                  </td>
                  <td>{schedule.last_triggered_at ? formatDateTime(schedule.last_triggered_at, { timeZone: schedule.timezone || "UTC" }) : "--"}</td>
                  <td>
                    <div className="row-actions">
                      <button className="small" disabled={busy || schedule.status === "disabled" || schedule.status === "deleted"} onClick={() => runAction("trigger schedule", () => triggerSchedule(schedule.id))}>
                        Trigger
                      </button>
                      {schedule.status === "paused" ? (
                        <button className="secondary small" disabled={busy} onClick={() => runAction("resume schedule", () => setScheduleStatus(schedule.id, "resume"))}>Resume</button>
                      ) : (
                        <button className="secondary small" disabled={busy || schedule.status === "deleted"} onClick={() => runAction("pause schedule", () => setScheduleStatus(schedule.id, "pause"))}>Pause</button>
                      )}
                      <button className="secondary small" disabled={busy || schedule.status === "deleted"} onClick={() => runAction("disable schedule", () => setScheduleStatus(schedule.id, "disable"))}>Disable</button>
                      {schedule.status === "deleted" ? (
                        <button className="secondary small" disabled={busy} onClick={() => runAction("restore schedule", () => setScheduleStatus(schedule.id, "restore"))}>Restore</button>
                      ) : (
                        <button className="secondary small" disabled={busy} onClick={() => runAction("delete schedule", () => setScheduleStatus(schedule.id, "delete"))}>Delete</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {!schedules.length ? (
                <tr><td colSpan={8} className="muted">No schedules configured.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
