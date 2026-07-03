"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  if (loading || !user) {
    return <main className="flex flex-1 items-center justify-center p-8" />;
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <Link href="/dashboard" className="font-semibold">
          CodeReviewAI
        </Link>
        <div className="flex items-center gap-3">
          <Avatar className="size-7">
            <AvatarImage src={user.avatar_url ?? undefined} alt={user.github_login} />
            <AvatarFallback>{user.github_login.slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <span className="text-sm text-muted-foreground">{user.github_login}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              logout();
              router.replace("/");
            }}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
