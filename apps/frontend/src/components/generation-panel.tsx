"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { GenerationResult } from "@/lib/types";

export function GenerationPanel({
  pullRequestId,
  action,
  label,
}: {
  pullRequestId: number;
  action: "generate-tests" | "generate-docs";
  label: string;
}) {
  const { token } = useAuth();
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.post<GenerationResult>(
        `/pull-requests/${pullRequestId}/${action}`,
        token,
      );
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Generation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">{label}</CardTitle>
        <Button size="sm" onClick={run} disabled={loading}>
          {loading ? "Generating…" : result ? "Regenerate" : "Generate"}
        </Button>
      </CardHeader>
      {(result || error) && (
        <CardContent className="flex flex-col gap-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {result && (
            <>
              <p className="text-sm text-muted-foreground">{result.notes}</p>
              {result.files.length === 0
                ? null
                : result.files.map((file, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <code className="text-xs text-muted-foreground">{file.filename}</code>
                      <pre className="max-h-96 overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-5 whitespace-pre">
                        {file.content}
                      </pre>
                    </div>
                  ))}
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
