"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { loginUrl, useAuth } from "@/lib/auth-context";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>AI Code Review & DevOps Assistant</CardTitle>
          <CardDescription>
            Sign in to connect a repo and watch AI reviews land on your pull requests.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            render={<a href={loginUrl()} />}
            nativeButton={false}
            className="w-full"
            disabled={loading}
          >
            Sign in with GitHub
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
