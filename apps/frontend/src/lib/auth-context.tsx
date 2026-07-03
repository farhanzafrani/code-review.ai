"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { API_URL } from "@/lib/config";
import type { User } from "@/lib/types";

const TOKEN_KEY = "codereviewai_token";

type Status = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  setToken: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function loginUrl(): string {
  return `${API_URL}/auth/github/login`;
}

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(readStoredToken);
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>(() =>
    readStoredToken() ? "loading" : "unauthenticated",
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .get<User>("/users/me", token)
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setStatus("authenticated");
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          window.localStorage.removeItem(TOKEN_KEY);
          setTokenState(null);
        }
        setStatus("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const setToken = useCallback((newToken: string) => {
    window.localStorage.setItem(TOKEN_KEY, newToken);
    setStatus("loading");
    setTokenState(newToken);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setTokenState(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, token, loading: status === "loading", setToken, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
