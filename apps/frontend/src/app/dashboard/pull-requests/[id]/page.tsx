"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { DiffView } from "@/components/diff-view";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { PullRequestDetail } from "@/lib/types";

const POLL_INTERVAL_MS = 4000;

export default function PullRequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [pr, setPr] = useState<PullRequestDetail | null>(null);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPr = useCallback(() => {
    if (!token) return;
    api
      .get<PullRequestDetail>(`/pull-requests/${id}`, token)
      .then(setPr)
      .catch(() => setError("Couldn't load this pull request."));
  }, [token, id]);

  useEffect(loadPr, [loadPr]);

  useEffect(() => {
    if (!token) return;
    api
      .get<string>(`/pull-requests/${id}/diff`, token)
      .then(setDiff)
      .catch(() => setDiff(null));
  }, [token, id]);

  const status = pr?.latest_review?.status ?? null;
  usePolling(loadPr, POLL_INTERVAL_MS, status === "pending" || status === "running");

  const review = pr?.latest_review ?? null;
  const bugs = review?.raw_result?.bugs ?? [];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        {pr && (
          <Link
            href={`/dashboard/repositories/${pr.repository_id}`}
            className="text-sm text-muted-foreground hover:underline"
          >
            ← {pr.repository_full_name}
          </Link>
        )}
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{pr ? pr.title : <Skeleton className="h-6 w-64" />}</h1>
          {status && <StatusBadge status={status} />}
        </div>
        {pr && (
          <a
            href={pr.html_url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-muted-foreground hover:underline"
          >
            View PR #{pr.number} on GitHub
          </a>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!pr ? (
        <Skeleton className="h-40 w-full" />
      ) : !review || review.status === "pending" || review.status === "running" ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            AI review in progress — this updates automatically.
          </CardContent>
        </Card>
      ) : review.status === "failed" ? (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-destructive">Review failed</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">{review.summary}</CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-sm">{review.summary}</p>
            <Separator />
            {bugs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No issues found in this diff.</p>
            ) : (
              <div className="flex flex-col gap-4">
                {bugs.map((bug, i) => (
                  <div key={i} className="flex flex-col gap-1 rounded-md border p-3">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={bug.severity} />
                      <code className="text-xs text-muted-foreground">{bug.file}</code>
                    </div>
                    <p className="text-sm">{bug.description}</p>
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium">Suggested fix:</span> {bug.suggestion}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {diff && (
        <Card>
          <CardHeader>
            <CardTitle>Diff</CardTitle>
          </CardHeader>
          <CardContent>
            <DiffView diff={diff} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
