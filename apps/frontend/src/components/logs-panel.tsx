"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 3000;

export function LogsPanel({ pullRequestId, active }: { pullRequestId: number; active: boolean }) {
  const { token } = useAuth();
  const [lines, setLines] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    if (!token) return;
    api
      .get<{ lines: string[] }>(`/pull-requests/${pullRequestId}/logs`, token)
      .then((res) => setLines(res.lines))
      .catch(() => {});
  }, [token, pullRequestId]);

  useEffect(load, [load]);
  usePolling(load, POLL_INTERVAL_MS, active);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines]);

  if (lines.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Pipeline logs</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          ref={scrollRef}
          className="max-h-56 overflow-y-auto rounded-md bg-muted/50 p-3 font-mono text-xs leading-relaxed"
        >
          {lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
