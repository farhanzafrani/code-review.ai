"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { PullRequest } from "@/lib/types";

const POLL_INTERVAL_MS = 4000;

export default function RepositoryPullRequestsPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [prs, setPrs] = useState<PullRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api
      .get<PullRequest[]>(`/repositories/${id}/pull-requests`, token)
      .then(setPrs)
      .catch(() => setError("Couldn't load pull requests."));
  }, [token, id]);

  useEffect(load, [load]);

  const hasInFlight = (prs ?? []).some(
    (pr) => pr.latest_review?.status === "pending" || pr.latest_review?.status === "running",
  );
  usePolling(load, POLL_INTERVAL_MS, hasInFlight);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <Link href="/dashboard" className="text-sm text-muted-foreground hover:underline">
          ← All repositories
        </Link>
        <h1 className="text-xl font-semibold">Pull requests</h1>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {prs === null ? (
        <Skeleton className="h-40 w-full" />
      ) : prs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No pull requests seen for this repository yet.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>PR</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Review</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {prs.map((pr) => (
              <TableRow key={pr.id}>
                <TableCell>
                  <a
                    href={pr.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-muted-foreground hover:underline"
                  >
                    #{pr.number}
                  </a>
                </TableCell>
                <TableCell>
                  <Link href={`/dashboard/pull-requests/${pr.id}`} className="hover:underline">
                    {pr.title}
                  </Link>
                </TableCell>
                <TableCell className="capitalize">{pr.state}</TableCell>
                <TableCell>
                  <StatusBadge status={pr.latest_review?.status ?? null} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
