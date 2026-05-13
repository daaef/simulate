"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CollapsibleSection } from "../../../components/CollapsibleSection";
import { ThemeToggle } from "../../../components/ThemeToggle";
import UserProfile from "../../../components/UserProfile";
import { useRole } from "../../../contexts/RoleContext";
import AdminDashboard from "../../../components/AdminDashboard";
import DeleteRunModal from "../../../components/runs/DeleteRunModal";
import FlowPlannerGuide from "../../../components/runs/FlowPlannerGuide";
import RecentRunsTable from "../../../components/runs/RecentRunsTable";
import RunLaunchPanel from "../../../components/runs/RunLaunchPanel";
import RunLiveConsole from "../../../components/runs/RunLiveConsole";
import RunProfilesPanel from "../../../components/runs/RunProfilesPanel";
import RunStatistics from "../../../components/runs/RunStatistics";
import {
  ApiRequestError,
  cancelRun,
  createRunProfile,
  createRun,
  deleteRunProfile,
  deleteRun,
  fetchDashboardSummary,
  fetchFlows,
  fetchHealth,
  fetchRunLog,
  fetchRunProfiles,
  fetchRuns,
  fetchSimulationPlans,
  launchRunProfile,
  updateRunProfile,
  type DashboardSummary,
  type FlowCapability,
  type FlowsResponse,
  type RunCreateRequest,
  type RunProfile,
  type RunRow,
  type SimulationPlan
} from "../../../lib/api";

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

const RUNS_PER_PAGE = 20;
type UiError = {
  source: string;
  message: string;
  details?: string | null;
};

