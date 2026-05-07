"use client";

interface LatencyDataPoint {
  endpoint: string;
  latency: number;
  status: number;
  count: number;
}

interface LatencyBarChartProps {
  data: LatencyDataPoint[];
}

/**
 * Vertical bar chart showing HTTP latency by endpoint
 */
export function LatencyBarChart({ data }: LatencyBarChartProps) {
  if (data.length === 0) {
    return <div className="chart-empty">No latency data available</div>;
  }

  // Sort by latency descending
  const sortedData = [...data].sort((a, b) => b.latency - a.latency).slice(0, 20);
  const maxLatency = Math.max(...sortedData.map((d) => d.latency));

  const getStatusColor = (status: number) => {
    if (status >= 200 && status < 300) return "var(--chart-success)";
    if (status >= 300 && status < 400) return "var(--chart-warning)";
    if (status >= 400 && status < 500) return "var(--chart-danger)";
    return "var(--chart-danger)";
  };

  return (
    <div className="chart-container bar-chart">
      <h4 className="chart-title">HTTP Latency by Endpoint</h4>
      <div className="chart-scroll">
        <div className="bar-chart-content">
          {sortedData.map((item, index) => (
            <div key={index} className="bar-row">
              <span className="bar-label" title={item.endpoint}>
                {item.endpoint.length > 30
                  ? item.endpoint.substring(0, 27) + "..."
                  : item.endpoint}
              </span>
              <div className="bar-wrapper">
                <div
                  className="bar"
                  style={{
                    width: `${(item.latency / maxLatency) * 100}%`,
                    backgroundColor: getStatusColor(item.status),
                  }}
                  title={`${item.endpoint}: ${item.latency.toFixed(0)}ms (${item.status})`}
                />
              </div>
              <span className="bar-value">{item.latency.toFixed(0)}ms</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
