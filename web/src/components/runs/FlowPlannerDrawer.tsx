"use client";

import { useEffect, useRef } from "react";
import FlowPlannerGuide from "./FlowPlannerGuide";
import { useFocusTrap } from "../../lib/useFocusTrap";

type GuideTab = "flows" | "commands" | "flags" | "plan" | "rules" | "failures" | "architecture" | "guide";

interface FlowPlannerDrawerProps {
  open: boolean;
  onClose: () => void;
  guideTab: GuideTab;
  onGuideTabChange: (tab: GuideTab) => void;
  architectureContent: string;
  simulatorGuideContent: string;
}

export default function FlowPlannerDrawer({
  open,
  onClose,
  guideTab,
  onGuideTabChange,
  architectureContent,
  simulatorGuideContent,
}: FlowPlannerDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(open, panelRef);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="flow-planner-drawer" role="presentation">
      <button
        type="button"
        className="flow-planner-drawer__backdrop"
        aria-label="Close guide"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        className="flow-planner-drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="flow-planner-drawer-title"
      >
        <header className="flow-planner-drawer__header">
          <h2 id="flow-planner-drawer-title" style={{ margin: 0 }}>
            Flow Planner &amp; Command Guide
          </h2>
          <button type="button" className="secondary small" style={{ width: "auto" }} onClick={onClose}>
            Close
          </button>
        </header>
        <div className="flow-planner-drawer__body">
          <FlowPlannerGuide
            guideTab={guideTab}
            onGuideTabChange={onGuideTabChange}
            architectureContent={architectureContent}
            simulatorGuideContent={simulatorGuideContent}
          />
        </div>
      </aside>
    </div>
  );
}
