import { useEffect, useRef } from "react";

/** Calls `callback` every `intervalMs` while `enabled` is true. */
export function usePolling(callback: () => void, intervalMs: number, enabled: boolean) {
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => callbackRef.current(), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs, enabled]);
}
