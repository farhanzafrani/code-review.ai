"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Repository } from "@/lib/types";

const GITHUB_APP_SLUG = process.env.NEXT_PUBLIC_GITHUB_APP_SLUG;

function installUrl(): string | null {
  return GITHUB_APP_SLUG ? `https://github.com/apps/${GITHUB_APP_SLUG}/installations/new` : null;
}

export default function DashboardPage() {
  const { token } = useAuth();
  const [repos, setRepos] = useState<Repository[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api
      .get<Repository[]>("/repositories", token)
      .then(setRepos)
      .catch(() => setError("Couldn't load repositories."));
  }, [token]);

  useEffect(load, [load]);

  async function disconnect(id: number) {
    if (!token) return;
    await api.del(`/repositories/${id}`, token);
    load();
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Connected repositories</h1>
          <p className="text-sm text-muted-foreground">
            Repos the GitHub App is installed on. Every PR gets an AI review automatically.
          </p>
        </div>
        {installUrl() ? (
          <Button render={<a href={installUrl()!} />} nativeButton={false}>
            Connect a repo
          </Button>
        ) : null}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {repos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : repos.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No repositories connected yet</CardTitle>
            <CardDescription>
              Install the GitHub App on a repository to start getting AI reviews on its PRs.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {repos.map((repo) => (
            <Card key={repo.id}>
              <CardHeader>
                <CardTitle className="text-base">
                  <Link href={`/dashboard/repositories/${repo.id}`} className="hover:underline">
                    {repo.full_name}
                  </Link>
                </CardTitle>
                <CardAction>
                  <Button variant="outline" size="sm" onClick={() => disconnect(repo.id)}>
                    Disconnect
                  </Button>
                </CardAction>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
