"use client";

import type { LatestRunIssue } from "../../lib/api";
import FindingsPanel from "./FindingsPanel";

export default function CriticalFindings({ issues }: { issues: LatestRunIssue[] }) {
  return (
    <article>
      <FindingsPanel
        title="Critical Findings"
        issues={issues}
        emptyMessage="No critical findings in the latest run."
        limit={6}
      />
    </article>
  );
}
