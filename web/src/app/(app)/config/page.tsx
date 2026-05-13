"use client";

import { useEffect, useMemo, useState } from "react";
import { useRole } from "../../../contexts/RoleContext";
import {
  ApiRequestError,
  createSimulationPlan,
  deleteSimulationPlan,
  fetchSystemEmailSettings,
  fetchSimulationPlan,
  fetchSimulationPlans,
  sendSystemTestEmail,
  type EmailEventTrigger,
  type SystemEmailSettings,
  updateSimulationPlan,
  updateSystemEmailSettings,
  type SimulationPlan,
  type SimulationPlanContent,
} from "../../../lib/api";
import IntegrationMappingsPanel from "../../../components/config/IntegrationMappingsPanel";

const PLAN_TEMPLATE: SimulationPlanContent = {
  schema_version: 2,
  defaults: {
    user_phone: "+2348166675609",
    store_id: "FZY_586940",
    location_radius: 1,
    coupon_id: null,
  },
  runtime_defaults: {
    flow: "doctor",
    mode: "trace",
    trace_suite: "doctor",
    trace_scenarios: [],
    timing_profile: "fast",
    users: 1,
    orders: 1,
    interval_seconds: 30,
    reject_rate: 0.1,
    continuous: false,
  },
  rules: {
    strict_plan: false,
    run_app_probes: true,
    run_store_dashboard_probes: true,
    run_post_order_actions: false,
    app_autopilot: true,
    auto_select_store: true,
    auto_select_coupon: true,
    auto_provision_fixtures: true,
    mutate_store_setup: false,
    mutate_menu_setup: false,
    auto_toggle_store_status: true,
  },
  payment_defaults: {
    mode: "stripe",
    case: "paid_no_coupon",
    free_order_amount: 0,
    coupon_id: null,
    save_card: false,
    test_payment_method: "pm_card_visa",
  },
  fixture_defaults: {
    store_setup: {
      name: "Fainzy Simulator Store",
      branch: "Simulator",
      description: "Store profile created by simulator setup flow.",
      start_time: "07:00",
      closing_time: "23:59",
      status: 1,
      address: "Simulator address",
      city: "Nagoya",
      state: "Aichi",
      country: "Japan",
    },
    menu: {
      category_name: "Simulator",
      name: "Simulator item",
      description: "Menu item created by simulator.",
      price: 100,
      ingredients: "simulator ingredients",
      discount: 0,
      discount_price: 0,
    },
  },
  review_defaults: {
    rating: 4,
    comment: "Simulator review",
  },
  new_user_defaults: {
    first_name: "Fainzy",
    last_name: "Simulator",
    email: "",
  },
  users: [
    {
      phone: "+2348166675609",
      role: "returning_default",
      lat: 35.15494521954757,
      lng: 136.9663666561246,
    },
  ],
  stores: [
    {
      store_id: "FZY_586940",
      subentity_id: 6,
      name: "Premium Cafe JP",
      branch: "Premium Cafe JP",
      currency: "jpy",
      status: 1,
      lat: 35.15494521954757,
      lng: 136.9663666561246,
    },
  ],
};

function formatError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}

function pretty(value: SimulationPlanContent): string {
  return JSON.stringify(value, null, 2);
}

const EMAIL_TRIGGER_OPTIONS: { value: EmailEventTrigger; label: string }[] = [
  { value: "run_failed", label: "Run failed" },
  { value: "schedule_launch_failed", label: "Schedule launch failed" },
  { value: "critical_alert", label: "Critical alert (mapped to run failed)" },
];

const DEFAULT_EMAIL_SETTINGS: SystemEmailSettings = {
  email_enabled: false,
  email_from_email: "",
  email_from_name: "",
  email_subject_prefix: "",
  email_recipients: [],
  email_event_triggers: [],
};

