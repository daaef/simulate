"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ErrorBanner } from "../../../components/ErrorBanner";
import { LastUpdatedIndicator } from "../../../components/LastUpdatedIndicator";
import {
  ApiRequestError,
  createSchedule,
  fetchRunProfiles,
  fetchScheduleSummary,
  fetchSchedules,
  fetchSystemTimezones,
  setScheduleStatus,
  triggerSchedule,
  updateSchedule,
  type ScheduleUpsertRequest,
  type CampaignStep,
  type RunProfile,
  type Schedule,
  type SchedulePeriod,
  type ScheduleRepeatRule,
  type ScheduleStopRule,
  type ScheduleSummary,
  type ScheduleType,
  type SystemTimezonesPolicy,
} from "../../../lib/api";
import { formatDateTime, formatTimeUntil, parseTimestamp } from "../../../lib/time-format";

const repeatOptions: ScheduleRepeatRule[] = ["none", "daily", "weekly", "monthly", "weekdays", "custom"];
const repeatLabels: Record<ScheduleRepeatRule, string> = {
  none: "Once (no repeat)",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  annually: "Annually",
  weekdays: "Weekdays (Mon–Fri)",
  custom: "Custom days",
};
const weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

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

function schedulePhaseLabel(phase: string): string {
  if (phase === "queued") return "Queued";
  if (phase === "started") return "Starting";
  if (phase === "launched") return "Run launched";
  if (phase === "overlap_skipped") return "Overlap skipped";
  if (phase === "failed") return "Launch failed";
  return phase;
}

function schedulePhaseClass(phase: string): string {
  if (phase === "queued") return "status-info";
  if (phase === "started") return "status-warning";
  if (phase === "launched") return "status-success";
  if (phase === "overlap_skipped") return "status-warning";
  if (phase === "failed") return "status-danger";
  return "status-info";
}

function runStatusLabel(status?: string | null): string {
  if (!status) return "No run";
  const normalized = status.toLowerCase();
  if (normalized === "queued") return "Queued";
  if (normalized === "running") return "Running";
  if (normalized === "succeeded") return "Succeeded";
  if (normalized === "failed") return "Failed";
  if (normalized === "cancelled") return "Cancelled";
  if (normalized === "cancelling") return "Cancelling";
  return status;
}

function runStatusClass(status?: string | null): string {
  if (!status) return "status-info";
  const normalized = status.toLowerCase();
  if (normalized === "succeeded") return "status-success";
  if (normalized === "failed" || normalized === "cancelled") return "status-danger";
  if (normalized === "running" || normalized === "cancelling" || normalized === "queued") return "status-warning";
  return "status-info";
}

function nextTriggerLabel(schedule: Schedule): string {
  if (schedule.next_run_at) return formatDateTime(schedule.next_run_at, { timeZone: schedule.timezone || "UTC" });
  if (schedule.status === "active" && schedule.execution_mode_label === "manual_only") return "Manual only";
  if (schedule.status === "paused") return "Paused";
  if (schedule.status === "disabled") return "Disabled";
  return "Not scheduled";
}

function nextTriggerMeta(schedule: Schedule): string {
  if (schedule.next_run_at) return `${formatTimeUntil(schedule.next_run_at)} · ${schedule.timezone || "UTC"}`;
  if (schedule.next_run_reason === "outside_active_range") return "No future run: outside active range.";
  if (schedule.next_run_reason === "outside_stop_range") return "No future run: outside stop range.";
  if (schedule.next_run_reason === "window_clipped") return "Next run clipped by run window constraints.";
  if (schedule.next_run_reason === "blackout_skipped") return "Next run skipped one or more blackout dates.";
  if (schedule.next_run_reason === "shifted_to_window_start") return "Next run shifted to window start.";
  if (schedule.status === "active" && schedule.execution_mode_label === "manual_only") return "Trigger manually to run.";
  if (schedule.status === "paused") return "Resume to recalculate next trigger.";
  if (schedule.status === "disabled") return "Disabled — will not run automatically.";
  return "No automatic trigger available.";
}

function executionModeLabel(label?: string | null): string {
  if (!label) return "";
  if (label === "manual_only") return "Manual trigger only";
  if (label === "automatic") return "Automatic";
  return label;
}

function toScheduleDateTime(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString();
}

