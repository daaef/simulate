"use client";

interface HeatmapDataPoint {
  timeBucket: string; // e.g., "0-10s", "10-20s"
  actor: string; // e.g., "user", "store", "robot", "trace"
  activity: number; // 0-100 intensity
}

interface ActorHeatmapProps {
  data: HeatmapDataPoint[];
  actors: string[];
  timeBuckets: string[];
}

/**
 * Activity heatmap showing actor activity over time
 */
export function ActorHeatmap({ data, actors, timeBuckets }: ActorHeatmapProps) {
  if (data.length === 0 || actors.length === 0 || timeBuckets.length === 0) {
    return <div className="chart-empty">No activity data available</div>;
  }

  const getActivityLevel = (actor: string, bucket: string) => {
    const point = data.find((d) => d.actor === actor && d.timeBucket === bucket);
    return point?.activity || 0;
  };

  const getColor = (activity: number) => {
    // Green gradient from light to dark based on activity
    const intensity = Math.min(activity / 100, 1);
    const r = Math.round(34 + (74 - 34) * (1 - intensity));
    const g = Math.round(197 + (222 - 197) * (1 - intensity));
    const b = Math.round(94 + (128 - 94) * (1 - intensity));
    return `rgb(${r}, ${g}, ${b})`;
  };

  return (
    <div className="chart-container heatmap-chart">
      <h4 className="chart-title">Actor Activity Timeline</h4>
      <div className="heatmap-wrapper">
        {/* Y-axis labels (actors) */}
        <div className="heatmap-actors">
          {actors.map((actor) => (
            <div key={actor} className="heatmap-actor-label">
              {actor}
            </div>
          ))}
        </div>

        {/* Heatmap grid */}
        <div className="heatmap-grid">
          {/* X-axis labels (time) */}
          <div className="heatmap-time-header">
            {timeBuckets.map((bucket) => (
              <div key={bucket} className="heatmap-time-label">
                {bucket}
              </div>
            ))}
          </div>

          {/* Grid cells */}
          {actors.map((actor) => (
            <div key={actor} className="heatmap-row">
              {timeBuckets.map((bucket) => {
                const activity = getActivityLevel(actor, bucket);
                return (
                  <div
                    key={`${actor}-${bucket}`}
                    className="heatmap-cell"
                    style={{
                      backgroundColor: getColor(activity),
                      opacity: activity > 0 ? 0.3 + (activity / 100) * 0.7 : 0.1,
                    }}
                    title={`${actor} at ${bucket}: ${activity}% active`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="heatmap-legend">
        <span>Low</span>
        <div className="heatmap-gradient" />
        <span>High</span>
      </div>
    </div>
  );
}
