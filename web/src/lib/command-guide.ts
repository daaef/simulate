export type GuideFlowRow = {
  flow: string;
  resolved_mode: "trace" | "load";
  suite_or_scenarios: string;
  what_it_tests: string;
  prerequisites: string;
  optional_flags: string;
  artifacts: string;
};

export type GuideCommandRow = {
  command: string;
  purpose: string;
  when_to_use: string;
  expected_result: string;
  common_failure: string;
};

export type GuideFlagRow = {
  flag: string;
  type: string;
  default_value: string;
  effect: string;
  constraints: string;
};

export type GuideComboRule = {
  combination: string;
  verdict: "valid" | "invalid" | "conditional";
  explanation: string;
  fix: string;
};

export type GuideFailureHint = {
  signature: string;
  likely_cause: string;
  next_action: string;
};

export const GUIDE_FLOW_MATRIX: GuideFlowRow[] = [
  {
    flow: "doctor",
    resolved_mode: "trace",
    suite_or_scenarios: "suite=doctor",
    what_it_tests: "Daily operator health flow with bootstrap, store setup, menu states, paid order, accept/reject, robot completion, receipt/review/reorder.",
    prerequisites: "Plan with at least one user and one store; auth credentials in .env.",
    optional_flags: "--timing, --store, --phone, --all-users, --no-auto-provision",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "full",
    resolved_mode: "trace",
    suite_or_scenarios: "suite=full",
    what_it_tests: "Most complete app-like trace including new user, coupon flows (paid/free), and full post-order checks.",
    prerequisites: "Coupon source enabled (SIM_AUTO_SELECT_COUPON=true or SIM_COUPON_ID set) for coupon scenarios.",
    optional_flags: "--timing, --store, --phone, --post-order-actions, --no-auto-provision",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "audit",
    resolved_mode: "trace",
    suite_or_scenarios: "suite=audit",
    what_it_tests: "Deep environment/system audit with broad scenario coverage and dashboard probes.",
    prerequisites: "Stable test backend and a plan with valid user/store records.",
    optional_flags: "--timing, --skip-app-probes, --skip-store-dashboard-probes",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "payments",
    resolved_mode: "trace",
    suite_or_scenarios: "suite=payments",
    what_it_tests: "Paid-no-coupon, paid-with-coupon, and free-with-coupon payment branches.",
    prerequisites: "Stripe test secret for paid branches and coupon availability for coupon branches.",
    optional_flags: "--timing, --post-order-actions",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "menus",
    resolved_mode: "trace",
    suite_or_scenarios: "suite=menus",
    what_it_tests: "Menu availability states (available, unavailable, sold out, store closed).",
    prerequisites: "Store selected in plan or --store.",
    optional_flags: "--timing, --store, --no-auto-provision",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "new-user",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[new_user_setup]",
    what_it_tests: "New user OTP/signup path and first-order readiness checks.",
    prerequisites: "Phone should not already be fully onboarded for strict new-user branch behavior.",
    optional_flags: "--phone, --store, --timing",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "paid-no-coupon",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[returning_paid_no_coupon]",
    what_it_tests: "Returning user paid order without coupon.",
    prerequisites: "Stripe test secret configured.",
    optional_flags: "--store, --phone, --timing, --post-order-actions",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "paid-coupon",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[returning_paid_with_coupon]",
    what_it_tests: "Returning user paid order with coupon discount.",
    prerequisites: "Coupon source available and Stripe test secret configured.",
    optional_flags: "--store, --phone, --timing, --post-order-actions",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "free-coupon",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[returning_free_with_coupon]",
    what_it_tests: "Returning user coupon order that resolves to zero amount and uses free-order branch.",
    prerequisites: "Coupon source available; coupon must reduce payable amount to zero.",
    optional_flags: "--store, --phone, --timing, --post-order-actions",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "store-setup",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[store_first_setup]",
    what_it_tests: "Store setup flow and profile/menu preflight behavior.",
    prerequisites: "Store login available; mutation enabled unless --no-auto-provision.",
    optional_flags: "--store, --timing, --no-auto-provision",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "store-dashboard",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[store_dashboard]",
    what_it_tests: "Store dashboard APIs (stats, revenue, top customers/orders).",
    prerequisites: "Store login token and valid store profile.",
    optional_flags: "--store, --timing, --skip-store-dashboard-probes",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "store-accept",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[store_accept]",
    what_it_tests: "Order accepted by store then processed to completion path.",
    prerequisites: "Menu item available for selected store.",
    optional_flags: "--store, --phone, --timing",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "store-reject",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[store_reject]",
    what_it_tests: "Order rejected by store branch and rejection assertions.",
    prerequisites: "Menu item available for selected store.",
    optional_flags: "--store, --phone, --timing",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "robot-complete",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[robot_complete]",
    what_it_tests: "Robot progression states through completed delivery lifecycle.",
    prerequisites: "Store accept branch reachable and robot simulation enabled.",
    optional_flags: "--store, --phone, --timing",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "receipt-review",
    resolved_mode: "trace",
    suite_or_scenarios: "scenarios=[receipt_review_reorder]",
    what_it_tests: "Post-order actions: receipt fetch, review/rating, and reorder call.",
    prerequisites: "At least one completed order in the scenario branch.",
    optional_flags: "--store, --phone, --timing, --post-order-actions",
    artifacts: "events.json, report.md, story.md"
  },
  {
    flow: "load",
    resolved_mode: "load",
    suite_or_scenarios: "mode=load (multi-user workers)",
    what_it_tests: "Concurrent long-running order traffic with configurable users/orders/rejection rate.",
    prerequisites: "Plan with users/stores; backend can handle concurrent auth/orders/websockets.",
    optional_flags: "--users, --orders, --interval, --reject, --continuous, --all-users",
    artifacts: "events.json, report.md, story.md"
  }
];

