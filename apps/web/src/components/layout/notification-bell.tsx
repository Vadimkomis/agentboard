"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "@/hooks/use-backend-token";
import type { Notification } from "@/lib/types";

export function NotificationBell() {
  const { token } = useBackendToken();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const { data: countData } = useQuery({
    queryKey: ["notification-count"],
    queryFn: () =>
      api.get<{ count: number }>("/api/notifications/unread-count", {
        token: token!,
      }),
    enabled: !!token,
    refetchInterval: 15000,
  });

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () =>
      api.get<Notification[]>("/api/notifications?limit=20", {
        token: token!,
      }),
    enabled: !!token && open,
  });

  const markAllRead = useMutation({
    mutationFn: () =>
      api.post("/api/notifications/read-all", {}, { token: token! }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["notification-count"] });
    },
  });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const unread = countData?.count || 0;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[var(--primary)] text-white text-[10px] flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-xl z-50">
          <div className="flex items-center justify-between p-3 border-b border-[var(--border)]">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                onClick={() => markAllRead.mutate()}
                className="text-xs text-[var(--primary)] hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications && notifications.length > 0 ? (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`p-3 border-b border-[var(--border)] last:border-0 ${
                    !n.read ? "bg-[var(--primary)]/5" : ""
                  }`}
                >
                  <p className="text-sm font-medium">{n.title}</p>
                  {n.body && (
                    <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                      {n.body}
                    </p>
                  )}
                  <p className="text-[10px] text-[var(--muted-foreground)] mt-1">
                    {new Date(n.created_at).toLocaleString()}
                  </p>
                </div>
              ))
            ) : (
              <div className="p-6 text-center text-sm text-[var(--muted-foreground)]">
                No notifications
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
