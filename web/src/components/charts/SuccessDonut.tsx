"use client";

interface SuccessData {
  httpSuccess: number;
  httpFailed: number;
  wsSuccess: number;
  wsFailed: number;
  scenariosPassed: number;
  scenariosFailed: number;
}

interface SuccessDonutProps {
  data: SuccessData;
}

/**
 * Donut chart showing success/failure breakdown
 */
export function SuccessDonut({ data }: SuccessDonutProps) {
  const totalHttp = data.httpSuccess + data.httpFailed;
  const totalWs = data.wsSuccess + data.wsFailed;
  const totalScenarios = data.scenariosPassed + data.scenariosFailed;

  // Calculate percentages
  const httpSuccessPct = totalHttp > 0 ? (data.httpSuccess / totalHttp) * 100 : 0;
  const wsSuccessPct = totalWs > 0 ? (data.wsSuccess / totalWs) * 100 : 0;
  const scenarioSuccessPct =
    totalScenarios > 0 ? (data.scenariosPassed / totalScenarios) * 100 : 0;

  const DonutSegment = ({
    percentage,
    color,
    label,
  }: {
    percentage: number;
    color: string;
    label: string;
  }) => {
    const radius = 40;
    const circumference = 2 * Math.PI * radius;
    const strokeDasharray = circumference;
    const strokeDashoffset = circumference - (percentage / 100) * circumference;

    return (
      <div className="donut-segment">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="var(--border-primary)"
            strokeWidth="10"
          />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray={strokeDasharray}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform="rotate(-90 50 50)"
          />
          <text
            x="50"
            y="50"
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="14"
            fontWeight="bold"
            fill="var(--text-secondary)"
          >
            {percentage.toFixed(0)}%
          </text>
        </svg>
        <span className="donut-label">{label}</span>
      </div>
    );
  };

  return (
    <div className="chart-container donut-chart">
      <h4 className="chart-title">Success Rate</h4>
      <div className="donut-grid">
        <DonutSegment
          percentage={httpSuccessPct}
          color="var(--chart-success)"
          label={`HTTP (${data.httpSuccess}/${totalHttp})`}
        />
        <DonutSegment
          percentage={wsSuccessPct}
          color="var(--chart-info)"
          label={`WebSocket (${data.wsSuccess}/${totalWs})`}
        />
        <DonutSegment
          percentage={scenarioSuccessPct}
          color="var(--chart-purple)"
          label={`Scenarios (${data.scenariosPassed}/${totalScenarios})`}
        />
      </div>
    </div>
  );
}
