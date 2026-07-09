"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { DiffView } from "@/components/diff-view";
import { GenerationPanel } from "@/components/generation-panel";
import { LogsPanel } from "@/components/logs-panel";
import { QualityGateBadge } from "@/components/quality-gate-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
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
  const sonarStatus = pr?.latest_review?.sonar_status ?? null;
  const inFlight = (s: typeof status) => s === "pending" || s === "running";
  usePolling(loadPr, POLL_INTERVAL_MS, inFlight(status) || inFlight(sonarStatus));

  const review = pr?.latest_review ?? null;
  const bugs = review?.raw_result?.bugs ?? [];
  const securityIssues = review?.raw_result?.security_issues ?? [];
  const sonarIssues = review?.sonar_result?.issues ?? [];

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

      {pr && <LogsPanel pullRequestId={pr.id} active={inFlight(status) || inFlight(sonarStatus)} />}

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
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Bugs ({bugs.length})</h3>
              {bugs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No bugs found in this diff.</p>
              ) : (
                <div className="flex flex-col gap-3">
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
            </div>
            <Separator />
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">🔒 Security ({securityIssues.length})</h3>
              {securityIssues.length === 0 ? (
                <p className="text-sm text-muted-foreground">No security issues found.</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {securityIssues.map((issue, i) => (
                    <div
                      key={i}
                      className="flex flex-col gap-1 rounded-md border border-destructive/30 p-3"
                    >
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={issue.severity} />
                        <Badge variant="outline">{issue.category}</Badge>
                        <code className="text-xs text-muted-foreground">{issue.file}</code>
                      </div>
                      <p className="text-sm">{issue.description}</p>
                      <p className="text-sm text-muted-foreground">
                        <span className="font-medium">Recommendation:</span> {issue.recommendation}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {sonarStatus && (
        <Card>
          <CardHeader>
            <CardTitle>🛡️ SonarQube</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {sonarStatus === "pending" || sonarStatus === "running" ? (
              <p className="text-sm text-muted-foreground">Scan in progress…</p>
            ) : sonarStatus === "failed" ? (
              <p className="text-sm text-destructive">
                Scan failed: {review?.sonar_result?.error}
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">Quality Gate:</span>
                  <QualityGateBadge status={review?.sonar_quality_gate ?? "NONE"} />
                </div>
                {sonarIssues.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No open issues.</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-medium">Issues ({sonarIssues.length})</h3>
                    {sonarIssues.map((issue, i) => (
                      <div key={i} className="rounded-md border p-3 text-sm">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{issue.severity}</Badge>
                          <code className="text-xs text-muted-foreground">
                            {issue.component}
                            {issue.line ? `:${issue.line}` : ""}
                          </code>
                        </div>
                        <p className="mt-1">{issue.message}</p>
                      </div>
                    ))}
                  </div>
                )}
              </>
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

      {pr && (
        <>
          <GenerationPanel pullRequestId={pr.id} action="generate-tests" label="Unit tests" />
          <GenerationPanel pullRequestId={pr.id} action="generate-docs" label="Documentation" />
        </>
      )}
    </div>
  );
}