export const GUIDE_COMMAND_ROWS: GuideCommandRow[] = [
  {
    command: "python3 -m simulate doctor --plan sim_actors.json --timing fast",
    purpose: "Default daily health run with app-like behavior and concise timing.",
    when_to_use: "Baseline smoke/regression test before or after backend changes.",
    expected_result: "Run should complete and produce events/report/story artifacts with pass/fail findings.",
    common_failure: "No active delivery locations returned (SIM_LAT/SIM_LNG mismatch with service area)."
  },
  {
    command: "python3 -m simulate full --plan sim_actors.json --timing realistic",
    purpose: "Deep end-to-end audit that includes coupon and new-user branches.",
    when_to_use: "Nightly or pre-release environment verification.",
    expected_result: "Large artifact set with full scenario verdict matrix.",
    common_failure: "Coupon-required scenario fails without coupon source."
  },
  {
    command: "python3 -m simulate --mode trace --suite audit --plan sim_actors.json",
    purpose: "Manual suite-driven trace when you want direct control without flow alias.",
    when_to_use: "Engineer-level custom debug runs tied to a known suite.",
    expected_result: "Trace suite executes in defined order with per-scenario assertions.",
    common_failure: "Unsupported suite/scenario spelling."
  },
  {
    command: "python3 -m simulate --mode trace --scenario store_first_setup --scenario store_dashboard --store FZY_926025",
    purpose: "Run selected scenarios only, in sequence.",
    when_to_use: "Targeted reproduction of one subsystem before full audit.",
    expected_result: "Only the specified scenarios run and write artifacts.",
    common_failure: "Store auth/profile lookup fails for missing/invalid store_id."
  },
  {
    command: "python3 -m simulate load --plan sim_actors.json --users 5 --orders 50 --interval 5 --reject 0.1",
    purpose: "Bounded concurrent load test with deterministic scale knobs.",
    when_to_use: "Performance and stability checks under realistic multi-user traffic.",
    expected_result: "All user workers place orders until order quota is met, then artifacts are written.",
    common_failure: "Load config invalid (users/orders < 1 or reject outside 0..1)."
  },
  {
    command: "python3 -m simulate load --plan sim_actors.json --users 10 --continuous",
    purpose: "Continuous soak run until manually stopped.",
    when_to_use: "Long-running reliability checks and websocket durability tests.",
    expected_result: "Run status remains running; stop manually from GUI or cancel endpoint.",
    common_failure: "Used with trace mode (unsupported)."
  },
  {
    command: "python3 -m simulate free-coupon --plan sim_actors.json --store FZY_926025 --phone +2348166675609",
    purpose: "Validate free-order endpoint branch driven by zero-amount coupon flow.",
    when_to_use: "Coupon and payment branching regression checks.",
    expected_result: "Order should route through free payment mode path.",
    common_failure: "Coupon not found or does not reduce payable amount to zero."
  },
  {
    command: "python3 -m simulate doctor --plan sim_actors.json --store FZY_926025 --phone +2348166675609 --no-auto-provision",
    purpose: "Negative test for missing setup/menu prerequisites without simulator mutation.",
    when_to_use: "Backend readiness checks where preconditions must be explicit.",
    expected_result: "Run fails fast when store/user prerequisites are absent.",
    common_failure: "No priced menu items found or store setup not complete."
  }
];

