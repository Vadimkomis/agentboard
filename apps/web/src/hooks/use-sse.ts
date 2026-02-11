"use client";

import { useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SSEEvent = {
  type: string;
  data: Record<string, unknown>;
};

export function useSSE(
  projectId: string | null,
  token: string | null,
  onEvent: (event: SSEEvent) => void
) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!projectId || !token) return;

    const url = `${API_BASE}/api/events/projects/${projectId}?token=${token}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      if (!event.data) return;
      try {
        const parsed = JSON.parse(event.data) as SSEEvent;
        onEventRef.current(parsed);
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      es.close();
      // Auto-reconnect after 3 seconds
      setTimeout(() => {
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null;
        }
      }, 3000);
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [projectId, token]);
}