function toDateTimeLocalInput(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function capitalizeFirst(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
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
  const router = useRouter();
  const SCHEDULES_REFRESH_MS = 15000;
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [summary, setSummary] = useState<ScheduleSummary | null>(null);
  const [timezonePolicy, setTimezonePolicy] = useState<SystemTimezonesPolicy | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scheduleType] = useState<ScheduleType>("campaign");
  const [profileId, setProfileId] = useState("");
  const [period, setPeriod] = useState<SchedulePeriod>("daily");
  const [anchorStartAt, setAnchorStartAt] = useState("");
  const [stopRule, setStopRule] = useState<ScheduleStopRule>("never");
  const [endAt, setEndAt] = useState("");
  const [durationHours, setDurationHours] = useState(5);
  const [runsPerPeriod, setRunsPerPeriod] = useState(1);
  const [repeat, setRepeat] = useState<ScheduleRepeatRule>("daily");
  const [allDay, setAllDay] = useState(false);
  const [customWeekdays, setCustomWeekdays] = useState<string[]>(["monday", "wednesday", "friday"]);
  const [timezone, setTimezone] = useState(defaultScheduleTimezone);
  const [dailyTimes, setDailyTimes] = useState<string[]>(["09:00"]);
  const [weeklySlots, setWeeklySlots] = useState<Array<{ weekday: string; time: string }>>([{ weekday: "monday", time: "09:00" }]);
  const [monthlyMode, setMonthlyMode] = useState<"day_of_month" | "weekday_ordinal">("day_of_month");
  const [monthlyDaySlots, setMonthlyDaySlots] = useState<Array<{ day: number; time: string }>>([{ day: 1, time: "09:00" }]);
  const [monthlyOrdinalSlots, setMonthlyOrdinalSlots] = useState<Array<{ ordinal: number; weekday: string; time: string }>>([{ ordinal: 1, weekday: "monday", time: "09:00" }]);
  const [blackoutDates, setBlackoutDates] = useState<string[]>([]);
  const [blackoutDateInput, setBlackoutDateInput] = useState("");
  const [campaignSteps, setCampaignSteps] = useState<CampaignStep[]>([]);
  const [stepProfileId, setStepProfileId] = useState("");
  const [stepRepeatCount, setStepRepeatCount] = useState(1);
  const [stepSpacingMinutes, setStepSpacingMinutes] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionBusyIds, setActionBusyIds] = useState<Set<number>>(new Set());
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null);
  const [editingScheduleName, setEditingScheduleName] = useState<string>("");
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);
  const loadInFlightRef = useRef(false);
  const showFormRef = useRef(false);
  const scheduleListRef = useRef<HTMLElement>(null);
  const [activeStatusFilter, setActiveStatusFilter] = useState<"all" | "active" | "paused" | "disabled">("all");

  const profileById = useMemo(() => new Map(profiles.map((profile) => [profile.id, profile])), [profiles]);
  const recentScheduleStates = useMemo(
    () => summary?.recent_schedule_states ?? [],
    [summary?.recent_schedule_states],
  );
  const upcomingSchedules = useMemo(() => {
    return schedules
      .filter((schedule) => parseTimestamp(schedule.next_run_at) != null)
      .sort((a, b) => {
        const at = parseTimestamp(a.next_run_at) ?? Number.POSITIVE_INFINITY;
        const bt = parseTimestamp(b.next_run_at) ?? Number.POSITIVE_INFINITY;
        return at - bt;
      })
      .slice(0, 3);
  }, [schedules]);

  const upcomingTotal = useMemo(
    () => schedules.filter((s) => parseTimestamp(s.next_run_at) != null).length,
    [schedules],
  );

  const filteredSchedules = useMemo(() => {
    if (activeStatusFilter === "all") return schedules;
    return schedules.filter((schedule) => schedule.status === activeStatusFilter);
  }, [schedules, activeStatusFilter]);

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
      return { mode, nextRunAt: null as string | null, reason: "Set a Start date to enable automatic scheduling." };
    }
    const now = new Date();
    const anchor = new Date(anchorStartAt);
    let next = anchor;
    if (Number.isNaN(anchor.getTime())) {
      return { mode: "manual_only", nextRunAt: null as string | null, reason: "Set a valid Start date and time." };
    }
    while (next.getTime() <= now.getTime()) {
      if (period === "daily") {
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
      reason: "Approximate — final time is resolved on save using timezone, stop rules, and blackout dates.",
    };
  }, [period, anchorStartAt]);

  const load = async (options?: { silent?: boolean }) => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    try {
      const [profilePayload, schedulePayload, summaryPayload, timezonePayload] = await Promise.all([
        fetchRunProfiles(),
        fetchSchedules(false),
        fetchScheduleSummary(),
        fetchSystemTimezones(),
      ]);
      setProfiles(profilePayload);
      setSchedules(schedulePayload);
      setSummary(summaryPayload);
      setTimezonePolicy(timezonePayload);
      // Seed form-input defaults only when the form is closed, so the 15s poll
      // never clobbers values the user is actively editing. Read the ref (not
      // `showForm`) because the interval's captured closure sees stale state.
      if (!showFormRef.current) {
        if (!profileId && profilePayload[0]) setProfileId(String(profilePayload[0].id));
        if (!stepProfileId && profilePayload[0]) setStepProfileId(String(profilePayload[0].id));
        if (timezonePayload) {
          const local = defaultScheduleTimezone();
          const tzOptions =
            timezonePayload.mode === "allowlist"
              ? (timezonePayload.allowed_timezones ?? [])
              : timezonePayload.available_timezones;
          const next = tzOptions.includes(local) ? local : (tzOptions[0] ?? "UTC");
          setTimezone(next);
        }
      }
      if (!options?.silent) {
        setError(null);
      }
      setLastUpdatedAt(new Date());
    } finally {
      loadInFlightRef.current = false;
    }
  };

  useEffect(() => {
    showFormRef.current = showForm;
  }, [showForm]);

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

  useEffect(() => {
    if (openMenuId === null) return;
    const close = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".action-menu")) setOpenMenuId(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [openMenuId]);

  useEffect(() => {
    if (!showForm) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") cancelEditSchedule(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showForm]);

  const addCampaignStep = () => {
    const parsedProfileId = Number(stepProfileId);
    if (!parsedProfileId) {
      setFormError("Choose a profile before adding a campaign step.");
      return;
    }
    setCampaignSteps((current) => [
      ...current,
      {
        profile_id: parsedProfileId,
        repeat_count: Math.max(1, stepRepeatCount),
        spacing_seconds: Math.max(0, stepSpacingMinutes * 60),
        timeout_seconds: 900,
        failure_policy: "continue",
        execution_mode: "saved_profile",
      },
    ]);
    setFormError(null);
  };

  const moveCampaignStep = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= campaignSteps.length) return;
    setCampaignSteps((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const addBlackoutDate = () => {
    if (!blackoutDateInput) return;
    setBlackoutDates((current) => Array.from(new Set([...current, blackoutDateInput])).sort());
    setBlackoutDateInput("");
    setFormError(null);
  };

  const removeBlackoutDate = (date: string) => {
    setBlackoutDates((current) => current.filter((item) => item !== date));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setBusy(true);
    try {
      const anchorMs = anchorStartAt ? new Date(anchorStartAt).getTime() : null;
      if (anchorMs == null || Number.isNaN(anchorMs)) {
        setFormError("Choose a valid start date and time.");
        return;
      }
      if (stopRule === "end_at") {
        const endMs = endAt ? new Date(endAt).getTime() : null;
        if (endMs == null || Number.isNaN(endMs)) {
          setFormError("Choose a valid end date and time.");
          return;
        }
        if (endMs <= anchorMs) {
          setFormError("End time must be after Start time.");
          return;
        }
      }
      if (stopRule === "duration" && durationHours <= 0) {
        setFormError("Duration must be greater than 0.");
        return;
      }
      if (!campaignSteps.length) {
        setFormError("Add at least one campaign step before saving.");
        return;
      }

      const parsedProfileId = Number(profileId);
      const derivedPeriod: SchedulePeriod = repeat === "weekly" ? "weekly" : repeat === "monthly" ? "monthly" : "daily";
      setPeriod(derivedPeriod);
      let parsedSlots: Record<string, unknown>[] = [];
      if (!allDay) {
        if (derivedPeriod === "daily") {
          parsedSlots = dailyTimes.slice(0, Math.max(1, runsPerPeriod)).map((time) => ({ time }));
        } else if (derivedPeriod === "weekly") {
          parsedSlots = weeklySlots.slice(0, Math.max(1, runsPerPeriod)).map((slot) => ({ weekday: slot.weekday, time: slot.time }));
        } else if (monthlyMode === "day_of_month") {
          parsedSlots = monthlyDaySlots.slice(0, Math.max(1, runsPerPeriod)).map((slot) => ({ kind: "day_of_month", day: slot.day, time: slot.time }));
        } else {
          parsedSlots = monthlyOrdinalSlots.slice(0, Math.max(1, runsPerPeriod)).map((slot) => ({ kind: "weekday_ordinal", ordinal: slot.ordinal, weekday: slot.weekday, time: slot.time }));
        }
      }
      const recurrenceConfig = repeat === "custom" ? { weekdays: customWeekdays } : {};
      const payload: ScheduleUpsertRequest = {
        name,
        description,
        schedule_type: scheduleType,
        profile_id: parsedProfileId || undefined,
        anchor_start_at: toScheduleDateTime(anchorStartAt),
        period: derivedPeriod,
        stop_rule: stopRule,
        end_at: stopRule === "end_at" ? toScheduleDateTime(endAt) : undefined,
        duration_seconds: stopRule === "duration" ? Math.max(1, Math.round(durationHours * 3600)) : undefined,
        runs_per_period: Math.max(1, runsPerPeriod),
        repeat,
        all_day: allDay,
        run_slots: parsedSlots,
        recurrence_config: recurrenceConfig,
        cadence: period,
        timezone,
        active_from: undefined,
        active_until: undefined,
        run_window_start: undefined,
        run_window_end: undefined,
        blackout_dates: blackoutDates,
        failure_policy: "continue",
        campaign_steps: campaignSteps,
      };
      if (editingScheduleId) {
        await updateSchedule(editingScheduleId, payload);
      } else {
        await createSchedule(payload);
      }
      setName("");
      setDescription("");
      setAnchorStartAt("");
      setEndAt("");
      setRunsPerPeriod(1);
      setDailyTimes(["09:00"]);
      setBlackoutDates([]);
      setBlackoutDateInput("");
      setCampaignSteps([]);
      setEditingScheduleId(null);
      setEditingScheduleName("");
      setShowForm(false);
      setFormError(null);
      await load();
      setError(null);
    } catch (caughtError) {
      setFormError(toMessage(caughtError, editingScheduleId ? "Failed to update schedule" : "Failed to create schedule"));
    } finally {
      setBusy(false);
    }
  };

  const startEditSchedule = (schedule: Schedule) => {
    setEditingScheduleId(schedule.id);
    setEditingScheduleName(schedule.name || "");
    setName(schedule.name || "");
    setDescription(schedule.description || "");
    setProfileId(String(schedule.profile_id || profiles[0]?.id || ""));
    setAnchorStartAt(toDateTimeLocalInput(schedule.anchor_start_at));
    setStopRule(schedule.stop_rule || "never");
    setEndAt(toDateTimeLocalInput(schedule.end_at));
    setDurationHours(Math.max(1, Math.round((schedule.duration_seconds || 3600) / 3600)));
    setRunsPerPeriod(Math.max(1, schedule.runs_per_period || 1));
    setRepeat(schedule.repeat || "daily");
    setAllDay(Boolean(schedule.all_day));
    setTimezone(schedule.timezone || defaultScheduleTimezone());
    setBlackoutDates([...(schedule.blackout_dates || [])]);
    setCampaignSteps([...(schedule.campaign_steps || [])]);
    const recurrenceWeekdays = Array.isArray(schedule.recurrence_config?.weekdays)
      ? (schedule.recurrence_config?.weekdays as string[])
      : ["monday", "wednesday", "friday"];
    setCustomWeekdays(recurrenceWeekdays);

    const slots = Array.isArray(schedule.run_slots) ? schedule.run_slots : [];
    const periodValue: SchedulePeriod = (schedule.period || "daily") as SchedulePeriod;
    setPeriod(periodValue);
    if (periodValue === "weekly") {
      const nextWeekly = slots
        .map((slot) => ({
          weekday: String(slot.weekday || "monday"),
          time: String(slot.time || "09:00"),
        }))
        .filter((slot) => slot.time);
      setWeeklySlots(nextWeekly.length ? nextWeekly : [{ weekday: "monday", time: "09:00" }]);
    } else if (periodValue === "monthly") {
      const daySlots = slots
        .filter((slot) => String(slot.kind || "day_of_month") === "day_of_month")
        .map((slot) => ({
          day: Math.max(1, Math.min(31, Number(slot.day || 1))),
          time: String(slot.time || "09:00"),
        }));
      const ordinalSlots = slots
        .filter((slot) => String(slot.kind || "") === "weekday_ordinal")
        .map((slot) => ({
          ordinal: Math.max(1, Math.min(5, Number(slot.ordinal || 1))),
          weekday: String(slot.weekday || "monday"),
          time: String(slot.time || "09:00"),
        }));
      if (ordinalSlots.length && !daySlots.length) {
        setMonthlyMode("weekday_ordinal");
      } else {
        setMonthlyMode("day_of_month");
      }
      setMonthlyDaySlots(daySlots.length ? daySlots : [{ day: 1, time: "09:00" }]);
      setMonthlyOrdinalSlots(
        ordinalSlots.length ? ordinalSlots : [{ ordinal: 1, weekday: "monday", time: "09:00" }]
      );
    } else {
      const nextDaily = slots
        .map((slot) => String(slot.time || "09:00"))
        .filter((time) => Boolean(time));
      setDailyTimes(nextDaily.length ? nextDaily : ["09:00"]);
    }
    setFormError(null);
    setShowForm(true);
    setError(null);
  };

  const cancelEditSchedule = () => {
    setEditingScheduleId(null);
    setEditingScheduleName("");
    setShowForm(false);
    setFormError(null);
    setConfirmDeleteId(null);
    setName("");
    setDescription("");
    setAnchorStartAt("");
    setEndAt("");
    setRunsPerPeriod(1);
    setStopRule("never");
    setRepeat("daily");
    setAllDay(false);
    setDailyTimes(["09:00"]);
    setWeeklySlots([{ weekday: "monday", time: "09:00" }]);
    setMonthlyMode("day_of_month");
    setMonthlyDaySlots([{ day: 1, time: "09:00" }]);
    setMonthlyOrdinalSlots([{ ordinal: 1, weekday: "monday", time: "09:00" }]);
    setBlackoutDates([]);
    setBlackoutDateInput("");
    setCampaignSteps([]);
    setError(null);
  };

  const runRowAction = async (scheduleId: number, label: string, action: () => Promise<unknown>) => {
    setActionBusyIds((ids) => new Set([...ids, scheduleId]));
    try {
      await action();
      await load();
      setError(null);
    } catch (caughtError) {
      setError(toMessage(caughtError, `Failed to ${label}`));
    } finally {
      setActionBusyIds((ids) => {
        const next = new Set(ids);
        next.delete(scheduleId);
        return next;
      });
    }
  };

  const goToList = (filter: "all" | "active" | "paused" | "disabled") => {
    setActiveStatusFilter(filter);
    scheduleListRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="page-shell">
      <section className="page-header">
        <div className="page-header__meta">
          <h1 className="page-title">Schedules</h1>
          <LastUpdatedIndicator updatedAt={lastUpdatedAt} onRefresh={() => void load()} />
        </div>
        <p className="page-subtitle">Automate and schedule recurring simulation campaigns.</p>
      </section>

      {error ? <ErrorBanner message={error} onRetry={() => void load()} /> : null}

      <div className="schedules-metrics">
        {(() => {
          const total = summary?.total ?? 0;
          const active = summary?.health.active ?? 0;
          const paused = summary?.health.paused ?? 0;
          const disabled = summary?.health.disabled ?? 0;
          const degraded = summary?.health.degraded_campaigns ?? 0;
          return (
            <>
              <button type="button" className={`metric-card metric-card--total${total === 0 ? " metric-card--zero" : ""}`} onClick={total > 0 ? () => goToList("all") : undefined} disabled={total === 0}>
                <span className="stat-label">Total Schedules</span>
                <strong className="stat-value">{total}</strong>
                <span className="metric-card__cta muted">{total > 0 ? "View all →" : "No schedules yet"}</span>
              </button>
              <button type="button" className={`metric-card metric-card--active${active === 0 ? " metric-card--zero" : ""}`} onClick={active > 0 ? () => goToList("active") : undefined} disabled={active === 0}>
                <span className="stat-label">Active</span>
                <strong className="stat-value">{active}</strong>
                <span className="metric-card__cta muted">{active > 0 ? "View active →" : "None active"}</span>
              </button>
              <button type="button" className={`metric-card metric-card--paused${paused === 0 ? " metric-card--zero" : ""}`} onClick={paused > 0 ? () => goToList("paused") : undefined} disabled={paused === 0}>
                <span className="stat-label">Paused</span>
                <strong className="stat-value">{paused}</strong>
                <span className="metric-card__cta muted">{paused > 0 ? "View paused →" : "None paused"}</span>
              </button>
              <button type="button" className={`metric-card metric-card--disabled${disabled === 0 ? " metric-card--zero" : ""}`} onClick={disabled > 0 ? () => goToList("disabled") : undefined} disabled={disabled === 0}>
                <span className="stat-label">Disabled</span>
                <strong className="stat-value">{disabled}</strong>
                <span className="metric-card__cta muted">{disabled > 0 ? "View disabled →" : "None disabled"}</span>
              </button>
              {degraded > 0 ? (
                <button type="button" className="metric-card metric-card--degraded" onClick={() => goToList("all")}>
                  <span className="stat-label">Degraded</span>
                  <strong className="stat-value">{degraded}</strong>
                  <span className="metric-card__cta muted">Needs attention →</span>
                </button>
              ) : null}
            </>
          );
        })()}
      </div>

      <section className="grid two schedules-activity-row">
        <div className="panel">
          <h2 className="section-title">Upcoming Triggers</h2>
          {upcomingSchedules.length ? (
            <>
              <div className="upcoming-list">
                {upcomingSchedules.map((schedule) => (
                  <div key={schedule.id} className="upcoming-item">
                    <div className="upcoming-item__meta">
                      <strong>{schedule.name}</strong>
                      <span className="muted">{capitalizeFirst(schedule.period ?? schedule.cadence ?? "")} · {schedule.timezone}</span>
                    </div>
                    <div className="upcoming-item__detail">
                      <span>{formatDateTime(schedule.next_run_at, { timeZone: schedule.timezone || "UTC" })}</span>
                      <span className="muted">{formatTimeUntil(schedule.next_run_at)}</span>
                      <span className={`status-pill ${statusClass(schedule.status)}`}>{capitalizeFirst(schedule.status)}</span>
                    </div>
                  </div>
                ))}
              </div>
              {upcomingTotal > 3 ? (
                <p className="muted" style={{ marginTop: "8px", fontSize: "12px" }}>Showing 3 of {upcomingTotal} upcoming triggers.</p>
              ) : null}
            </>
          ) : (
            <p className="muted" style={{ marginTop: "10px" }}>No automatic triggers scheduled. Create or resume a schedule to see upcoming runs here.</p>
          )}
        </div>

        <section className="panel">
          <h2 className="section-title">Recent Executions</h2>
          {recentScheduleStates.length ? (
            <div className="schedule-execution-cards">
              {recentScheduleStates.map((state) => {
                const clickable = state.latest_run_id != null;
                const title = clickable ? "View run" : "Run not created";
                const handleNavigate = () => {
                  if (!state.latest_run_id) return;
                  router.push(`/runs/${state.latest_run_id}`);
                };
                return (
                  <button
                    key={`schedule-state-${state.schedule_id}`}
                    type="button"
                    className={`schedule-execution-card${clickable ? " clickable" : " disabled"}`}
                    onClick={handleNavigate}
                    disabled={!clickable}
                    title={title}
                    aria-label={title}
                  >
                    <div className="schedule-execution-card-main">
                      <strong>{state.schedule_name || `Schedule #${state.schedule_id}`}</strong>
                      <div className="schedule-execution-primary">
                        {state.last_triggered_at ? formatDateTime(state.last_triggered_at) : "Not triggered yet"}
                        {state.latest_run_finished_at ? ` · finished ${formatDateTime(state.latest_run_finished_at)}` : ""}
                      </div>
                      <div className="muted">
                        {state.latest_run_id ? `Run #${state.latest_run_id}` : "No run created yet"}
                      </div>
                    </div>
                    <div className="schedule-execution-card-statuses">
                      <span className={`status-pill ${schedulePhaseClass(state.schedule_phase)}`}>
                        {schedulePhaseLabel(state.schedule_phase)}
                      </span>
                      <span className={`status-pill ${runStatusClass(state.latest_run_status)}`}>
                        {runStatusLabel(state.latest_run_status)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="chart-empty">No schedule executions yet.</div>
          )}
        </section>
      </section>

      <section className="panel" ref={scheduleListRef} id="schedule-list">
        <div className="schedule-list-header">
          <h2 className="section-title">Schedule List</h2>
          <div className="schedule-list-controls">
            <div className="filter-tabs">
              {(["all", "active", "paused", "disabled"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  className={`filter-tab${activeStatusFilter === f ? " filter-tab--active" : ""}`}
                  onClick={() => setActiveStatusFilter(f)}
                >
                  {capitalizeFirst(f)}
                  <span className="filter-tab__count">
                  {f === "all" ? schedules.length : schedules.filter((s) => s.status === f).length}
                  </span>
                </button>
              ))}
            </div>
            <button type="button" onClick={() => { setEditingScheduleId(null); setShowForm(true); }}>
              + New Schedule
            </button>
          </div>
        </div>
        <div className="responsive-table">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Steps</th>
                <th>Cadence</th>
                <th>Next Trigger</th>
                <th>Last Trigger</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredSchedules.map((schedule) => {
                  const isDisabled = schedule.status === "disabled";
                  const isPaused = schedule.status === "paused";
                  const canPause = !isDisabled && !isPaused;
                  const canDisable = !isDisabled;
                  const canEnable = isDisabled;
                  const canTrigger = !isDisabled;
                  const rowBusy = actionBusyIds.has(schedule.id);
                  return (
                    <tr key={schedule.id}>
                      <td>
                        <strong>{schedule.name}</strong>
                        {schedule.description ? <div className="muted">{schedule.description}</div> : null}
                      </td>
                      <td><span className={`status-pill ${statusClass(schedule.status)}`}>{capitalizeFirst(schedule.status)}</span></td>
                      <td>
                        {schedule.schedule_type === "simple"
                          ? profileById.get(schedule.profile_id ?? 0)?.name ?? schedule.profile_id ?? "--"
                          : `${schedule.campaign_steps.length} step${schedule.campaign_steps.length !== 1 ? "s" : ""}`}
                      </td>
                      <td>
                        <div>{capitalizeFirst(schedule.period ?? schedule.cadence ?? "")} · {schedule.timezone}</div>
                        {schedule.anchor_start_at ? (
                          <div className="muted">From {formatDateTime(schedule.anchor_start_at, { timeZone: schedule.timezone || "UTC" })}</div>
                        ) : null}
                        {schedule.stop_rule && schedule.stop_rule !== "never" ? (
                          <div className="muted">
                            {schedule.stop_rule === "end_at"
                              ? `Until ${schedule.end_at ? formatDateTime(schedule.end_at, { timeZone: schedule.timezone || "UTC" }) : "--"}`
                              : `After ${(schedule.duration_seconds ?? 0) / 3600}h`}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <strong>{nextTriggerLabel(schedule)}</strong>
                        <div className="muted">{nextTriggerMeta(schedule)}</div>
                        {schedule.execution_mode_label ? (
                          <div className="muted">{executionModeLabel(schedule.execution_mode_label)}</div>
                        ) : null}
                      </td>
                      <td>{schedule.last_triggered_at ? formatDateTime(schedule.last_triggered_at, { timeZone: schedule.timezone || "UTC" }) : "Never"}</td>
                      <td>
                        <div className="row-actions">
                          <button className="small" disabled={rowBusy || !canTrigger} onClick={() => runRowAction(schedule.id, "trigger schedule", () => triggerSchedule(schedule.id))}>
                            Trigger
                          </button>
                          <button className="secondary small" disabled={rowBusy} onClick={() => startEditSchedule(schedule)}>
                            Edit
                          </button>
                          <div className="action-menu">
                            <button
                              type="button"
                              className="secondary small"
                              aria-label="More actions"
                              aria-expanded={openMenuId === schedule.id}
                              onClick={() => { setOpenMenuId(openMenuId === schedule.id ? null : schedule.id); setConfirmDeleteId(null); }}
                            >
                              ···
                            </button>
                            {openMenuId === schedule.id ? (
                              <div className="action-menu__dropdown">
                                {isPaused ? (
                                  <button type="button" disabled={rowBusy} onClick={() => { setOpenMenuId(null); void runRowAction(schedule.id, "resume schedule", () => setScheduleStatus(schedule.id, "resume")); }}>Resume</button>
                                ) : null}
                                {canPause ? (
                                  <button type="button" disabled={rowBusy} onClick={() => { setOpenMenuId(null); void runRowAction(schedule.id, "pause schedule", () => setScheduleStatus(schedule.id, "pause")); }}>Pause</button>
                                ) : null}
                                {canEnable ? (
                                  <button type="button" disabled={rowBusy} onClick={() => { setOpenMenuId(null); void runRowAction(schedule.id, "enable schedule", () => setScheduleStatus(schedule.id, "resume")); }}>Enable</button>
                                ) : null}
                                {canDisable ? (
                                  <button type="button" disabled={rowBusy} onClick={() => { setOpenMenuId(null); void runRowAction(schedule.id, "disable schedule", () => setScheduleStatus(schedule.id, "disable")); }}>Disable</button>
                                ) : null}
                                {confirmDeleteId === schedule.id ? (
                                  <div className="action-menu__confirm">
                                    <span className="action-menu__confirm-label">Delete "{schedule.name}"?</span>
                                    <button type="button" className="danger" disabled={rowBusy} onClick={() => { setConfirmDeleteId(null); setOpenMenuId(null); void runRowAction(schedule.id, "delete schedule", () => setScheduleStatus(schedule.id, "delete")); }}>Yes, delete</button>
                                    <button type="button" disabled={rowBusy} onClick={() => setConfirmDeleteId(null)}>Cancel</button>
                                  </div>
                                ) : (
                                  <button type="button" className="danger" disabled={rowBusy} onClick={() => setConfirmDeleteId(schedule.id)}>Delete…</button>
                                )}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              {!filteredSchedules.length ? (
                <tr><td colSpan={7} className="muted">
                  {activeStatusFilter === "all" ? "No schedules configured." : `No ${activeStatusFilter} schedules.`}
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {showForm ? (
        <div
          className="drawer-overlay"
          onClick={cancelEditSchedule}
          aria-hidden="true"
        />
      ) : null}
      <div
        className={`drawer${showForm ? " drawer--open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={editingScheduleId ? `Edit: ${editingScheduleName || `Schedule #${editingScheduleId}`}` : "Create Schedule"}
      >
        <div className="drawer__header">
          <h2 className="section-title">{editingScheduleId ? `Edit: ${editingScheduleName || `Schedule #${editingScheduleId}`}` : "Create Schedule"}</h2>
          <button type="button" className="drawer__close secondary small" onClick={cancelEditSchedule} aria-label="Close drawer">×</button>
        </div>
        <form className="drawer__body grid" onSubmit={submit}>
          {formError ? (
            <div className="form-error-inline" role="alert">{formError}</div>
          ) : null}
          <label className="grid">
            <span className="muted">Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className="grid">
            <span className="muted">Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} />
          </label>
          <div className="grid two">
            <label className="grid">
              <span className="muted">Repeat</span>
              <select value={repeat} onChange={(event) => setRepeat(event.target.value as ScheduleRepeatRule)}>
                {repeatOptions.map((item) => <option key={item} value={item}>{repeatLabels[item]}</option>)}
              </select>
            </label>
            <label className="grid">
              <span className="muted">Runs per period</span>
              <input type="number" min={1} value={runsPerPeriod} onChange={(event) => setRunsPerPeriod(Math.max(1, Number(event.target.value) || 1))} />
            </label>
          </div>
          <label className="grid" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
            <input type="checkbox" checked={allDay} onChange={(event) => setAllDay(event.target.checked)} />
            <span>All day (no specific run time)</span>
          </label>
          {repeat === "custom" ? (
            <div className="grid">
              <span className="muted">Custom days</span>
              <div className="grid three">
                {weekdays.map((day) => (
                  <label key={day} style={{ flexDirection: "row", alignItems: "center", gap: "6px" }}>
                    <input
                      type="checkbox"
                      checked={customWeekdays.includes(day)}
                      onChange={(event) => {
                        setCustomWeekdays((current) =>
                          event.target.checked ? Array.from(new Set([...current, day])) : current.filter((item) => item !== day),
                        );
                      }}
                    />
                    {capitalizeFirst(day)}
                  </label>
                ))}
              </div>
            </div>
          ) : null}
          {!allDay ? (
            <div className="grid">
              <span className="muted">Run time slots</span>
              {(repeat === "weekly" ? Array.from({ length: runsPerPeriod }).map((_, index) => (
                <div className="grid two" key={`weekly-${index}`}>
                  <select value={weeklySlots[index]?.weekday ?? "monday"} onChange={(event) => setWeeklySlots((current) => {
                    const next = [...current];
                    next[index] = { weekday: event.target.value, time: next[index]?.time ?? "09:00" };
                    return next;
                  })}>
                    {weekdays.map((day) => <option key={day} value={day}>{capitalizeFirst(day)}</option>)}
                  </select>
                  <input type="time" value={weeklySlots[index]?.time ?? "09:00"} onChange={(event) => setWeeklySlots((current) => {
                    const next = [...current];
                    next[index] = { weekday: next[index]?.weekday ?? "monday", time: event.target.value };
                    return next;
                  })} />
                </div>
              )) : repeat === "monthly" ? (
                <div className="grid">
                  <select value={monthlyMode} onChange={(event) => setMonthlyMode(event.target.value as "day_of_month" | "weekday_ordinal")}>
                    <option value="day_of_month">Day of month</option>
                    <option value="weekday_ordinal">Weekday ordinal</option>
                  </select>
                  {monthlyMode === "day_of_month"
                    ? Array.from({ length: runsPerPeriod }).map((_, index) => (
                        <div className="grid two" key={`monthly-dom-${index}`}>
                          <input type="number" min={1} max={31} value={monthlyDaySlots[index]?.day ?? 1} onChange={(event) => setMonthlyDaySlots((current) => {
                            const next = [...current];
                            next[index] = { day: Math.max(1, Math.min(31, Number(event.target.value) || 1)), time: next[index]?.time ?? "09:00" };
                            return next;
                          })} />
                          <input type="time" value={monthlyDaySlots[index]?.time ?? "09:00"} onChange={(event) => setMonthlyDaySlots((current) => {
                            const next = [...current];
                            next[index] = { day: next[index]?.day ?? 1, time: event.target.value };
                            return next;
                          })} />
                        </div>
                      ))
                    : Array.from({ length: runsPerPeriod }).map((_, index) => (
                        <div className="grid two" key={`monthly-ord-${index}`}>
                          <select value={String(monthlyOrdinalSlots[index]?.ordinal ?? 1)} onChange={(event) => setMonthlyOrdinalSlots((current) => {
                            const next = [...current];
                            next[index] = { ordinal: Number(event.target.value), weekday: next[index]?.weekday ?? "monday", time: next[index]?.time ?? "09:00" };
                            return next;
                          })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{["1st","2nd","3rd","4th","5th"][n-1]}</option>)}</select>
                          <select value={monthlyOrdinalSlots[index]?.weekday ?? "monday"} onChange={(event) => setMonthlyOrdinalSlots((current) => {
                            const next = [...current];
                            next[index] = { ordinal: next[index]?.ordinal ?? 1, weekday: event.target.value, time: next[index]?.time ?? "09:00" };
                            return next;
                          })}>{weekdays.map((day) => <option key={day} value={day}>{capitalizeFirst(day)}</option>)}</select>
                          <input type="time" value={monthlyOrdinalSlots[index]?.time ?? "09:00"} style={{ gridColumn: "1 / -1" }} onChange={(event) => setMonthlyOrdinalSlots((current) => {
                            const next = [...current];
                            next[index] = { ordinal: next[index]?.ordinal ?? 1, weekday: next[index]?.weekday ?? "monday", time: event.target.value };
                            return next;
                          })} />
                        </div>
                      ))}
                </div>
              ) : Array.from({ length: runsPerPeriod }).map((_, index) => (
                <input key={`daily-${index}`} type="time" value={dailyTimes[index] ?? "09:00"} onChange={(event) => setDailyTimes((current) => {
                  const next = [...current];
                  next[index] = event.target.value;
                  return next;
                })} />
              )))}
            </div>
          ) : null}
          <div className="grid two">
            <label className="grid">
              <span className="muted">Start at</span>
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
            <legend>Stop rule</legend>
            <div className="grid three">
              <label className="grid">
                <span className="muted">Rule</span>
                <select value={stopRule} onChange={(event) => setStopRule(event.target.value as ScheduleStopRule)}>
                  <option value="never">Never</option>
                  <option value="end_at">End at date</option>
                  <option value="duration">After duration</option>
                </select>
              </label>
              {stopRule === "end_at" ? (
                <label className="grid">
                  <span className="muted">End at</span>
                  <input type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} required />
                </label>
              ) : null}
              {stopRule === "duration" ? (
                <label className="grid">
                  <span className="muted">Duration (hours)</span>
                  <input type="number" min={1} value={durationHours} onChange={(event) => setDurationHours(Math.max(1, Number(event.target.value) || 1))} />
                </label>
              ) : null}
            </div>
          </fieldset>
          <section className="panel" style={{ padding: "12px 14px" }}>
            <div className="grid">
              <span className="muted">Estimated next run</span>
              <strong>{schedulePreview.mode === "automatic" ? "Automatic" : "Manual trigger only"}</strong>
              {schedulePreview.nextRunAt ? (
                <span className="muted">{formatDateTime(schedulePreview.nextRunAt, { timeZone: timezone })}</span>
              ) : null}
              <span className="muted" style={{ fontSize: "12px" }}>{schedulePreview.reason}</span>
            </div>
          </section>
          <fieldset className="field-group">
            <legend>Blackout dates</legend>
            <p className="form-help">Full calendar days (in the schedule timezone) when automatic triggers are skipped. Manual trigger still works on these days.</p>
            <div className="grid two" style={{ marginTop: "8px" }}>
              <label className="grid">
                <span className="muted">Skip date</span>
                <input type="date" value={blackoutDateInput} onChange={(event) => setBlackoutDateInput(event.target.value)} />
              </label>
              <button className="secondary" type="button" onClick={addBlackoutDate} disabled={!blackoutDateInput}>
                Add date
              </button>
            </div>
            {blackoutDates.length ? (
              <div className="pill-list" style={{ marginTop: "8px" }} aria-label="Selected blackout dates">
                {blackoutDates.map((date) => (
                  <span className="chip" key={date}>
                    {date}
                    <button className="pill-remove" type="button" onClick={() => removeBlackoutDate(date)} aria-label={`Remove blackout date ${date}`}>
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
          </fieldset>

          <fieldset className="field-group">
            <legend>Campaign steps <span className="muted" style={{ fontWeight: 400, fontSize: "13px" }}>(required)</span></legend>
            <div className="grid three">
              <label className="grid">
                <span className="muted">Profile</span>
                <select value={stepProfileId} onChange={(event) => setStepProfileId(event.target.value)}>
                  {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                </select>
              </label>
              <label className="grid">
                <span className="muted">Repeat</span>
                <input type="number" min={1} max={100} value={stepRepeatCount} onChange={(event) => setStepRepeatCount(Number(event.target.value))} />
              </label>
              <label className="grid">
                <span className="muted">Spacing (min)</span>
                <input type="number" min={0} value={stepSpacingMinutes} onChange={(event) => setStepSpacingMinutes(Number(event.target.value))} />
              </label>
            </div>
            <button className="secondary" type="button" onClick={addCampaignStep} style={{ marginTop: "8px" }}>+ Add step</button>
            {campaignSteps.length === 0 ? (
              <p className="form-help form-help--required">At least one campaign step is required before saving.</p>
            ) : (
              <div className="responsive-table" style={{ marginTop: "10px" }}>
                <table>
                  <thead>
                    <tr><th>#</th><th>Profile</th><th>Repeat</th><th>Spacing</th><th></th></tr>
                  </thead>
                  <tbody>
                    {campaignSteps.map((step, index) => (
                      <tr key={`${step.profile_id}-${index}`}>
                        <td>{index + 1}</td>
                        <td>{profileById.get(step.profile_id)?.name ?? step.profile_id}</td>
                        <td>{step.repeat_count}×</td>
                        <td>{step.spacing_seconds >= 60 ? `${Math.round(step.spacing_seconds / 60)}m` : step.spacing_seconds > 0 ? `${step.spacing_seconds}s` : "—"}</td>
                        <td>
                          <div style={{ display: "flex", gap: "4px" }}>
                            <button className="secondary small" type="button" disabled={index === 0} onClick={() => moveCampaignStep(index, -1)} aria-label="Move step up">↑</button>
                            <button className="secondary small" type="button" disabled={index === campaignSteps.length - 1} onClick={() => moveCampaignStep(index, 1)} aria-label="Move step down">↓</button>
                            <button className="secondary small" type="button" onClick={() => setCampaignSteps((current) => current.filter((_, i) => i !== index))}>Remove</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </fieldset>

          <div className="row-actions">
            <button disabled={busy || !profiles.length}>{busy ? "Saving…" : editingScheduleId ? "Save changes" : "Create schedule"}</button>
            <button className="secondary" type="button" disabled={busy} onClick={cancelEditSchedule}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
