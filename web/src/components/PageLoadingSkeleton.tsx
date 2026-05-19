"use client";

interface PageLoadingSkeletonProps {
  statCount?: number;
  panelCount?: number;
}

export function PageLoadingSkeleton({ statCount = 4, panelCount = 2 }: PageLoadingSkeletonProps) {
  return (
    <div className="page-loading-skeleton" aria-busy="true" aria-label="Loading">
      <div className={`grid ${statCount >= 4 ? "four" : statCount === 3 ? "three" : "two"}`}>
        {Array.from({ length: statCount }).map((_, index) => (
          <article key={index} className="panel stat skeleton-stat">
            <div className="skeleton-line skeleton-line--short" />
            <div className="skeleton-line skeleton-line--tall" />
          </article>
        ))}
      </div>
      <div className={`grid ${panelCount >= 2 ? "two" : "one"}`}>
        {Array.from({ length: panelCount }).map((_, index) => (
          <article key={index} className="panel skeleton-panel">
            <div className="skeleton-line skeleton-line--medium" />
            <div className="skeleton-line" />
            <div className="skeleton-line" />
            <div className="skeleton-line skeleton-line--short" />
          </article>
        ))}
      </div>
    </div>
  );
}
