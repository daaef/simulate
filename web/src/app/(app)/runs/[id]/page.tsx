"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  fetchExecutionSnapshot,
  fetchRunOverview,
  fetchRun,
  fetchRunArtifactEvents,
  fetchRunArtifactText,
  fetchRunLog,
  fetchRunMetrics,
  replayRun,
  type RunMetrics,
  type RunRow,
  type LatestRunIssue,
} from "../../../../lib/api";
import RunArtifactMarkdown from "../../../../components/runs/detail/RunArtifactMarkdown";
import RunDetailHeader from "../../../../components/runs/detail/RunDetailHeader";
import RunDetailOverview from "../../../../components/runs/detail/RunDetailOverview";
import RunDetailTabNav from "../../../../components/runs/detail/RunDetailTabNav";
import RunEventsPanel from "../../../../components/runs/detail/RunEventsPanel";
import RunExecutionSnapshotPanel from "../../../../components/runs/detail/RunExecutionSnapshotPanel";
import RunLogPanel from "../../../../components/runs/detail/RunLogPanel";

type TabType = "overview" | "story" | "report" | "traffic" | "console" | "execution";

type EventRow = Record<string, unknown>;

const EVENTS_PAGE_SIZE = 100;

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

interface PageParams {
  [key: string]: string;
  id: string;
}

export default function RunDetailPage() {
  const router = useRouter();
  const params = useParams<PageParams>();
  const runId = parseInt(params.id, 10);

  const [run, setRun] = useState<RunRow | null>(null);
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [issues, setIssues] = useState<LatestRunIssue[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Artifact states
  const [report, setReport] = useState<string | null>(null);
  const [story, setStory] = useState<string | null>(null);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsOffset, setEventsOffset] = useState(0);
  const [log, setLog] = useState<string | null>(null);
  const [reportChunk, setReportChunk] = useState(0);
  const [isReplaying, setIsReplaying] = useState(false);

  // Fetch run data
  useEffect(() => {
    let cancelled = false;
    fetchRun(runId)
      .then((data) => {
        if (!cancelled) setRun(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Fetch metrics
  useEffect(() => {
    fetchRunMetrics(runId).then((res) => {
      if (res.available) setMetrics(res.metrics);
    }).catch(() => {
      // Metrics not available, ignore
    });
    fetchExecutionSnapshot(runId)
      .then((payload) => {
        if (payload.available) {
          setRun((current) => (current ? { ...current, execution_snapshot: payload.snapshot } : current));
        }
      })
      .catch(() => {
        // Snapshot not available, ignore
      });
    fetchRunOverview(runId)
      .then((payload) => {
        setIssues(payload.issues || []);
      })
      .catch(() => {
        setIssues([]);
      });
  }, [runId]);

  // Fetch artifacts based on active tab
  useEffect(() => {
    if (!run) return;

    const loadArtifact = async () => {
      switch (activeTab) {
        case "report":
          if (report === null && run.report_path) {
            const res = await fetchRunArtifactText(runId, "report");
            if (res.available) setReport(res.content);
          }
          break;
        case "story":
          if (story === null && run.story_path) {
            const res = await fetchRunArtifactText(runId, "story");
            if (res.available) setStory(res.content);
          }
          break;
        case "traffic":
          if (run.events_path) {
            const res = await fetchRunArtifactEvents(runId, { offset: eventsOffset, limit: EVENTS_PAGE_SIZE });
            if (res.available) {
              setEvents(res.content as EventRow[]);
              setEventsTotal(res.total_count || 0);
            }
          }
          break;
        case "console":
          if (log === null) {
            const res = await fetchRunLog(runId, 5000);
            if (res.available) setLog(res.log);
          }
          break;
      }
    };

    loadArtifact();
  }, [activeTab, run, runId, eventsOffset, report, story, log]);

  const goBack = () => {
    router.push("/runs");
  };

  const handleReplay = async () => {
    setIsReplaying(true);
    try {
      const payload = await replayRun(runId);
      router.push(`/runs/${payload.run.id}`);
    } finally {
      setIsReplaying(false);
    }
  };

  if (loading) {
    return (
      <main style={{ maxWidth: 1200, margin: "0 auto", padding: 40, textAlign: "center" }}>
        <p className="muted">Loading run details...</p>
      </main>
    );
  }

  if (error || !run) {
    return (
      <main style={{ maxWidth: 600, margin: "40px auto", padding: 40, textAlign: "center" }} className="panel">
        <h2 style={{ color: "#b91c1c" }}>Error loading run</h2>
        <p className="muted">{error || "Run not found"}</p>
        <button onClick={goBack} style={{ width: "auto", marginTop: 16 }}>
          Back to Dashboard
        </button>
      </main>
    );
  }

  return (
    <main className="grid" style={{ gap: 16 }}>
      <RunDetailHeader run={run} onBack={goBack} />

      <div className="panel grid" style={{ gap: 12 }}>
        <RunDetailTabNav
          activeTab={activeTab}
          onTabChange={setActiveTab}
          hasReport={Boolean(run.report_path)}
          hasStory={Boolean(run.story_path)}
          hasEvents={Boolean(run.events_path)}
        />

        <div>
          {activeTab === "overview" && (
            <RunDetailOverview metrics={metrics} runStatus={run.status} runError={run.error} issues={issues} />
          )}

          {activeTab === "execution" && <RunExecutionSnapshotPanel run={run} onReplay={handleReplay} replaying={isReplaying} />}

          {activeTab === "report" && (
            <RunArtifactMarkdown
              text={report}
              emptyMessage="Report artifact is not available yet."
              chunkIndex={reportChunk}
              onChunkChange={setReportChunk}
            />
          )}

          {activeTab === "story" && (
            <RunArtifactMarkdown text={story} emptyMessage="Story artifact is not available yet." />
          )}

          {activeTab === "traffic" && (
            <RunEventsPanel
              events={events}
              eventsTotal={eventsTotal}
              eventsOffset={eventsOffset}
              pageSize={EVENTS_PAGE_SIZE}
              onPreviousPage={() => setEventsOffset(Math.max(0, eventsOffset - EVENTS_PAGE_SIZE))}
              onNextPage={() => setEventsOffset(eventsOffset + EVENTS_PAGE_SIZE)}
            />
          )}

          {activeTab === "console" && (
            <RunLogPanel log={log} logClassForLine={logClassForLine} />
          )}
        </div>
      </div>
    </main>
  );
}
