"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { cn } from "@/lib/utils";
import type { Ticket } from "@/lib/types";
import { useBoardStore } from "@/lib/board-store";

const priorityColors: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400",
  high: "bg-orange-500/20 text-orange-400",
  medium: "bg-yellow-500/20 text-yellow-400",
  low: "bg-green-500/20 text-green-400",
};

const agentColors: Record<string, string> = {
  backend: "bg-blue-500/20 text-blue-400",
  frontend: "bg-purple-500/20 text-purple-400",
  mobile: "bg-emerald-500/20 text-emerald-400",
  devops: "bg-orange-500/20 text-orange-400",
  qa: "bg-yellow-500/20 text-yellow-400",
  fullstack: "bg-indigo-500/20 text-indigo-400",
  docs: "bg-gray-500/20 text-gray-400",
};

const statusColors: Record<string, string> = {
  backlog: "bg-gray-500/20 text-gray-400",
  triaging: "bg-yellow-500/20 text-yellow-400",
  ready: "bg-blue-500/20 text-blue-400",
  in_progress: "bg-indigo-500/20 text-indigo-400",
  in_review: "bg-purple-500/20 text-purple-400",
  done: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
  cancelled: "bg-gray-500/20 text-gray-400",
};

export function TicketCard({ ticket }: { ticket: Ticket }) {
  const openDetail = useBoardStore((s) => s.openDetail);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: ticket.id, data: { ticket } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => openDetail(ticket)}
      className={cn(
        "rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 cursor-grab active:cursor-grabbing hover:border-[var(--primary)]/50 transition-colors",
        isDragging && "opacity-50 shadow-lg"
      )}
    >
      <p className="text-sm font-medium mb-2 line-clamp-2">{ticket.title}</p>
      <div className="flex flex-wrap gap-1.5">
        {ticket.status === "triaging" && (
          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
            Triaging
          </span>
        )}
        {ticket.priority && (
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full",
              priorityColors[ticket.priority] || "bg-gray-500/20 text-gray-400"
            )}
          >
            {ticket.priority}
          </span>
        )}
        {ticket.agent_type && (
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full",
              agentColors[ticket.agent_type] || "bg-gray-500/20 text-gray-400"
            )}
          >
            {ticket.agent_type}
          </span>
        )}
        {ticket.runtime && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--secondary)] text-[var(--secondary-foreground)]">
            {ticket.runtime}
          </span>
        )}
        {ticket.pr_url && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400">
            PR
          </span>
        )}
      </div>
    </div>
  );
}
