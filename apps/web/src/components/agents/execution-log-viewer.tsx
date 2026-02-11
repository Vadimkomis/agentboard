"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "@/hooks/use-backend-token";
import { cn } from "@/lib/utils";
import type { ExecutionLog } from "@/lib/types";

const logTypeColors: Record<string, string> = {
  assistant: "text-white",
  tool_call: "text-blue-400",
  tool_result: "text-green-400",
  thinking: "text-gray-500",
  error: "text-red-400",
  system: "text-yellow-400",
};

export function ExecutionLogViewer({
  projectId,
  ticketId,
  executionId,
  isRunning,
}: {
  projectId: string;
  ticketId: string;
  executionId: string;
  isRunning: boolean;
}) {
  const { token } = useBackendToken();
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: logs } = useQuery({
    queryKey: ["execution-logs", executionId],
    queryFn: () =>
      api.get<ExecutionLog[]>(
        `/api/projects/${projectId}/tickets/${ticketId}/executions/${executionId}/logs`,
        { token: token! }
      ),
    enabled: !!token,
    refetchInterval: isRunning ? 2000 : false,
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="rounded-lg border border-[var(--border)] bg-black/80 p-4 font-mono text-xs max-h-96 overflow-y-auto">
      {logs?.map((log) => (
        <div key={log.id} className="mb-1">
          <span className="text-gray-600 mr-2">
            [{new Date(log.created_at).toLocaleTimeString()}]
          </span>
          <span className={cn("text-gray-500 mr-2", logTypeColors[log.log_type])}>
            [{log.log_type}]
          </span>
          <span className={logTypeColors[log.log_type] || "text-white"}>
            {log.content}
          </span>
        </div>
      ))}
      {isRunning && (
        <div className="flex items-center gap-2 mt-2 text-blue-400">
          <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
          Agent is running...
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
