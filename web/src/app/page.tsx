"use client";

import { useRouter } from "next/navigation";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { CollapsibleSection } from "../components/CollapsibleSection";
import { Pagination } from "../components/Pagination";
import { ThemeToggle } from "../components/ThemeToggle";
import LoginForm from "../components/LoginForm";
import UserProfile from "../components/UserProfile";
import AuthGuard from "../components/AuthGuard";
import { useAuth } from "../contexts/AuthContext";
import { useRole } from "../contexts/RoleContext";
import AdminDashboard from "../components/AdminDashboard";
import {
  ApiRequestError,
  cancelRun,
  createRun,
  deleteRun,
  fetchDashboardSummary,
  fetchFlows,
  fetchHealth,
  fetchRunArtifactEvents,
  fetchRunArtifactText,
  fetchRunLog,
  fetchRunMetrics,
  fetchRuns,
  type DashboardSummary,
  type RunArtifactResponse,
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
import { formatRelativeTime, formatRunDuration } from "../lib/time-format";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Architecture content (from ARCHITECTURE.md)
const ARCHITECTURE_CONTENT = `# Complete Order Flow Simulator

## Overview

\`simulate\` supports two execution styles plus friendly presets:

| Mode | Purpose |
|---|---|
| \`load\` | Randomised multi-actor traffic simulation for churn, failure hunting, and live platform smoke tests |
| \`trace\` | Deterministic proof-oriented scenarios for \`completed\`, \`rejected\`, \`cancelled\`, and optional \`auto_cancel\` |

| Friendly preset | Purpose |
|---|---|
| \`doctor\` | Daily production health check: app probes, store setup/dashboard, menu gates, payments, store actions, robot completion, receipt/review/reorder |
| \`full\` | Broadest suite including new-user setup and coupon scenarios |
| \`receipt-review\` | Completed order plus receipt, review, and reorder probes |
| \`store-dashboard\` | Store orders, statistics, and top-customer probes |

Each simulator is **fully self-contained** — it owns its own auth, data seeding, and
active websocket connection. There are no shared queues between simulators.

## Component Responsibilities

| Component | Responsibility |
|---|---|
| \`__main__\` | CLI parsing, config validation, launches sims, passive websocket observer, report writing |
| \`user_sim\` | User auth (OTP/cached token), menu/location seeding, active WS \`/ws/soc/<user_id>/\`, order placement, payment, cancellation |
| \`store_sim\` | Store auth (product auth + store login), active WS \`/ws/soc/store_<id>/\`, accept/reject, payment wait, mark ready |
| \`robot_sim\` | Store token acquisition (independent), active WS \`/ws/soc/store_<id>/\`, delivery lifecycle to completed |
| \`trace_runner\` | Deterministic scenarios; bootstraps own auth/fixtures, uses polling for verification |
| \`websocket_observer\` | Passive user/store/stats socket observation for report validation |
| \`transport\` | Masked request/response proof, auth proof, latency capture |
| \`reporting\` | \`events.json\`, \`report.md\`, and \`story.md\` artifacts |
| \`run_plan\` | JSON run-plan parsing and validation for operator input |
| \`app_probes\` | Real-app API probes outside the core order mutation |
| \`post_order_actions\` | Receipt, review, and reorder probes after completed orders |
| \`health\` | Daily doctor summary, latency, bottleneck, websocket, and issue metrics |

## Status Ownership

| Owner | Status/action | Endpoint |
|---|---|---|
| User | \`pending\` order creation | \`POST /v1/core/orders/\` |
| Store | \`payment_processing\` or \`rejected\` | \`PATCH /v1/core/orders/?order_id=<id>\` |
| User | \`cancelled\` while still pending | \`PATCH /v1/core/orders/?order_id=<id>\` |
| Backend | \`order_processing\` | Stripe webhook or free-order confirmation |
| Store | \`ready\` | \`PATCH /v1/core/orders/?order_id=<id>\` |
| Robot | \`enroute_pickup\` to \`completed\` | \`PATCH /v1/core/orders/?order_id=<id>\` |

The simulator never patches \`order_processing\`; it waits for the backend to prove payment completion.

## Trace Mode

Supported scenarios:

| Scenario | Intent |
|---|---|
| \`completed\` | Full happy path from order placement through robot completion |
| \`rejected\` | Store rejects before payment |
| \`cancelled\` | Customer cancels while the order is still pending |
| \`auto_cancel\` | Diagnostic check for backend timeout cancellation without store action |
| \`app_bootstrap\` | Probe config, product auth, pricing, saved cards, coupons, active user orders |
| \`store_dashboard\` | Probe store orders, store statistics, and top customers |
| \`receipt_review_reorder\` | Full completed order plus receipt generation, review submission, and reorder fetch |

Timing profiles:

| Profile | Intent |
|---|---|
| \`fast\` | Minimal artificial delays for proof runs and CI-like validation |
| \`realistic\` | Human-like store and robot timing |

## Auth And Token Reuse

Each simulator handles its own authentication inside its \`run()\` entrypoint (or \`bootstrap_auth()\` for trace mode).

**User auth** (\`user_sim\`):
1. If \`USER_LASTMILE_TOKEN\` and \`USER_ID\` exist, validates via \`GET /v1/core/orders/?user=<USER_ID>\`.
2. If validation succeeds, reuses the cached token.
3. If rejected (\`401/403\`), clears cache, runs OTP flow, persists fresh token + user_id to \`.env\`.

**Store auth** (\`store_sim\`):
- Reuses \`STORE_LASTMILE_TOKEN\` from \`.env\`, or fetches via product-auth endpoint.
- Fetches store profile via \`/v1/entities/store/login\` and sets \`SUBENTITY_ID\`.

**Robot auth** (\`robot_sim\`):
- Independently acquires the same store token (env or product-auth).
- No shared token provider — each sim authenticates on its own.

Auth proof (masked header, scheme, source, fingerprint) is recorded in every case.

## Websocket Validation

The observer connects before scenario or load actors start:

| Stream | URL |
|---|---|
| User orders | \`/ws/soc/<user_id>/\` |
| Store orders | \`/ws/soc/store_<store_id>/\` |
| Store stats | \`/ws/soc/store_statistics_<store_id>/\` |

Messages are decoded the same way the Flutter apps consume them: outer JSON first, then \`payload["message"]\` if it contains nested JSON. Every expected status change is matched against websocket traffic by order id/reference and status, with latency attached to the originating event. Missing or late messages are recorded as findings.

## Run Artifacts

Each run writes:

\`\`\`
simulate/runs/<timestamp>/
  events.json
  report.md
  story.md
\`\`\`

Artifact roles:

| File | Contents |
|---|---|
| \`events.json\` | Full source-of-truth ledger for auth, fixture lookup, HTTP traffic, websocket traffic, delays, status proofs, and issues |
| \`report.md\` | Technical proof document with scenario verdicts, websocket assertions, developer findings, and full per-step trace |
| \`story.md\` | Layman-friendly explanation of what happened and what went wrong |

\`report.md\` starts with a daily doctor summary before the technical trace:

| Section | Contents |
|---|---|
| Daily Doctor Summary | Verdict, duration, scenario/order/API/websocket/issue counts |
| Graphical Summary | Plain-text bars for quick scanning in any markdown viewer |
| Bottlenecks | Slowest endpoints grouped by method/path with average, p95, and max latency |
| Scenario Verdicts | Expected vs actual result per scenario |
| Websocket Assertions | Expected status messages matched to observed socket traffic |
| Technical Trace | Full per-event proof with auth fingerprints, payload previews, and latency |

## JSON Run Plan

The public input is a JSON file. \`sim_actors.json\` remains valid, and richer plans can add GPS to each user:

\`\`\`json
{
  "defaults": {
    "user_phone": "+2348166675609",
    "store_id": "FZY_586940",
    "location_radius": 1,
    "coupon_id": null
  },
  "users": [
    {
      "phone": "+2349077777740",
      "role": "returning",
      "lat": 35.15494521954757,
      "lng": 136.9663666561246,
      "orders": 3
    }
  ],
  "stores": [
    {
      "store_id": "FZY_586940",
      "subentity_id": 6,
      "currency": "jpy",
      "lat": 35.15494521954757,
      "lng": 136.9663666561246
    }
  ]
}
\`\`\`

Use \`--strict-plan\` when operators want the simulator to reject users without GPS coordinates or stores without IDs.`;

// Simulator Guide content (from SIMULATOR_GUIDE.md)
const SIMULATOR_GUIDE_CONTENT = `# Fainzy Simulator Guidebook

This simulator is a daily doctor for the ordering platform. It simulates user app, store app, and robot behavior; continuously checks HTTP and websocket paths; and writes operator-friendly reports plus full technical evidence.

## 1) Inputs and Outputs

Required operator inputs:

- \`.env\` for environment URLs and secrets.
- A plan JSON (default \`sim_actors.json\`) with users (phone + delivery GPS) and stores (\`store_id\`, optional metadata).

Generated artifacts per run:

- \`runs/<timestamp>/events.json\`: complete event ledger.
- \`runs/<timestamp>/report.md\`: summary + bottlenecks + tabled findings + technical trace.
- \`runs/<timestamp>/story.md\`: narrative scenario summary.

## 2) Validated Command Matrix

All rows below are supported flow presets exposed by CLI help.

| Flow Preset | Resolved Mode/Suite/Scenarios | What It Tests | Required Prerequisites | Key Optional Flags | Artifacts |
| --- | --- | --- | --- | --- | --- |
| \`doctor\` | \`trace\` + suite \`doctor\` | Daily core health: app bootstrap, setup/dashboard, menus, paid flow, accept/reject, robot complete, receipt/review/reorder | Valid user/store in plan; Stripe key for paid path unless paid path is converted to free by coupon coverage | \`--timing\`, \`--store\`, \`--phone\`, \`--plan\`, \`--strict-plan\`, \`--no-auto-provision\`, \`--skip-app-probes\`, \`--skip-store-dashboard-probes\` | \`events.json\`, \`report.md\`, \`story.md\` |
| \`full\` | \`trace\` + suite \`full\` | Broadest suite: includes new-user and coupon variants in addition to doctor coverage | Same as \`doctor\`, plus coupon availability for coupon scenarios (or auto-select coupon enabled) | Same as \`doctor\` | Same |
| \`audit\` | \`trace\` + suite \`audit\` | Full app/store/menus/payments/post-order verification with scenario granularity | Same as \`full\` | Same as \`doctor\` | Same |
| \`payments\` | \`trace\` + suite \`payments\` | Paid no-coupon, paid with coupon, free with coupon payment routing | Stripe for paid branches; coupon for coupon branches (or auto-select coupon) | \`--timing\`, \`--phone\`, \`--store\`, \`--no-auto-provision\` | Same |
| \`menus\` | \`trace\` + suite \`menus\` | Menu availability behavior (available/unavailable/sold-out/store-closed) | Valid fixtures (store + menu); auto-provision can repair missing setup/menu | \`--timing\`, \`--store\`, \`--no-auto-provision\` | Same |
| \`new-user\` | \`trace\` + scenario \`new_user_setup\` | OTP + create-user path and first-time setup assertions | Phone in plan not fully onboarded (or backend forcing create path) | \`--phone\`, \`--timing\`, \`--store\`, \`--no-auto-provision\` | Same |
| \`paid-no-coupon\` | \`trace\` + scenario \`returning_paid_no_coupon\` | Standard paid checkout route | Stripe key and valid fixtures | \`--timing\`, \`--phone\`, \`--store\`, \`--post-order-actions\` | Same |
| \`paid-coupon\` | \`trace\` + scenario \`returning_paid_with_coupon\` | Coupon checkout path with paid endpoint unless coupon fully covers total | Coupon configured/available (or auto-select coupon enabled) | \`--timing\`, \`--phone\`, \`--store\`, \`--no-auto-provision\` | Same |
| \`free-coupon\` | \`trace\` + scenario \`returning_free_with_coupon\` | Coupon path targeting free-order behavior | Coupon configured/available (or auto-select coupon enabled) | \`--timing\`, \`--phone\`, \`--store\`, \`--no-auto-provision\` | Same |
| \`store-setup\` | \`trace\` + scenario \`store_first_setup\` | Store setup/profile patch, store open/restore, category/menu readiness | Store auth must succeed | \`--store\`, \`--timing\`, \`--no-auto-provision\` | Same |
| \`store-dashboard\` | \`trace\` + scenario \`store_dashboard\` | Store-side probes: orders, statistics, top customers | Store auth must succeed | \`--store\`, \`--timing\`, \`--skip-store-dashboard-probes\` | Same |
| \`store-accept\` | \`trace\` + scenario \`store_accept\` | One completed order framed as accept behavior | Stripe key unless payment route becomes free | \`--timing\`, \`--store\`, \`--phone\` | Same |
| \`store-reject\` | \`trace\` + scenario \`store_reject\` | One rejected order framed as reject behavior | Valid fixtures | \`--timing\`, \`--store\`, \`--phone\` | Same |
| \`robot-complete\` | \`trace\` + scenario \`robot_complete\` | End-to-end robot status progression to completed | Valid fixtures; Stripe key unless free payment path applies | \`--timing\`, \`--store\`, \`--phone\` | Same |
| \`receipt-review\` | \`trace\` + scenario \`receipt_review_reorder\` | Completed order + receipt + review + reorder actions | Completed order path must succeed | \`--timing\`, \`--store\`, \`--phone\`, \`--post-order-actions\` | Same |
| \`load\` | \`load\` | Concurrent users/stores/robots, repeated order traffic, performance and stability | Plan with usable users/stores; Stripe for paid runs | \`--users\`, \`--orders\`, \`--interval\`, \`--reject\`, \`--continuous\`, \`--all-users\`, \`--store\`, \`--phone\`, \`--no-auto-provision\` | Same |

## 3) Quick Start Commands

Daily recommended run:

\`\`\`bash
python3 -m simulate doctor --plan sim_actors.json --timing fast
\`\`\`

Broad audit:

\`\`\`bash
python3 -m simulate full --plan sim_actors.json --timing fast
\`\`\`

High-concurrency load:

\`\`\`bash
python3 -m simulate load --plan sim_actors.json --all-users --users 10 --orders 100 --interval 3 --reject 0.1
\`\`\`

## 4) Common Failures

- \`No active delivery locations were returned\`: adjust user delivery GPS (\`SIM_LAT/SIM_LNG\` or plan user GPS) and radius.
- \`No available priced menu items found\`: enable auto-provision or check store/menu endpoints.
- \`No usable store candidate could serve this simulation\`: every candidate store failed login/setup/fixture bootstrap.
- \`SIM_COUPON_ID is required for coupon flows\`: configure coupon or enable auto-select coupon.
- \`STRIPE_SECRET_KEY is required\`: paid flow selected without Stripe key.

## 5) Environment Setup

Key environment variables:

- \`USER_PHONE_NUMBER\`: Your phone number for OTP
- \`STORE_ID\`: Store ID to test with
- \`STRIPE_SECRET_KEY\`: For payment testing
- \`LASTMILE_BASE_URL\`: Backend API URL
- \`FAINZY_BASE_URL\`: Frontend URL

The simulator handles authentication automatically and caches tokens in \`.env\` for subsequent runs.`;

type GuideTab = "flows" | "commands" | "flags" | "plan" | "rules" | "failures" | "architecture" | "guide";
type InspectorTab = "summary" | "report" | "story" | "events";
type EventRow = Record<string, unknown>;

const RUNS_PER_PAGE = 20;
const REPORT_PAGE_SIZE = 500;
const EVENTS_PAGE_SIZE = 100;
type UiError = {
  source: string;
  message: string;
  details?: string | null;
};

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

function makeUiError(
  err: unknown,
  source: string,
  fallback: string,
  backendHealthy: boolean | null
): UiError {
  if (err instanceof ApiRequestError) {
    if (source.startsWith("artifact-") && err.status === 504) {
      return {
        source,
        message: backendHealthy
          ? "Artifact request timed out while backend is reachable. Retry or reduce request size."
          : "Artifact request timed out and backend health is currently unavailable.",
        details: err.details
      };
    }
    return {
      source,
      message: err.message || fallback,
      details: err.details
    };
  }
  if (err instanceof Error) {
    return { source, message: err.message || fallback };
  }
  return { source, message: fallback };
}

const MarkdownPane = memo(function MarkdownPane({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>;
});

const CollapseButton = memo(function CollapseButton({ 
  isExpanded, 
  onToggle, 
  title 
}: { 
  isExpanded: boolean; 
  onToggle: () => void; 
  title: string;
}) {
  return (
    <button
      className="secondary"
      onClick={onToggle}
      style={{ 
        width: "auto", 
        display: "flex", 
        alignItems: "center", 
        gap: 8,
        padding: "6px 12px",
        fontSize: "14px"
      }}
    >
      <span 
        style={{ 
          display: "inline-block", 
          transition: "transform 0.2s",
          transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)"
        }}
      >
        ▼
      </span>
      {isExpanded ? `Collapse ${title}` : `Expand ${title}`}
    </button>
  );
});

export default function App() {
  const { user, isLoading, isAuthenticated } = useAuth();
  const { canCreateRuns, canManageUsers, isAdmin } = useRole();
  const [flows, setFlows] = useState<string[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [summary, setSummary] = useState<DashboardSummary>(EMPTY_SUMMARY);
  const router = useRouter();
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
  const [error, setError] = useState<UiError | null>(null);
  const [deleteConfirmRun, setDeleteConfirmRun] = useState<RunRow | null>(null);

  // Collapsible section states
  const [isStartRunExpanded, setIsStartRunExpanded] = useState(true);
  const [isLiveConsoleExpanded, setIsLiveConsoleExpanded] = useState(true);
  const [isFlowPlannerExpanded, setIsFlowPlannerExpanded] = useState(false);
  const [isRecentRunsExpanded, setIsRecentRunsExpanded] = useState(true);
  const [isStatisticsExpanded, setIsStatisticsExpanded] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const backendHealthyRef = useRef<boolean | null>(null);

  useEffect(() => {
    backendHealthyRef.current = backendHealthy;
  }, [backendHealthy]);

  function clearErrorForSource(source: string): void {
    setError((current) => (current?.source === source ? null : current));
  }

  function setErrorForSource(source: string, err: unknown, fallback: string): void {
    setError(makeUiError(err, source, fallback, backendHealthyRef.current));
  }

  useEffect(() => {
    fetchFlows()
      .then((payload) => {
        setFlows(payload);
        clearErrorForSource("flows");
      })
      .catch((err: unknown) => setErrorForSource("flows", err, "Failed to load simulator flows."));
  }, []);

  useEffect(() => {
    const refreshHealth = () => {
      fetchHealth()
        .then(() => {
          setBackendHealthy(true);
          clearErrorForSource("healthz");
        })
        .catch((err: unknown) => {
          setBackendHealthy(false);
          setErrorForSource("healthz", err, "Backend API is unavailable.");
        });
    };
    refreshHealth();
    const timer = window.setInterval(refreshHealth, 10000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const refreshRunsAndSummary = () => {
      Promise.all([fetchRuns(RUNS_PER_PAGE, runsOffset), fetchDashboardSummary()])
        .then(([runsPayload, summaryPayload]) => {
          setRuns(runsPayload.runs);
          setRunsTotal(runsPayload.total);
          setSummary(summaryPayload);
          setBackendHealthy(true);
          clearErrorForSource("runs-summary");
          if (!selectedRunId && runsPayload.runs[0]) {
            setSelectedRunId(runsPayload.runs[0].id);
          }
        })
        .catch((err: unknown) =>
          setErrorForSource("runs-summary", err, "Failed to refresh runs and dashboard summary.")
        );
    };
    refreshRunsAndSummary();
    const timer = window.setInterval(refreshRunsAndSummary, 5000);
    return () => window.clearInterval(timer);
  }, [selectedRunId, runsOffset]);

  useEffect(() => {
    if (!selectedRunId) {
      setLogText("");
      return;
    }
    const status = (runs.find((run) => run.id === selectedRunId)?.status || "").toLowerCase();
    const shouldPoll = isActiveStatus(status);
    const refreshLog = () => {
      fetchRunLog(selectedRunId)
        .then((payload) => {
          setLogText(payload.log);
          clearErrorForSource("run-log");
        })
        .catch((err: unknown) => setErrorForSource("run-log", err, "Failed to load run log."));
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
          clearErrorForSource("run-metrics");
        })
        .catch((err: unknown) => setErrorForSource("run-metrics", err, "Failed to load run metrics."))
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
        clearErrorForSource("artifact-report");
      })
      .catch((err: unknown) => setErrorForSource("artifact-report", err, "Failed to load report artifact."))
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
        clearErrorForSource("artifact-story");
      })
      .catch((err: unknown) => setErrorForSource("artifact-story", err, "Failed to load story artifact."))
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
          clearErrorForSource("artifact-events");
        })
        .catch((err: unknown) => setErrorForSource("artifact-events", err, "Failed to load events artifact."))
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
    clearErrorForSource("create-run");
    setIsSubmitting(true);
    try {
      const created = await createRun({
        ...form,
        store_id: form.store_id || undefined,
        phone: form.phone || undefined
      });
      setSelectedRunId(created.id);
      const [runsPayload, summaryPayload] = await Promise.all([fetchRuns(), fetchDashboardSummary()]);
      setRuns(runsPayload.runs);
      setSummary(summaryPayload);
      clearErrorForSource("runs-summary");
    } catch (err) {
      setErrorForSource("create-run", err, "Failed to start run.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function onCancelRun(runId: number) {
    clearErrorForSource("cancel-run");
    try {
      await cancelRun(runId);
      const [runsPayload, summaryPayload] = await Promise.all([fetchRuns(), fetchDashboardSummary()]);
      setRuns(runsPayload.runs);
      setSummary(summaryPayload);
      clearErrorForSource("runs-summary");
    } catch (err) {
      setErrorForSource("cancel-run", err, "Failed to cancel run.");
    }
  }

  async function onDeleteRun(runId: number) {
    clearErrorForSource("delete-run");
    try {
      const result = await deleteRun(runId);
      console.log(`Deleted run ${runId}:`, result);
      const [runsPayload, summaryPayload] = await Promise.all([fetchRuns(), fetchDashboardSummary()]);
      setRuns(runsPayload.runs);
      setSummary(summaryPayload);
      clearErrorForSource("runs-summary");
      
      // If the deleted run was selected, clear the selection
      if (selectedRun?.id === runId) {
        setSelectedRunId(null);
      }
    } catch (err) {
      setErrorForSource("delete-run", err, "Failed to delete run.");
    }
  }

  const logLines = logText.split("\n").filter((line) => line.length > 0);

  return (
    <AuthGuard>
      <main className="grid" style={{ gap: 16 }}>
        <div className="panel grid" style={{ gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h1 style={{ margin: 0 }}>Fainzy Simulator Web Control</h1>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <ThemeToggle />
              <UserProfile />
            </div>
          </div>
          <div className="muted">
            Run simulator flows, monitor progress, inspect stories/reports/events, and track system health.
          </div>
          <div className="muted">
            API health:{" "}
            {backendHealthy === null
              ? "checking..."
              : backendHealthy
                ? "reachable"
                : "unavailable"}
          </div>
        </div>

        {error ? (
          <div className="panel error-banner">
            <div>{error.message}</div>
            {error.details ? (
              <details>
                <summary>Details</summary>
                <pre className="error-details">
                  <code>{error.details}</code>
                </pre>
              </details>
            ) : null}
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

        {canCreateRuns ? (
            <CollapsibleSection defaultExpanded={true}>
              <div className="grid two" style={{ alignItems: "start" }}>
              <div className="panel grid" style={{ gap: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <h2 style={{ margin: 0 }}>Start Run</h2>
                  <CollapseButton 
                    isExpanded={isStartRunExpanded} 
                    onToggle={() => setIsStartRunExpanded(!isStartRunExpanded)}
                    title="Start Run"
                  />
                </div>
                {isStartRunExpanded && (
                  <>
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
                        <textarea
                          value={form.plan}
                          onChange={(event) => setForm((prev) => ({ ...prev, plan: event.target.value }))}
                          placeholder="Enter simulation plan..."
                          rows={3}
                        />
                      </label>
                    </div>
                    <div className="grid three">
                      {/* <label>
                        Mode
                        <select
                          value={form.mode}
                          onChange={(event) =>
                            setForm((prev) => ({ ...prev, mode: event.target.value as "trace" | "load" }))
                          }
                        >
                          <option value="">Default</option>
                          <option value="trace">trace</option>
                          <option value="load">load</option>
                        </select>
                      </label> */}
                      <label>
                        Store ID
                        <input
                          type="text"
                          value={form.store_id}
                          onChange={(event) => setForm((prev) => ({ ...prev, store_id: event.target.value }))}
                          placeholder="Optional: store ID"
                        />
                      </label>
                      <label>
                        Phone
                        <input
                          type="text"
                          value={form.phone}
                          onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                          placeholder="Optional: phone number"
                        />
                      </label>
                    </div>
                    <div className="grid three">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={form.all_users}
                          onChange={(event) => setForm((prev) => ({ ...prev, all_users: event.target.checked }))}
                        />
                        All Users
                      </label>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={form.no_auto_provision}
                          onChange={(event) => setForm((prev) => ({ ...prev, no_auto_provision: event.target.checked }))}
                        />
                        No Auto Provision
                      </label>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={form.post_order_actions || false}
                          onChange={(event) => setForm((prev) => ({ ...prev, post_order_actions: event.target.checked }))}
                        />
                        Post-Order Actions
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
                  </>
                )}
              </div>
        <div className="panel grid" style={{ gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <h2 style={{ margin: 0 }}>Live Console</h2>
            <CollapseButton 
              isExpanded={isLiveConsoleExpanded} 
              onToggle={() => setIsLiveConsoleExpanded(!isLiveConsoleExpanded)}
              title="Live Console"
            />
          </div>
          {isLiveConsoleExpanded && (
            <>
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
            </>
          )}
        </div>
              </div>
            </CollapsibleSection>
        ) : (
          <div className="panel grid" style={{ gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <h2 style={{ margin: 0 }}>Start Run</h2>
            </div>
            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-secondary)' }}>
              You don't have permission to create runs. Contact an administrator for access.
            </div>
          </div>
        )}


        <CollapsibleSection title="Flow Planner & Command Guide" defaultExpanded={false}>
          <div className="panel grid" style={{ gap: 12 }}>
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
              ["failures", "Failure Hints"],
              ["architecture", "Architecture"],
              ["guide", "Simulator Guide"]
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
        {guideTab === "architecture" ? (
          <div className="artifact markdown-view">
            <MarkdownPane text={ARCHITECTURE_CONTENT} />
          </div>
        ) : null}
        {guideTab === "guide" ? (
          <div className="artifact markdown-view">
            <MarkdownPane text={SIMULATOR_GUIDE_CONTENT} />
          </div>
        ) : null}
        </div>
        </CollapsibleSection>

        <CollapsibleSection title="Recent Runs" defaultExpanded={true}>
        <div className="panel">
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
                onClick={() => router.push(`/runs/${run.id}`)}
                style={{
                  cursor: "pointer"
                }}
              >
                <td>{run.id}</td>
                <td>{run.status}</td>
                <td>{run.flow}</td>
                <td>
                  <div style={{ fontWeight: 500 }}>{run.store_id || "-"}</div>
                  {run.store_name && (
                    <div style={{ fontSize: "11px", opacity: 0.7, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "120px" }}>
                      {run.store_name}
                    </div>
                  )}
                  {run.store_phone && (
                    <div style={{ fontSize: "10px", opacity: 0.6 }}>
                      {run.store_phone}
                    </div>
                  )}
                </td>
                <td>
                  <div style={{ fontWeight: 500 }}>{run.phone || "-"}</div>
                  {run.user_name && (
                    <div style={{ fontSize: "11px", opacity: 0.7, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "120px" }}>
                      {run.user_name}
                    </div>
                  )}
                </td>
                <td>{run.created_at}</td>
                <td>{run.exit_code ?? "-"}</td>
                <td>
                  <div className="row-actions">
                    <button className="secondary small" onClick={(e) => { e.stopPropagation(); router.push(`/runs/${run.id}`); }}>
                      View
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
                    <button
                      className="secondary small"
                      disabled={isActiveStatus(run.status)}
                      onClick={(event) => {
                        event.stopPropagation();
                        setDeleteConfirmRun(run);
                      }}
                      style={{ marginLeft: "4px" }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pagination
          total={runsTotal}
          offset={runsOffset}
          limit={RUNS_PER_PAGE}
          onPageChange={(newOffset: number) => setRunsOffset(newOffset)}
        />
        </div>
        </CollapsibleSection>

        <CollapsibleSection title="Statistics" defaultExpanded={false}>
        <div className="grid two" style={{ alignItems: "start" }}>
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
        </div>
        </CollapsibleSection>

        {/* Admin Dashboard - Only visible to admins */}
        {isAdmin && (
          <CollapsibleSection defaultExpanded={false}>
            <div className="panel grid" style={{ gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Admin Dashboard</h2>
              </div>
              <AdminDashboard />
            </div>
          </CollapsibleSection>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirmRun && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}>
            <div style={{
              backgroundColor: 'var(--bg-secondary)',
              padding: '24px',
              borderRadius: '8px',
              width: '400px',
              border: '1px solid var(--border-primary)',
            }}>
              <h3 style={{ margin: '0 0 12px 0', color: 'var(--text-primary)' }}>Confirm Delete</h3>
              <p style={{ margin: '0 0 20px 0', color: 'var(--text-secondary)', fontSize: '14px' }}>
                Are you sure you want to delete run #{deleteConfirmRun.id}? This will permanently remove all associated files and cannot be undone.
              </p>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => {
                    onDeleteRun(deleteConfirmRun.id);
                    setDeleteConfirmRun(null);
                  }}
                  style={{
                    flex: 1,
                    padding: '10px 16px',
                    backgroundColor: 'var(--method-delete-bg)',
                    color: 'var(--method-delete-text)',
                    border: '1px solid var(--method-delete-border)',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 500,
                  }}
                >
                  Delete
                </button>
                <button
                  onClick={() => setDeleteConfirmRun(null)}
                  className="secondary"
                  style={{
                    flex: 1,
                    padding: '10px 16px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 500,
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </AuthGuard>
  );
}
