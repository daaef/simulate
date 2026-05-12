"use client";

import type { LatestRunOverview } from "../../lib/api";
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