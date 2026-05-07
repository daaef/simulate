/**
 * Time formatting utilities for user-friendly timestamps
 */

/**
 * Format a timestamp as relative time (e.g., "2 minutes ago", "Just now")
 */
export function formatRelativeTime(timestamp: string | null | undefined): string {
  if (!timestamp) return "—";
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  // Same minute
  if (diffSec < 60) {
    return "Just now";
  }
  
  // Same hour
  if (diffMin < 60) {
    return `${diffMin}m ago`;
  }
  
  // Same day
  if (diffHour < 24 && date.getDate() === now.getDate()) {
    return `Today at ${formatTime(date)}`;
  }
  
  // Yesterday
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.getDate() === yesterday.getDate() && 
      date.getMonth() === yesterday.getMonth() && 
      date.getFullYear() === yesterday.getFullYear()) {
    return `Yesterday at ${formatTime(date)}`;
  }
  
  // Within 7 days
  if (diffDay < 7) {
    return `${diffDay} days ago`;
  }
  
  // Older - show date
  return formatDate(date);
}

/**
 * Format a date as readable string (e.g., "May 4, 3:45 PM")
 */
export function formatDate(date: Date): string {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const month = months[date.getMonth()];
  const day = date.getDate();
  const year = date.getFullYear();
  const time = formatTime(date);
  
  const currentYear = new Date().getFullYear();
  if (year !== currentYear) {
    return `${month} ${day}, ${year} at ${time}`;
  }
  
  return `${month} ${day} at ${time}`;
}

/**
 * Format time only (e.g., "3:45 PM")
 */
export function formatTime(date: Date): string {
  let hours = date.getHours();
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const ampm = hours >= 12 ? "PM" : "AM";
  
  hours = hours % 12;
  hours = hours ? hours : 12; // 0 should be 12
  
  return `${hours}:${minutes} ${ampm}`;
}

/**
 * Format duration in seconds/milliseconds to readable string
 * e.g., "2m 34s", "1h 5m", "45s"
 */
export function formatDuration(startMs: number | null | undefined, endMs: number | null | undefined): string {
  if (startMs == null || endMs == null) return "—";
  
  const diffSec = Math.floor((endMs - startMs) / 1000);
  
  if (diffSec < 60) {
    return `${diffSec}s`;
  }
  
  const minutes = Math.floor(diffSec / 60);
  const seconds = diffSec % 60;
  
  if (minutes < 60) {
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  if (remainingMinutes > 0) {
    return `${hours}h ${remainingMinutes}m`;
  }
  
  return `${hours}h`;
}

/**
 * Parse ISO timestamp to milliseconds
 */
export function parseTimestamp(timestamp: string | null | undefined): number | null {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return isNaN(date.getTime()) ? null : date.getTime();
}

/**
 * Format run duration from start and end timestamps
 */
export function formatRunDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined
): string {
  const startMs = parseTimestamp(startedAt);
  const endMs = parseTimestamp(finishedAt) ?? Date.now();
  return formatDuration(startMs, endMs);
}

export function formatDateTime(
  timestamp: string | null | undefined,
  options?: { timeZone?: string; fallback?: string }
): string {
  if (!timestamp) return options?.fallback ?? "—";
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return options?.fallback ?? "—";

  const formatOptions: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  };

  try {
    return new Intl.DateTimeFormat(undefined, {
      ...formatOptions,
      timeZone: options?.timeZone || undefined,
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, formatOptions).format(date);
  }
}

export function formatTimeUntil(timestamp: string | null | undefined): string {
  if (!timestamp) return "No automatic trigger";
  const targetMs = parseTimestamp(timestamp);
  if (targetMs == null) return "Trigger time unavailable";

  const diffMs = targetMs - Date.now();
  if (diffMs <= 0) return "Due now";

  const totalMinutes = Math.ceil(diffMs / 60000);
  if (totalMinutes < 60) return totalMinutes <= 1 ? "in 1m" : `in ${totalMinutes}m`;

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours < 24) return minutes ? `in ${hours}h ${minutes}m` : `in ${hours}h`;

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  if (days < 14) return remainingHours ? `in ${days}d ${remainingHours}h` : `in ${days}d`;

  return `in ${days}d`;
}
