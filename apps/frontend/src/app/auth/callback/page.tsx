"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

function CallbackInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { setToken } = useAuth();

  useEffect(() => {
    const token = params.get("token");
    if (token) {
      setToken(token);
      router.replace("/dashboard");
    } else {
      router.replace("/");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return <p className="text-sm text-muted-foreground">Signing you in…</p>;
}

export default function AuthCallbackPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-8">
      <Suspense fallback={<p className="text-sm text-muted-foreground">Signing you in…</p>}>
        <CallbackInner />
      </Suspense>
    </main>
  );
}
