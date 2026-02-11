"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { usePlanningStore } from "@/lib/planning-store";
import {
  usePlanningMessages,
  useSendPlanningMessage,
  useFinalizePlan,
} from "@/hooks/use-planning";
import { toast } from "sonner";

export function PlanningChat({
  projectId,
  ticketId,
}: {
  projectId: string;
  ticketId: string;
}) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { data: messages, isLoading } = usePlanningMessages(projectId, ticketId);
  const sendMessage = useSendPlanningMessage(projectId, ticketId);
  const finalize = useFinalizePlan(projectId, ticketId);
  const streamingMessages = usePlanningStore((s) => s.streamingMessages);

  const isStreaming = messages?.some((m) => m.is_streaming) ||
    Object.keys(streamingMessages).length > 0;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessages]);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || isStreaming) return;
    setInput("");
    try {
      await sendMessage.mutateAsync(content);
    } catch {
      toast.error("Failed to send message");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFinalize = async () => {
    try {
      await finalize.mutateAsync();
      toast.success("Plan finalized");
    } catch {
      toast.error("Failed to finalize plan");
    }
  };

  const hasAssistantMessage = messages?.some((m) => m.role === "assistant");

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 mb-4 min-h-0">
        {isLoading && (
          <div className="flex justify-center py-4">
            <div className="w-5 h-5 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {messages?.map((msg) => {
          const streamContent = streamingMessages[msg.id];
          const displayContent = msg.is_streaming && streamContent
            ? streamContent
            : msg.content;

          return (
            <div
              key={msg.id}
              className={cn(
                "flex",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                  msg.role === "user"
                    ? "bg-[var(--primary)] text-white"
                    : "bg-[var(--secondary)] text-[var(--secondary-foreground)]"
                )}
              >
                <div className="whitespace-pre-wrap break-words">
                  {displayContent || (
                    <span className="inline-flex items-center gap-1 text-[var(--muted-foreground)]">
                      <span className="w-1.5 h-1.5 bg-current rounded-full animate-pulse" />
                      <span className="w-1.5 h-1.5 bg-current rounded-full animate-pulse [animation-delay:150ms]" />
                      <span className="w-1.5 h-1.5 bg-current rounded-full animate-pulse [animation-delay:300ms]" />
                    </span>
                  )}
                </div>
                {msg.is_streaming && streamContent && (
                  <span className="inline-block w-1.5 h-4 bg-current opacity-70 animate-pulse ml-0.5 align-text-bottom" />
                )}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-[var(--border)] pt-3 space-y-2">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Reply to PM agent..."
            disabled={isStreaming || sendMessage.isPending}
            rows={2}
            className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-[var(--primary)] disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming || sendMessage.isPending}
            className="self-end px-3 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            Send
          </button>
        </div>
        {hasAssistantMessage && !isStreaming && (
          <button
            onClick={handleFinalize}
            disabled={finalize.isPending}
            className="w-full px-4 py-2.5 rounded-lg border border-[var(--primary)] text-[var(--primary)] text-sm font-medium hover:bg-[var(--primary)] hover:text-white transition-colors disabled:opacity-50"
          >
            {finalize.isPending ? "Finalizing..." : "Finalize Plan"}
          </button>
        )}
      </div>
    </div>
  );
}
