"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Notification } from "@/lib/types";

const POLL_INTERVAL_MS = 15000;

export function NotificationBell() {
  const { token } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    if (!token) return;
    api
      .get<Notification[]>("/notifications", token)
      .then(setNotifications)
      .catch(() => {});
  }, [token]);

  useEffect(load, [load]);
  usePolling(load, POLL_INTERVAL_MS, !!token);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markRead = (id: number) => {
    if (!token) return;
    api
      .post(`/notifications/${id}/read`, token)
      .then(() =>
        setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n))),
      )
      .catch(() => {});
  };

  const markAllRead = () => {
    if (!token) return;
    api
      .post("/notifications/read-all", token)
      .then(() => setNotifications((prev) => prev.map((n) => ({ ...n, read: true }))))
      .catch(() => {});
  };

  return (
    <div className="relative" ref={containerRef}>
      <Button variant="outline" size="sm" className="relative" onClick={() => setOpen((o) => !o)}>
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full bg-red-600 text-[10px] text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </Button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-md border bg-popover shadow-md">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-medium">Notifications</span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="text-xs text-muted-foreground hover:underline"
                onClick={markAllRead}
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">No notifications yet.</p>
            ) : (
              notifications.map((n) => {
                const body = (
                  <div
                    className={`border-b px-3 py-2 text-sm last:border-b-0 ${
                      n.read ? "text-muted-foreground" : "font-medium"
                    }`}
                    onClick={() => !n.read && markRead(n.id)}
                  >
                    {n.message}
                  </div>
                );
                return n.pull_request_id ? (
                  <Link
                    key={n.id}
                    href={`/dashboard/pull-requests/${n.pull_request_id}`}
                    onClick={() => setOpen(false)}
                    className="block hover:bg-muted/50"
                  >
                    {body}
                  </Link>
                ) : (
                  <div key={n.id} className="hover:bg-muted/50">
                    {body}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