export const GUIDE_FLAG_ROWS: GuideFlagRow[] = [
  {
    flag: "--mode",
    type: "enum(trace|load)",
    default_value: "from .env SIM_RUN_MODE",
    effect: "Forces trace suite/scenario execution or load worker execution.",
    constraints: "If trace, do not use --continuous."
  },
  {
    flag: "--suite",
    type: "string",
    default_value: "from .env SIM_TRACE_SUITE",
    effect: "Selects named trace scenario suite.",
    constraints: "Trace mode only."
  },
  {
    flag: "--scenario",
    type: "repeatable string",
    default_value: "none",
    effect: "Appends explicit scenario list for trace mode.",
    constraints: "Trace mode only; must match supported scenario keys."
  },
  {
    flag: "--timing",
    type: "enum(fast|realistic)",
    default_value: "from .env SIM_TIMING_PROFILE",
    effect: "Controls delay ranges and auto-cancel wait windows.",
    constraints: "Affects both trace and flow presets."
  },
  {
    flag: "--users",
    type: "int",
    default_value: "from .env N_USERS",
    effect: "Sets concurrent user workers.",
    constraints: "Load mode only; value must be >= 1."
  },
  {
    flag: "--orders",
    type: "int",
    default_value: "from .env SIM_ORDERS",
    effect: "Total orders to place in bounded load mode.",
    constraints: "Load mode only; value must be >= 1."
  },
  {
    flag: "--interval",
    type: "float seconds",
    default_value: "from .env ORDER_INTERVAL_SECONDS",
    effect: "Delay between order submissions per user worker.",
    constraints: "Load mode only."
  },
  {
    flag: "--reject",
    type: "float [0..1]",
    default_value: "from .env REJECT_RATE",
    effect: "Store rejection probability in load flow.",
    constraints: "Load mode only; must be between 0 and 1."
  },
  {
    flag: "--continuous",
    type: "boolean switch",
    default_value: "false",
    effect: "Runs load mode indefinitely until canceled.",
    constraints: "Invalid in trace mode."
  },
  {
    flag: "--phone",
    type: "string",
    default_value: "from selected plan actor",
    effect: "Overrides selected user phone.",
    constraints: "Should exist in plan unless testing onboarding branch."
  },
  {
    flag: "--store",
    type: "string",
    default_value: "from selected plan store",
    effect: "Overrides selected store ID for auth/preflight/order flows.",
    constraints: "Must map to a valid backend store login."
  },
  {
    flag: "--all-users",
    type: "boolean switch",
    default_value: "false",
    effect: "Runs all users from the plan instead of single selected user.",
    constraints: "Load and trace both supported; increases runtime/data volume."
  },
  {
    flag: "--plan",
    type: "file path",
    default_value: "from .env SIM_ACTORS_PATH",
    effect: "Loads users/stores/defaults JSON actor plan.",
    constraints: "Path must exist and parse as valid JSON."
  },
  {
    flag: "--strict-plan",
    type: "boolean switch",
    default_value: "from .env SIM_STRICT_PLAN",
    effect: "Enforces complete plan fields for users/stores.",
    constraints: "May fail early if user/store entries are incomplete."
  },
  {
    flag: "--skip-app-probes",
    type: "boolean switch",
    default_value: "false",
    effect: "Skips non-order user app probes (config/pricing/cards/coupons).",
    constraints: "Trace mode diagnostics become narrower."
  },
  {
    flag: "--skip-store-dashboard-probes",
    type: "boolean switch",
    default_value: "false",
    effect: "Skips store dashboard probe APIs.",
    constraints: "Trace/load store observability coverage is reduced."
  },
  {
    flag: "--post-order-actions",
    type: "boolean switch",
    default_value: "from .env SIM_RUN_POST_ORDER_ACTIONS",
    effect: "Runs receipt/review/reorder after completed orders.",
    constraints: "Requires completed orders in selected scenarios."
  },
  {
    flag: "--enforce-websocket-gates / --no-enforce-websocket-gates",
    type: "boolean switch",
    default_value: "from .env SIM_ENFORCE_WEBSOCKET_GATES (false)",
    effect: "Controls whether websocket gate failures fail fast or are recorded as warnings and bypassed.",
    constraints: "Affects trace/doctor progression behavior when websocket source is unavailable or delayed."
  },
  {
    flag: "--no-auto-provision",
    type: "boolean switch",
    default_value: "false",
    effect: "Disables auto setup/menu provisioning mutations.",
    constraints: "Use for negative tests; may fail when setup/menu missing."
  }
];

