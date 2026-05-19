"use client";

import { useEffect, useState } from "react";

interface LastUpdatedIndicatorProps {
  updatedAt: Date | null;
  onRefresh?: () => void;
  refreshLabel?: string;
  className?: string;
}

function formatAgo(seconds: number): string {
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function LastUpdatedIndicator({
  updatedAt,
  onRefresh,
  refreshLabel = "Refresh",
  className = "",
}: LastUpdatedIndicatorProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const secondsAgo = updatedAt
    ? Math.max(0, Math.floor((Date.now() - updatedAt.getTime()) / 1000))
    : null;

  void tick;

  return (
    <div className={`last-updated ${className}`.trim()}>
      <span className="last-updated__label muted">
        {updatedAt ? `Updated ${formatAgo(secondsAgo ?? 0)}` : "Not loaded yet"}
      </span>
      {onRefresh ? (
        <button type="button" className="secondary small last-updated__refresh" onClick={onRefresh}>
          {refreshLabel}
        </button>
      ) : null}
    </div>
  );
}
