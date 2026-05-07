"use client";

interface TimelineEvent {
  timestamp: number;
  label: string;
  category: "scenario" | "http" | "websocket" | "actor";
  status?: "success" | "error" | "pending";
  duration?: number;
}

interface EventTimelineProps {
  events: TimelineEvent[];
  startTime: number;
  endTime: number;
}

/**
 * Horizontal timeline showing events during a run
 */
export function EventTimeline({ events, startTime, endTime }: EventTimelineProps) {
  const duration = endTime - startTime;
  
  if (duration <= 0 || events.length === 0) {
    return <div className="chart-empty">No timeline data available</div>;
  }

  const getPosition = (timestamp: number) => {
    const offset = timestamp - startTime;
    return (offset / duration) * 100;
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case "scenario": return "var(--chart-success)";
      case "http": return "var(--chart-info)";
      case "websocket": return "var(--chart-purple)";
      case "actor": return "var(--chart-warning)";
      default: return "var(--chart-axis)";
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className="chart-container timeline-chart">
      <h4 className="chart-title">Event Timeline</h4>
      <div className="timeline-wrapper">
        {/* Time scale */}
        <div className="timeline-scale">
          {[0, 25, 50, 75, 100].map((percent) => (
            <span key={percent} className="timeline-tick" style={{ left: `${percent}%` }}>
              {formatDuration((duration * percent) / 100)}
            </span>
          ))}
        </div>
        
        {/* Timeline bar */}
        <div className="timeline-bar">
          {events.map((event, index) => (
            <div
              key={index}
              className={`timeline-event ${event.status || ""}`}
              style={{
                left: `${getPosition(event.timestamp)}%`,
                backgroundColor: getCategoryColor(event.category),
              }}
              title={`${event.label} (${formatDuration(event.duration || 0)})`}
            >
              <span className="event-label">{event.label}</span>
            </div>
          ))}
        </div>
        
        {/* Legend */}
        <div className="timeline-legend">
          {["scenario", "http", "websocket", "actor"].map((cat) => (
            <span key={cat} className="legend-item">
              <span 
                className="legend-color" 
                style={{ backgroundColor: getCategoryColor(cat) }}
              />
              {cat}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
