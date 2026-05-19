"use client";

import type { LatestRunIssue } from "../../lib/api";
import FindingsPanel from "./FindingsPanel";

export default function OperationalFindings({ issues }: { issues: LatestRunIssue[] }) {
  return (
    <article>
      <FindingsPanel
        title="Operational Findings"
        issues={issues}
        emptyMessage="No operational findings in the latest run."
        limit={25}
      />
    </article>
  );
}