export default function ConfigPage() {
  const { hasPermission } = useRole();
  const canConfigure = hasPermission("system", "configure");
  const [plans, setPlans] = useState<SimulationPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [planName, setPlanName] = useState("Daily Doctor Plan");
  const [editorValue, setEditorValue] = useState(pretty(PLAN_TEMPLATE));
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [emailSettings, setEmailSettings] = useState<SystemEmailSettings>(DEFAULT_EMAIL_SETTINGS);
  const [emailRecipientsInput, setEmailRecipientsInput] = useState("");
  const [emailMessage, setEmailMessage] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [isEmailSaving, setIsEmailSaving] = useState(false);
  const [isEmailTesting, setIsEmailTesting] = useState(false);

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.id === selectedPlanId) ?? null,
    [plans, selectedPlanId]
  );

  async function loadPlans() {
    setIsLoading(true);
    setError(null);
    try {
      const nextPlans = await fetchSimulationPlans();
      setPlans(nextPlans);
      if (!selectedPlanId && nextPlans[0]) {
        setSelectedPlanId(nextPlans[0].id);
        setPlanName(nextPlans[0].name);
        setEditorValue(pretty(nextPlans[0].content));
      }
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadPlans();
  }, []);

  useEffect(() => {
    async function loadEmailSettings() {
      setEmailError(null);
      try {
        const payload = await fetchSystemEmailSettings();
        setEmailSettings(payload);
        setEmailRecipientsInput((payload.email_recipients || []).join("\n"));
      } catch (caught) {
        setEmailError(formatError(caught));
      }
    }
    void loadEmailSettings();
  }, []);

  async function loadPlan(planId: string) {
    setError(null);
    setMessage(null);
    try {
      const plan = await fetchSimulationPlan(planId);
      setSelectedPlanId(plan.id);
      setPlanName(plan.name);
      setEditorValue(pretty(plan.content));
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  function startNewPlan() {
    setSelectedPlanId(null);
    setPlanName("Daily Doctor Plan");
    setEditorValue(pretty(PLAN_TEMPLATE));
    setMessage(null);
    setError(null);
  }

  async function savePlan() {
    setIsSaving(true);
    setMessage(null);
    setError(null);
    try {
      const parsed = JSON.parse(editorValue) as SimulationPlanContent;
      const saved = selectedPlanId
        ? await updateSimulationPlan(selectedPlanId, { name: planName, content: parsed })
        : await createSimulationPlan({ name: planName, content: parsed });
      setSelectedPlanId(saved.id);
      setPlanName(saved.name);
      setEditorValue(pretty(saved.content));
      setMessage(`Saved ${saved.path}`);
      const nextPlans = await fetchSimulationPlans();
      setPlans(nextPlans);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function removePlan() {
    if (!selectedPlanId) return;
    setIsSaving(true);
    setMessage(null);
    setError(null);
    try {
      await deleteSimulationPlan(selectedPlanId);
      setSelectedPlanId(null);
      setPlanName("Daily Doctor Plan");
      setEditorValue(pretty(PLAN_TEMPLATE));
      setMessage("Plan deleted.");
      const nextPlans = await fetchSimulationPlans();
      setPlans(nextPlans);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function saveEmailSettings() {
    setIsEmailSaving(true);
    setEmailMessage(null);
    setEmailError(null);
    try {
      const payload = await updateSystemEmailSettings({
        ...emailSettings,
        email_recipients: emailRecipientsInput,
      });
      setEmailSettings(payload);
      setEmailRecipientsInput((payload.email_recipients || []).join("\n"));
      setEmailMessage("Email settings saved.");
    } catch (caught) {
      setEmailError(formatError(caught));
    } finally {
      setIsEmailSaving(false);
    }
  }

  async function sendTestEmail() {
    setIsEmailTesting(true);
    setEmailMessage(null);
    setEmailError(null);
    try {
      const result = await sendSystemTestEmail();
      if (!result.sent) {
        setEmailMessage(`Test email not sent (${result.reason || "skipped"}).`);
      } else {
        setEmailMessage("Test email sent successfully.");
      }
    } catch (caught) {
      setEmailError(formatError(caught));
    } finally {
      setIsEmailTesting(false);
    }
  }

  if (!canConfigure) {
    return (
      <div style={{ padding: "24px" }}>
        <h1 style={{ margin: "0 0 8px", fontSize: "36px", color: "var(--text-primary)" }}>Config</h1>
        <div className="panel" style={{ color: "var(--text-secondary)" }}>
          You do not have permission to configure simulation plans.
        </div>
      </div>
    );
  }

  return (
    <div className="grid" style={{ gap: 16, padding: "24px" }}>
      <div>
        <h1 style={{ margin: "0 0 8px", fontSize: "36px", color: "var(--text-primary)" }}>Config</h1>
        <div style={{ color: "var(--text-secondary)" }}>
          Secrets stay in `.env`; this page edits launchable JSON run plans.
        </div>
      </div>

      <div className="grid two" style={{ alignItems: "start" }}>
        <section className="panel grid" style={{ gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <h2>Plans</h2>
            <button type="button" className="secondary small" style={{ width: "auto" }} onClick={startNewPlan}>
              New
            </button>
          </div>
          {isLoading ? (
            <div className="muted">Loading plans...</div>
          ) : plans.length ? (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Path</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id} style={plan.id === selectedPlanId ? { background: "var(--bg-tertiary)" } : undefined}>
                    <td>{plan.name}</td>
                    <td><code>{plan.path}</code></td>
                    <td>
                      <button type="button" className="secondary small" onClick={() => void loadPlan(plan.id)}>
                        Load
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="muted">No GUI plans saved yet.</div>
          )}
        </section>

        <section className="panel grid" style={{ gap: 12 }}>
          <label>
            Plan Name
            <input value={planName} onChange={(event) => setPlanName(event.target.value)} />
          </label>
          {selectedPlan ? (
            <div style={{ color: "var(--text-secondary)" }}>
              Launch path: <code>{selectedPlan.path}</code>
            </div>
          ) : null}
          <label>
            JSON Plan
            <textarea
              value={editorValue}
              onChange={(event) => setEditorValue(event.target.value)}
              rows={28}
              spellCheck={false}
              style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
            />
          </label>
          {error ? (
            <div style={{ border: "1px solid #fca5a5", color: "#991b1b", borderRadius: 6, padding: "10px 12px" }}>
              {error}
            </div>
          ) : null}
          {message ? (
            <div style={{ border: "1px solid #86efac", color: "#166534", borderRadius: 6, padding: "10px 12px" }}>
              {message}
            </div>
          ) : null}
          <div className="grid two">
            <button type="button" disabled={isSaving || !planName.trim()} onClick={() => void savePlan()}>
              {isSaving ? "Saving..." : selectedPlanId ? "Save Plan" : "Create Plan"}
            </button>
            <button type="button" className="secondary" disabled={isSaving || !selectedPlanId} onClick={() => void removePlan()}>
              Delete Selected
            </button>
          </div>
        </section>
      </div>
      <section className="panel grid" style={{ gap: 12 }}>
        <h2>Email Notifications</h2>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={emailSettings.email_enabled}
            onChange={(event) => setEmailSettings((prev) => ({ ...prev, email_enabled: event.target.checked }))}
          />
          Enable email notifications
        </label>
        <div className="grid two">
          <label>
            From Email
            <input
              value={emailSettings.email_from_email}
              onChange={(event) => setEmailSettings((prev) => ({ ...prev, email_from_email: event.target.value }))}
              placeholder="alerts@example.com"
            />
          </label>
          <label>
            From Name (Optional)
            <input
              value={emailSettings.email_from_name}
              onChange={(event) => setEmailSettings((prev) => ({ ...prev, email_from_name: event.target.value }))}
              placeholder="Simulator Alerts"
            />
          </label>
        </div>
        <label>
          Subject Prefix (Optional)
          <input
            value={emailSettings.email_subject_prefix}
            onChange={(event) => setEmailSettings((prev) => ({ ...prev, email_subject_prefix: event.target.value }))}
            placeholder="[Simulator]"
          />
        </label>
        <label>
          Recipients (comma or newline separated)
          <textarea
            value={emailRecipientsInput}
            onChange={(event) => setEmailRecipientsInput(event.target.value)}
            rows={4}
            spellCheck={false}
            placeholder="ops@example.com&#10;eng@example.com"
            style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
          />
        </label>
        <div className="grid" style={{ gap: 8 }}>
          <div style={{ fontWeight: 600 }}>Event Triggers</div>
          {EMAIL_TRIGGER_OPTIONS.map((trigger) => (
            <label key={trigger.value} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={emailSettings.email_event_triggers.includes(trigger.value)}
                onChange={(event) => {
                  setEmailSettings((prev) => {
                    const next = new Set(prev.email_event_triggers);
                    if (event.target.checked) next.add(trigger.value);
                    else next.delete(trigger.value);
                    return { ...prev, email_event_triggers: Array.from(next) as EmailEventTrigger[] };
                  });
                }}
              />
              {trigger.label}
            </label>
          ))}
        </div>
        {emailError ? (
          <div style={{ border: "1px solid #fca5a5", color: "#991b1b", borderRadius: 6, padding: "10px 12px" }}>
            {emailError}
          </div>
        ) : null}
        {emailMessage ? (
          <div style={{ border: "1px solid #86efac", color: "#166534", borderRadius: 6, padding: "10px 12px" }}>
            {emailMessage}
          </div>
        ) : null}
        <div className="grid two">
          <button type="button" disabled={isEmailSaving} onClick={() => void saveEmailSettings()}>
            {isEmailSaving ? "Saving..." : "Save Email Settings"}
          </button>
          <button type="button" className="secondary" disabled={isEmailTesting} onClick={() => void sendTestEmail()}>
            {isEmailTesting ? "Sending..." : "Send Test Email"}
          </button>
        </div>
      </section>
      <IntegrationMappingsPanel />
    </div>
  );
}
