"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  GUIDE_COMBO_RULES,
  GUIDE_COMMAND_ROWS,
  GUIDE_FAILURE_HINTS,
  GUIDE_FLAG_ROWS,
  GUIDE_FLOW_MATRIX,
  PLAN_TEMPLATE,
  TIMING_REFERENCE,
} from "../../lib/command-guide";

type GuideTab = "flows" | "commands" | "flags" | "plan" | "rules" | "failures" | "architecture" | "guide";

interface FlowPlannerGuideProps {
  guideTab: GuideTab;
  onGuideTabChange: (tab: GuideTab) => void;
  architectureContent: string;
  simulatorGuideContent: string;
}

function MarkdownPane({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>;
}

function comboClass(verdict: string): string {
  if (verdict === "valid") return "chip chip-valid";
  if (verdict === "invalid") return "chip chip-invalid";
  return "chip chip-conditional";
}

export default function FlowPlannerGuide({
  guideTab,
  onGuideTabChange,
  architectureContent,
  simulatorGuideContent,
}: FlowPlannerGuideProps) {
  return (
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
            ["guide", "Simulator Guide"],
          ] as Array<[GuideTab, string]>
        ).map(([value, label]) => (
          <button key={value} className={guideTab === value ? "" : "secondary"} onClick={() => onGuideTabChange(value)}>
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
                  <td><code>{row.flow}</code></td>
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
                  <td><code>{row.command}</code></td>
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
                  <td><code>{row.flag}</code></td>
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
                    <td><code>{row.profile}</code></td>
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
                  <td><span className={comboClass(row.verdict)}>{row.verdict}</span></td>
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
          <MarkdownPane text={architectureContent} />
        </div>
      ) : null}
      {guideTab === "guide" ? (
        <div className="artifact markdown-view">
          <MarkdownPane text={simulatorGuideContent} />
        </div>
      ) : null}
    </div>
  );
}
