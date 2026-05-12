"use client";

import type { ActorSummary } from "../../lib/api";

function identityLine(actor: ActorSummary): string {
  const identity = actor.identity || {};
  const name = String(identity.name || "");
  const id = String(identity.id || identity.subentity_id || identity.login_id || "");
  const phone = String(identity.phone || "");

  return [name, id, phone].filter(Boolean).join(" / ") || "No identity captured";
}

function actorTone(actor: ActorSummary): string {
  if (actor.failed_events > 0) return "status-danger";
  if (actor.events > 0) return "status-success";
  return "status-info";
}

export default function ActorStrip({ actors }: { actors: Record<string, ActorSummary> }) {
  const ordered = ["user", "store", "robot"]
    .map((key) => actors[key])
    .filter(Boolean);

  return (
    <section className="actor-strip">
      {ordered.map((actor) => (
        <article key={actor.key} className="panel actor-card">
          <div className="actor-card-head">
            <div>
              <p className="eyebrow">{actor.label}</p>
              <h3>{identityLine(actor)}</h3>
            </div>
            <span className={`status-pill ${actorTone(actor)}`}>
              {actor.failed_events ? `${actor.failed_events} failed` : `${actor.events} events`}
            </span>
          </div>

          <div className="actor-card-meta">
            <div>
              <span>Total events</span>
              <strong>{actor.events}</strong>
            </div>
            <div>
              <span>Failures</span>
              <strong>{actor.failed_events}</strong>
            </div>
            <div>
              <span>Latest action</span>
              <strong>{actor.latest_action || "—"}</strong>
            </div>
          </div>
        </article>
      ))}
    </section>
  );
}