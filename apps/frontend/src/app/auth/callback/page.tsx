"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export default function AuthCallbackPage() {
  const router = useRouter();
  const { setToken } = useAuth();

  useEffect(() => {
    // A URL fragment (#token=...), not a query param — the backend sends
    // it this way so the token is never sent to any server (this page's
    // own load included) and can't land in access logs or browser history.
    // Fragments aren't visible to useSearchParams() (query string only),
    // so read window.location.hash directly.
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (token) {
      setToken(token);
      router.replace("/dashboard");
    } else {
      router.replace("/");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <p className="text-sm text-muted-foreground">Signing you in…</p>
    </main>
  );
}