const DEFAULT_FORM: RunCreateRequest = {
  flow: "doctor",
  plan: "sim_actors.json",
  timing: "fast",
  mode: undefined,
  suite: undefined,
  scenarios: [],
  store_id: "",
  phone: "",
  all_users: false,
  strict_plan: false,
  skip_app_probes: false,
  skip_store_dashboard_probes: false,
  no_auto_provision: false,
  enforce_websocket_gates: false,
  post_order_actions: false,
  users: undefined,
  orders: undefined,
  interval: undefined,
  reject: undefined,
  continuous: false,
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

export default function App() {
  const { canCreateRuns, isAdmin } = useRole();
  const [flows, setFlows] = useState<string[]>([]);
  const [flowCapabilities, setFlowCapabilities] = useState<Record<string, FlowCapability>>({});
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [summary, setSummary] = useState<DashboardSummary>(EMPTY_SUMMARY);
  const router = useRouter();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [guideTab, setGuideTab] = useState<GuideTab>("flows");
  const [logText, setLogText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isProfileSubmitting, setIsProfileSubmitting] = useState(false);
  const [isProfileLaunching, setIsProfileLaunching] = useState(false);
  const [form, setForm] = useState<RunCreateRequest>(DEFAULT_FORM);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [simulationPlans, setSimulationPlans] = useState<SimulationPlan[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [profileName, setProfileName] = useState("");
  const [profileDescription, setProfileDescription] = useState("");
  const [error, setError] = useState<UiError | null>(null);
  const [deleteConfirmRun, setDeleteConfirmRun] = useState<RunRow | null>(null);

  const [isStartRunExpanded, setIsStartRunExpanded] = useState(true);
  const [isLiveConsoleExpanded, setIsLiveConsoleExpanded] = useState(true);
  const profilesSectionRef = useRef<HTMLDivElement | null>(null);
  const profileNameInputRef = useRef<HTMLInputElement | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const backendHealthyRef = useRef<boolean | null>(null);
  const allowedPlanPaths = useMemo(
    () => new Set<string>(["sim_actors.json", ...simulationPlans.map((plan) => plan.path)]),
    [simulationPlans]
  );

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
      .then((payload: FlowsResponse) => {
        setFlows(payload.flows);
        setFlowCapabilities(payload.capabilities || {});
        clearErrorForSource("flows");
      })
      .catch((err: unknown) => setErrorForSource("flows", err, "Failed to load simulator flows."));
  }, []);

  const activeFlowCapability = useMemo(() => {
    return flowCapabilities[form.flow] || null;
  }, [flowCapabilities, form.flow]);

  const resolvedMode = useMemo<"trace" | "load">(() => {
    if (form.mode) return form.mode;
    const fromCapability = activeFlowCapability?.resolved_mode;
    return fromCapability === "load" ? "load" : "trace";
  }, [form.mode, activeFlowCapability]);

  const modeValidationError = useMemo(() => {
    if (resolvedMode === "trace") {
      if (form.continuous) return "Continuous is only valid in load mode.";
      if (
        form.users !== undefined ||
        form.orders !== undefined ||
        form.interval !== undefined ||
        form.reject !== undefined
      ) {
        return "users/orders/interval/reject are only valid in load mode.";
      }
    }
    if (resolvedMode === "load" && ((form.scenarios?.length || 0) > 0 || (form.suite && form.suite.trim()))) {
      return "suite/scenarios are only valid in trace mode.";
    }
    if (form.reject !== undefined && (form.reject < 0 || form.reject > 1)) {
      return "Reject rate must be between 0 and 1.";
    }
    if (form.users !== undefined && form.users < 1) return "Users must be >= 1.";
    if (form.orders !== undefined && form.orders < 1) return "Orders must be >= 1.";
    return null;
  }, [resolvedMode, form]);

  useEffect(() => {
    fetchRunProfiles()
      .then((payload) => {
        setProfiles(payload);
        clearErrorForSource("run-profiles");
      })
      .catch((err: unknown) => setErrorForSource("run-profiles", err, "Failed to load run profiles."));
  }, []);

  useEffect(() => {
    if (!canCreateRuns) return;
    fetchSimulationPlans()
      .then((payload) => {
        setSimulationPlans(payload);
        clearErrorForSource("simulation-plans");
      })
      .catch((err: unknown) => setErrorForSource("simulation-plans", err, "Failed to load simulation plans."));
  }, [canCreateRuns]);

  useEffect(() => {
    if (allowedPlanPaths.has(form.plan)) return;
    setForm((prev) => ({ ...prev, plan: "sim_actors.json" }));
  }, [allowedPlanPaths, form.plan]);

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

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
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
    if (form.mode) parts.push("--mode", form.mode);
    if (form.suite && form.suite.trim()) parts.push("--suite", form.suite.trim());
    for (const scenario of form.scenarios || []) {
      if (scenario.trim()) parts.push("--scenario", scenario.trim());
    }
    if (form.store_id && form.store_id.trim()) {
      parts.push("--store", form.store_id.trim());
    }
    if (form.phone && form.phone.trim()) {
      parts.push("--phone", form.phone.trim());
    }
    if (form.all_users) parts.push("--all-users");
    if (form.strict_plan) parts.push("--strict-plan");
    if (form.skip_app_probes) parts.push("--skip-app-probes");
    if (form.skip_store_dashboard_probes) parts.push("--skip-store-dashboard-probes");
    if (form.no_auto_provision) parts.push("--no-auto-provision");
    if (form.enforce_websocket_gates) parts.push("--enforce-websocket-gates");
    if (form.post_order_actions) parts.push("--post-order-actions");
    if (form.users !== undefined) parts.push("--users", String(form.users));
    if (form.orders !== undefined) parts.push("--orders", String(form.orders));
    if (form.interval !== undefined) parts.push("--interval", String(form.interval));
    if (form.reject !== undefined) parts.push("--reject", String(form.reject));
    if (form.continuous) parts.push("--continuous");
    if (form.extra_args && form.extra_args.length) {
      parts.push(...form.extra_args);
    }
    return parts.join(" ");
  }, [form]);

  async function onStartRun() {
    clearErrorForSource("create-run");
    setIsSubmitting(true);
    try {
      const created = await createRun({
        ...form,
        suite: form.suite || undefined,
        scenarios: (form.scenarios || []).length ? form.scenarios : undefined,
        store_id: form.store_id || undefined,
        phone: form.phone || undefined,
      });
      setSelectedRunId(created.id);
      const [runsPayload, summaryPayload] = await Promise.all([
        fetchRuns(RUNS_PER_PAGE, runsOffset),
        fetchDashboardSummary()
      ]);
      setRuns(runsPayload.runs);
      setRunsTotal(runsPayload.total);
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
      const [runsPayload, summaryPayload] = await Promise.all([
        fetchRuns(RUNS_PER_PAGE, runsOffset),
        fetchDashboardSummary()
      ]);
      setRuns(runsPayload.runs);
      setRunsTotal(runsPayload.total);
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
      const [runsPayload, summaryPayload] = await Promise.all([
        fetchRuns(RUNS_PER_PAGE, runsOffset),
        fetchDashboardSummary()
      ]);
      setRuns(runsPayload.runs);
      setRunsTotal(runsPayload.total);
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

  async function refreshProfiles() {
    const payload = await fetchRunProfiles();
    setProfiles(payload);
    clearErrorForSource("run-profiles");
  }

  async function onSaveProfile() {
    clearErrorForSource("run-profiles");
    setIsProfileSubmitting(true);
    try {
      const created = await createRunProfile({
        name: profileName.trim(),
        description: profileDescription.trim() || undefined,
        flow: form.flow,
        plan: form.plan,
        timing: form.timing,
        mode: form.mode,
        suite: form.suite || undefined,
        scenarios: form.scenarios || [],
        store_id: form.store_id || undefined,
        phone: form.phone || undefined,
        all_users: form.all_users,
        strict_plan: form.strict_plan,
        skip_app_probes: form.skip_app_probes,
        skip_store_dashboard_probes: form.skip_store_dashboard_probes,
        no_auto_provision: form.no_auto_provision,
        enforce_websocket_gates: form.enforce_websocket_gates,
        post_order_actions: form.post_order_actions,
        users: form.users,
        orders: form.orders,
        interval: form.interval,
        reject: form.reject,
        continuous: form.continuous,
        extra_args: form.extra_args,
      });
      await refreshProfiles();
      setSelectedProfileId(created.id);
    } catch (err) {
      setErrorForSource("run-profiles", err, "Failed to save run profile.");
    } finally {
      setIsProfileSubmitting(false);
    }
  }

  async function onUpdateProfile() {
    if (!selectedProfileId) return;
    clearErrorForSource("run-profiles");
    setIsProfileSubmitting(true);
    try {
      await updateRunProfile(selectedProfileId, {
        name: profileName.trim(),
        description: profileDescription.trim() || undefined,
        flow: form.flow,
        plan: form.plan,
        timing: form.timing,
        mode: form.mode,
        suite: form.suite || undefined,
        scenarios: form.scenarios || [],
        store_id: form.store_id || undefined,
        phone: form.phone || undefined,
        all_users: form.all_users,
        strict_plan: form.strict_plan,
        skip_app_probes: form.skip_app_probes,
        skip_store_dashboard_probes: form.skip_store_dashboard_probes,
        no_auto_provision: form.no_auto_provision,
        enforce_websocket_gates: form.enforce_websocket_gates,
        post_order_actions: form.post_order_actions,
        users: form.users,
        orders: form.orders,
        interval: form.interval,
        reject: form.reject,
        continuous: form.continuous,
        extra_args: form.extra_args,
      });
      await refreshProfiles();
    } catch (err) {
      setErrorForSource("run-profiles", err, "Failed to update run profile.");
    } finally {
      setIsProfileSubmitting(false);
    }
  }

  function onLoadProfile(profile: RunProfile) {
    setSelectedProfileId(profile.id);
    setProfileName(profile.name);
    setProfileDescription(profile.description || "");
    setForm({
      flow: profile.flow,
      plan: profile.plan,
      timing: profile.timing,
      mode: profile.mode || undefined,
      suite: profile.suite || undefined,
      scenarios: profile.scenarios || [],
      store_id: profile.store_id || "",
      phone: profile.phone || "",
      all_users: profile.all_users,
      strict_plan: profile.strict_plan,
      skip_app_probes: profile.skip_app_probes,
      skip_store_dashboard_probes: profile.skip_store_dashboard_probes,
      no_auto_provision: profile.no_auto_provision,
      enforce_websocket_gates: profile.enforce_websocket_gates,
      post_order_actions: profile.post_order_actions || false,
      users: profile.users ?? undefined,
      orders: profile.orders ?? undefined,
      interval: profile.interval ?? undefined,
      reject: profile.reject ?? undefined,
      continuous: profile.continuous,
      extra_args: profile.extra_args,
    });
  }

  async function onLaunchProfile(profileId: number) {
    clearErrorForSource("run-profiles");
    setIsProfileLaunching(true);
    try {
      const payload = await launchRunProfile(profileId);
      setSelectedRunId(payload.run.id);
      const [runsPayload, summaryPayload] = await Promise.all([
        fetchRuns(RUNS_PER_PAGE, runsOffset),
        fetchDashboardSummary(),
      ]);
      setRuns(runsPayload.runs);
      setRunsTotal(runsPayload.total);
      setSummary(summaryPayload);
    } catch (err) {
      setErrorForSource("run-profiles", err, "Failed to launch run profile.");
    } finally {
      setIsProfileLaunching(false);
    }
  }

  async function onDeleteProfile(profileId: number) {
    clearErrorForSource("run-profiles");
    try {
      await deleteRunProfile(profileId);
      if (selectedProfileId === profileId) {
        setSelectedProfileId(null);
      }
      await refreshProfiles();
    } catch (err) {
      setErrorForSource("run-profiles", err, "Failed to delete run profile.");
    }
  }

  const logLines = logText.split("\n").filter((line) => line.length > 0);

  function onSaveAsProfileShortcut() {
    profilesSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => {
      profileNameInputRef.current?.focus();
    }, 120);
  }

  return (
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

        <section className="runs-stat-stack" aria-label="Run statistics">
          <div className="grid three">
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
          </div>
          <RunStatistics summary={summary} />
        </section>

        {canCreateRuns ? (
            <CollapsibleSection title="Start Run" defaultExpanded={true}>
              <div className="grid two" style={{ alignItems: "start" }}>
                <RunLaunchPanel
                  flows={flows}
                  flowCapabilities={flowCapabilities}
                  resolvedMode={resolvedMode}
                  modeValidationError={modeValidationError}
                  form={form}
                  isSubmitting={isSubmitting}
                  selectedRun={selectedRun}
                  isExpanded={isStartRunExpanded}
                  onToggleExpanded={() => setIsStartRunExpanded(!isStartRunExpanded)}
                  onFormChange={(updater) => setForm(updater)}
                  onStartRun={onStartRun}
                  onCancelSelectedRun={() => selectedRun && onCancelRun(selectedRun.id)}
                  onSaveAsProfileShortcut={onSaveAsProfileShortcut}
                  commandPreview={commandPreview}
                  hasAdvancedOverrides={
                    Boolean(form.mode) ||
                    Boolean(form.suite) ||
                    Boolean(form.scenarios && form.scenarios.length > 0)
                  }
                  canCancelSelectedRun={Boolean(selectedRun && isActiveStatus(selectedRun.status))}
                  planOptions={simulationPlans}
                />
                <RunLiveConsole
                  selectedRun={selectedRun}
                  logLines={logLines}
                  isExpanded={isLiveConsoleExpanded}
                  onToggleExpanded={() => setIsLiveConsoleExpanded(!isLiveConsoleExpanded)}
                  logClassForLine={logClassForLine}
                />
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

        {canCreateRuns ? (
          <div ref={profilesSectionRef}>
            <RunProfilesPanel
              profiles={profiles}
              profileName={profileName}
              profileDescription={profileDescription}
              selectedProfileId={selectedProfileId}
              isSaving={isProfileSubmitting}
              isLaunching={isProfileLaunching}
              form={form}
              onProfileNameChange={setProfileName}
              onProfileDescriptionChange={setProfileDescription}
              onSaveProfile={onSaveProfile}
              onUpdateProfile={onUpdateProfile}
              onLoadProfile={onLoadProfile}
              onLaunchProfile={onLaunchProfile}
              onDeleteProfile={onDeleteProfile}
              profileNameInputRef={(node) => {
                profileNameInputRef.current = node;
              }}
            />
          </div>
        ) : null}


        <CollapsibleSection title="Flow Planner & Command Guide" defaultExpanded={false}>
          <FlowPlannerGuide
            guideTab={guideTab}
            onGuideTabChange={setGuideTab}
            architectureContent={ARCHITECTURE_CONTENT}
            simulatorGuideContent={SIMULATOR_GUIDE_CONTENT}
          />
        </CollapsibleSection>

        <CollapsibleSection title="Recent Runs" defaultExpanded={true}>
          <RecentRunsTable
            runs={runs}
            runsTotal={runsTotal}
            runsOffset={runsOffset}
            runsPerPage={RUNS_PER_PAGE}
            onPageChange={setRunsOffset}
            onViewRun={(runId) => router.push(`/runs/${runId}`)}
            onCancelRun={onCancelRun}
            onDeleteRunRequest={setDeleteConfirmRun}
            isActiveStatus={isActiveStatus}
          />
        </CollapsibleSection>

        {/* Admin Dashboard - Only visible to admins */}
        {isAdmin && (
          <CollapsibleSection title="Admin Dashboard" defaultExpanded={false}>
            <div className="panel grid" style={{ gap: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Admin Dashboard</h2>
              </div>
              <AdminDashboard />
            </div>
          </CollapsibleSection>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirmRun ? (
          <DeleteRunModal
            run={deleteConfirmRun}
            onConfirm={() => {
              onDeleteRun(deleteConfirmRun.id);
              setDeleteConfirmRun(null);
            }}
            onCancel={() => setDeleteConfirmRun(null)}
          />
        ) : null}
      </main>
  );
}
