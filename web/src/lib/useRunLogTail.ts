"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchRunLog } from "./api";

function shouldStickToBottom(element: HTMLElement, threshold = 48): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

type UseRunLogTailOptions = {
  pollMs?: number;
  tail?: number;
  enabled?: boolean;
};

export function useRunLogTail(runId: number | null, options: UseRunLogTailOptions = {}) {
  const pollMs = options.pollMs ?? 1000;
  const tail = options.tail ?? 5000;
  const enabled = options.enabled ?? true;
  const [log, setLog] = useState("");
  const logRef = useRef<HTMLPreElement | null>(null);
  const previousRunIdRef = useRef<number | null>(null);

  const setLogRef = useCallback((node: HTMLPreElement | null) => {
    logRef.current = node;
  }, []);

  useEffect(() => {
    if (runId === previousRunIdRef.current) {
      return;
    }
    previousRunIdRef.current = runId;
    setLog("");
  }, [runId]);

  useEffect(() => {
    if (!runId) return;

    let cancelled = false;

    const refresh = () => {
      fetchRunLog(runId, tail)
        .then((payload) => {
          if (cancelled) return;
          const next = payload.available ? payload.log : "";
          setLog((current) => {
            if (current === next) return current;
            return next;
          });
          const node = logRef.current;
          if (!node) return;
          const stick = shouldStickToBottom(node);
          requestAnimationFrame(() => {
            if (!logRef.current || !stick) return;
            logRef.current.scrollTop = logRef.current.scrollHeight;
          });
        })
        .catch(() => {
          // ignore transient log fetch errors while polling
        });
    };

    refresh();
    if (!enabled) {
      return () => {
        cancelled = true;
      };
    }
    const timer = window.setInterval(refresh, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runId, pollMs, tail, enabled]);

  return { log, setLogRef };
}
