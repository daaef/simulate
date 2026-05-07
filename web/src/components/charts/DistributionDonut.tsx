"use client";

export type DistributionDatum = {
  label: string;
  value: number;
  color?: string;
};

const DEFAULT_COLORS = [
  "var(--chart-success)",
  "var(--chart-danger)",
  "var(--chart-warning)",
  "var(--chart-info)",
  "var(--chart-purple)",
];

type DistributionDonutProps = {
  title: string;
  data: DistributionDatum[];
  emptyLabel?: string;
};

export function DistributionDonut({ title, data, emptyLabel = "No data available" }: DistributionDonutProps) {
  const filtered = data.filter((item) => item.value > 0);
  const total = filtered.reduce((sum, item) => sum + item.value, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let cumulative = 0;

  return (
    <div className="chart-card">
      <div className="chart-heading">{title}</div>
      {total > 0 ? (
        <div className="donut-layout">
          <svg className="donut-svg" width="132" height="132" viewBox="0 0 132 132" role="img" aria-label={title}>
            <circle cx="66" cy="66" r={radius} fill="none" stroke="var(--chart-muted-fill)" strokeWidth="16" />
            {filtered.map((item, index) => {
              const segment = (item.value / total) * circumference;
              const offset = -(cumulative / total) * circumference;
              cumulative += item.value;
              return (
                <circle
                  key={item.label}
                  cx="66"
                  cy="66"
                  r={radius}
                  fill="none"
                  stroke={item.color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
                  strokeWidth="16"
                  strokeDasharray={`${segment} ${circumference - segment}`}
                  strokeDashoffset={offset}
                  strokeLinecap="butt"
                  transform="rotate(-90 66 66)"
                />
              );
            })}
            <text x="66" y="62" textAnchor="middle" className="donut-total">
              {total}
            </text>
            <text x="66" y="80" textAnchor="middle" className="donut-caption">
              total
            </text>
          </svg>
          <div className="chart-legend">
            {filtered.map((item, index) => (
              <div key={item.label} className="legend-row">
                <span
                  className="legend-swatch"
                  style={{ backgroundColor: item.color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length] }}
                />
                <span className="legend-label">{item.label}</span>
                <span className="legend-value">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="chart-empty">{emptyLabel}</div>
      )}
    </div>
  );
}
