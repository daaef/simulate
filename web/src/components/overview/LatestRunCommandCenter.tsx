"use client";

import type { LatestRunOverview } from "../../lib/api";
import RunActionCountsPanel from "../runs/RunActionCountsPanel";
import ActorStrip from "./ActorStrip";
import CriticalFindings from "./CriticalFindings";
import LatestRunHero from "./LatestRunHero";
import LifecycleTimeline from "./LifecycleTimeline";
import ProtocolHealthBoard from "./ProtocolHealthBoard";
import TopTrafficPanel from "./TopTrafficPanel";

export default function LatestRunCommandCenter({
  overview,
}: {
  overview: LatestRunOverview | null;
}) {
  if (!overview) {
    return (
      <section className="latest-run-command-center">
        <article className="panel">
          <p className="muted">Loading latest run intelligence...</p>
        </article>
      </section>
    );
  }

  return (
    <section className="latest-run-command-center">
      <LatestRunHero overview={overview} />
      {overview.run && overview.metrics ? (
        <RunActionCountsPanel
          action_counts={overview.metrics.action_counts}
          total_events={overview.metrics.total_events}
          failed_events={overview.metrics.failed_events}
          http_calls={overview.metrics.http_calls}
          websocket_events={overview.metrics.websocket_events}
          top_actors={overview.metrics.top_actors}
          title={`Run #${overview.run.id} Metrics Dashboard`}
          defaultCollapsed
          showOutcomeChips
        />
      ) : null}
      <ActorStrip actors={overview.actors || {}} />
      <ProtocolHealthBoard
        http={overview.protocols?.http || {}}
        websocket={overview.protocols?.websocket || {}}
      />
      <section className="grid two">
        <LifecycleTimeline steps={overview.lifecycle || []} />
        <CriticalFindings issues={overview.issues || []} />
      </section>
      <TopTrafficPanel
        http={overview.protocols?.http || {}}
        websocket={overview.protocols?.websocket || {}}
      />
    </section>
  );
}
