"use client";

import type { ReactNode } from "react";

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  details?: ReactNode;
  className?: string;
}

export function ErrorBanner({
  message,
  onRetry,
  retryLabel = "Retry",
  details,
  className = "",
}: ErrorBannerProps) {
  return (
    <div className={`error-banner error-banner--actionable ${className}`.trim()} role="alert">
      <div className="error-banner__body">
        <div>{message}</div>
        {onRetry ? (
          <button type="button" className="secondary small error-banner__retry" onClick={onRetry}>
            {retryLabel}
          </button>
        ) : null}
      </div>
      {details ? <div className="error-banner__details">{details}</div> : null}
    </div>
  );
}
