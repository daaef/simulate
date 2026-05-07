"use client";

type SparklineProps = {
  title: string;
  points: number[];
  labels?: string[];
  emptyLabel?: string;
};

export function Sparkline({ title, points, labels = [], emptyLabel = "No trend data available" }: SparklineProps) {
  const values = points.filter((point) => Number.isFinite(point));
  const width = 360;
  const height = 120;
  const padding = 12;
  const max = Math.max(1, ...values);
  const min = Math.min(0, ...values);
  const span = Math.max(1, max - min);

  const polyline = values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : padding + (index / (values.length - 1)) * (width - padding * 2);
      const y = height - padding - ((value - min) / span) * (height - padding * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="chart-card">
      <div className="chart-heading">{title}</div>
      {values.length ? (
        <div className="sparkline-wrap">
          <svg className="sparkline-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
            <line x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} className="sparkline-grid" />
            <polyline points={polyline} fill="none" className="sparkline-line" />
            {values.map((value, index) => {
              const x = values.length === 1 ? width / 2 : padding + (index / (values.length - 1)) * (width - padding * 2);
              const y = height - padding - ((value - min) / span) * (height - padding * 2);
              return <circle key={`${index}-${value}`} cx={x} cy={y} r="3" className="sparkline-point" />;
            })}
          </svg>
          <div className="sparkline-meta">
            <span>{labels[0] ?? "oldest"}</span>
            <strong>{values.reduce((sum, item) => sum + item, 0)} total</strong>
            <span>{labels[labels.length - 1] ?? "latest"}</span>
          </div>
        </div>
      ) : (
        <div className="chart-empty">{emptyLabel}</div>
      )}
    </div>
  );
}