export const GUIDE_COMBO_RULES: GuideComboRule[] = [
  {
    combination: "--mode trace + --continuous",
    verdict: "invalid",
    explanation: "Continuous runs are only implemented for load mode.",
    fix: "Switch to --mode load or remove --continuous."
  },
  {
    combination: "paid-coupon/free-coupon flow + no coupon source",
    verdict: "invalid",
    explanation: "Coupon scenarios require SIM_COUPON_ID or SIM_AUTO_SELECT_COUPON=true.",
    fix: "Set coupon id in .env/plan or enable auto coupon selection."
  },
  {
    combination: "--mode load + --scenario/--suite",
    verdict: "invalid",
    explanation: "Load mode does not execute trace suites/scenarios.",
    fix: "Use trace mode for scenario/suite execution."
  },
  {
    combination: "trace flow + --users/--orders/--reject/--interval",
    verdict: "conditional",
    explanation: "These flags are parsed but do not drive trace scenario scheduling.",
    fix: "Use these only for load mode unless intentionally keeping defaults aligned."
  },
  {
    combination: "--no-auto-provision + store without setup/menu",
    verdict: "conditional",
    explanation: "Run can fail by design if prerequisites are absent.",
    fix: "Use store-setup flow first or remove --no-auto-provision."
  },
  {
    combination: "--strict-plan + partial actor entries",
    verdict: "invalid",
    explanation: "Strict mode enforces required store/user fields.",
    fix: "Complete plan fields or run without --strict-plan."
  },
  {
    combination: "--all-users + large plan",
    verdict: "conditional",
    explanation: "Expands run fan-out and increases runtime/backend load.",
    fix: "Use targeted --phone for quick checks, then scale when needed."
  }
];

export const GUIDE_FAILURE_HINTS: GuideFailureHint[] = [
  {
    signature: "No active delivery locations were returned",
    likely_cause: "User GPS/radius does not map to active backend service area.",
    next_action: "Adjust SIM_LAT/SIM_LNG/SIM_LOCATION_RADIUS or actor GPS to an active delivery zone."
  },
  {
    signature: "No available priced menu items found",
    likely_cause: "Store menu missing, sold out, or unavailable and provisioning disabled.",
    next_action: "Run store-setup or doctor without --no-auto-provision, then retry."
  },
  {
    signature: "SIM_COUPON_ID is required for coupon flows",
    likely_cause: "Coupon flow selected while neither fixed coupon nor auto selection is enabled.",
    next_action: "Set SIM_COUPON_ID or enable SIM_AUTO_SELECT_COUPON=true."
  },
  {
    signature: "STRIPE_SECRET_KEY is required when SIM_PAYMENT_MODE=stripe",
    likely_cause: "Paid flow selected without Stripe test key.",
    next_action: "Set STRIPE_SECRET_KEY in .env with the same test account as backend webhooks."
  },
  {
    signature: "No users could be authenticated",
    likely_cause: "Plan/override phone(s) invalid or OTP/auth backend not reachable.",
    next_action: "Verify phone values in plan and backend OTP/auth availability."
  },
  {
    signature: "No stores could be logged in",
    likely_cause: "Invalid store id or store token endpoint failure.",
    next_action: "Verify store_id, store credentials, and store auth endpoint health."
  }
];

export const PLAN_TEMPLATE = `{
  "defaults": {
    "payment_mode": "stripe",
    "timing": "fast"
  },
  "users": [
    {
      "phone": "+2348166675609",
      "lat": 9.9094,
      "lng": 8.8912
    }
  ],
  "stores": [
    {
      "store_id": "FZY_926025"
    }
  ]
}`;

export const TIMING_REFERENCE = [
  {
    profile: "fast",
    store_decision_delay: "0.2s to 0.5s",
    store_prep_delay: "0.2s to 0.5s",
    robot_progression_delay: "0.2s to 0.6s per status hop",
    auto_cancel_wait: "30s"
  },
  {
    profile: "realistic",
    store_decision_delay: "3s to 12s",
    store_prep_delay: "20s to 90s",
    robot_progression_delay: "5s to 120s per status hop",
    auto_cancel_wait: "180s"
  }
];
