"use client";

type TabType = "overview" | "story" | "report" | "traffic" | "console" | "execution";

interface RunDetailTabNavProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  hasReport: boolean;
  hasStory: boolean;
  hasEvents: boolean;
}

const TAB_ROWS: Array<{ value: TabType; label: string; description: string }> = [
  { value: "overview", label: "Overview", description: "Operator summary, metrics, and visual health signals." },
  { value: "story", label: "Story", description: "Human-readable narrative of what happened." },
  { value: "report", label: "Technical Report", description: "Full markdown proof document and trace summary." },
  { value: "traffic", label: "Traffic", description: "HTTP and event evidence from recorded artifacts." },
  { value: "console", label: "Console", description: "Raw simulator console output." },
  { value: "execution", label: "Execution", description: "Actor identity, resolved inputs, and replay context." },
];

export default function RunDetailTabNav({
  activeTab,
  onTabChange,
  hasReport,
  hasStory,
  hasEvents,
}: RunDetailTabNavProps) {
  return (
    <div className="grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {TAB_ROWS.map((tab) => {
          const disabled =
            (tab.value === "report" && !hasReport) ||
            (tab.value === "story" && !hasStory) ||
            (tab.value === "traffic" && !hasEvents);
          return (
            <button
              key={tab.value}
              className={activeTab === tab.value ? "" : "secondary"}
              onClick={() => onTabChange(tab.value)}
              disabled={disabled}
              style={{ width: "auto" }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="muted">
        {TAB_ROWS.find((tab) => tab.value === activeTab)?.description}
      </div>
    </div>
  );
}
