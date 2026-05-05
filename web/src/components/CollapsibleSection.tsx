"use client";

import { useEffect, useState, ReactNode } from "react";

interface CollapsibleSectionProps {
  title?: string;
  children: ReactNode;
  defaultExpanded?: boolean;
  storageKey?: string;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
}

/**
 * Collapsible section with persistent state in localStorage
 */
export function CollapsibleSection({
  title,
  children,
  defaultExpanded = true,
  storageKey,
  className = "",
  headerClassName = "",
  contentClassName = "",
}: CollapsibleSectionProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [isMounted, setIsMounted] = useState(false);

  // Load persisted state on mount
  useEffect(() => {
    setIsMounted(true);
    if (storageKey) {
      const stored = localStorage.getItem(`collapsible_${storageKey}`);
      if (stored !== null) {
        setIsExpanded(stored === "true");
      }
    }
  }, [storageKey]);

  // Persist state on change
  useEffect(() => {
    if (storageKey && isMounted) {
      localStorage.setItem(`collapsible_${storageKey}`, String(isExpanded));
    }
  }, [isExpanded, storageKey, isMounted]);

  const toggle = () => setIsExpanded(!isExpanded);

  return (
    <div className={`collapsible-section ${className}`}>
      {title && (
        <div 
          className={`collapsible-header ${headerClassName}`}
          onClick={toggle}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              toggle();
            }
          }}
        >
          <span className="collapsible-title">{title}</span>
          <span className={`collapsible-icon ${isExpanded ? "expanded" : ""}`}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 6L8 10L12 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </div>
      )}
      <div className={`collapsible-content ${isExpanded ? "expanded" : ""} ${contentClassName}`}>
        {children}
      </div>
    </div>
  );
}
