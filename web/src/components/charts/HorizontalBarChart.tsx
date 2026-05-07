"use client";

export type HorizontalBarDatum = {
  label: string;
  value: number;
  color?: string;
};

type HorizontalBarChartProps = {
  title: string;
  data: HorizontalBarDatum[];
  emptyLabel?: string;
  maxItems?: number;
};

export function HorizontalBarChart({
  title,
  data,
  emptyLabel = "No data available",
  maxItems = 8,
}: HorizontalBarChartProps) {
  const rows = [...data].filter((item) => item.value > 0).sort((a, b) => b.value - a.value).slice(0, maxItems);
  const maxValue = Math.max(1, ...rows.map((item) => item.value));

  return (
    <div className="chart-card">
      <div className="chart-heading">{title}</div>
      {rows.length ? (
        <div className="metric-bars">
          {rows.map((item) => (
            <div key={item.label} className="metric-bar-row">
              <div className="metric-bar-label" title={item.label}>{item.label}</div>
              <div className="metric-bar-track">
                <div
                  className="metric-bar-fill"
                  style={{
                    width: `${Math.max(5, (item.value / maxValue) * 100)}%`,
                    backgroundColor: item.color ?? "var(--chart-info)",
                  }}
                />
              </div>
              <div className="metric-bar-value">{item.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="chart-empty">{emptyLabel}</div>
      )}
    </div>
  );
}
