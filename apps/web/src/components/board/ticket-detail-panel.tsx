"use client";

import { cn } from "@/lib/utils";
import type { Execution } from "@/lib/types";
import { useBoardStore } from "@/lib/board-store";
import { useApproveTicket, useDeleteTicket, useTransitionTicket } from "@/hooks/use-tickets";
import { useReopenPlan } from "@/hooks/use-planning";
import { useBackendToken } from "@/hooks/use-backend-token";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { toast } from "sonner";
import { PlanningChat } from "./planning-chat";

const statusLabels: Record<string, { label: string; color: string }> = {
  backlog: { label: "Backlog", color: "bg-gray-500/20 text-gray-400" },
  planning: { label: "Planning", color: "bg-amber-500/20 text-amber-400" },
  triaging: { label: "Triaging", color: "bg-yellow-500/20 text-yellow-400" },
  ready: { label: "Ready", color: "bg-blue-500/20 text-blue-400" },
  in_progress: { label: "In Progress", color: "bg-indigo-500/20 text-indigo-400" },
  in_review: { label: "In Review", color: "bg-purple-500/20 text-purple-400" },
  done: { label: "Done", color: "bg-green-500/20 text-green-400" },
  failed: { label: "Failed", color: "bg-red-500/20 text-red-400" },
  cancelled: { label: "Cancelled", color: "bg-gray-500/20 text-gray-400" },
};

const allStatuses = [
  "backlog",
  "planning",
  "triaging",
  "ready",
  "in_progress",
  "in_review",
  "done",
  "failed",
  "cancelled",
] as const;

export function TicketDetailPanel({ projectId }: { projectId: string }) {
  const { selectedTicket: ticket, detailOpen, closeDetail } = useBoardStore();
  const { token } = useBackendToken();
  const approve = useApproveTicket(projectId);
  const transition = useTransitionTicket(projectId);
  const deleteTicket = useDeleteTicket(projectId);
  const reopen = useReopenPlan(projectId, ticket?.id ?? "");

  const { data: executions } = useQuery({
    queryKey: ["executions", projectId, ticket?.id],
    queryFn: () =>
      api.get<Execution[]>(
        `/api/projects/${projectId}/tickets/${ticket!.id}/executions`,
        { token: token! }
      ),
    enabled: !!token && !!ticket,
  });

  if (!detailOpen || !ticket) return null;

  const status = statusLabels[ticket.status] || statusLabels.backlog;

  const handleApprove = async () => {
    try {
      await approve.mutateAsync(ticket.id);
      toast.success("Agent execution started");
      closeDetail();
    } catch {
      toast.error("Failed to approve ticket");
    }
  };

  const handleReplan = async () => {
    try {
      await reopen.mutateAsync();
      toast.success("Planning reopened");
    } catch {
      toast.error("Failed to reopen planning");
    }
  };

  const handleStatusChange = async (newStatus: string) => {
    if (newStatus === ticket.status) return;
    try {
      await transition.mutateAsync({ ticketId: ticket.id, status: newStatus });
      toast.success(`Status changed to ${statusLabels[newStatus]?.label ?? newStatus}`);
    } catch {
      toast.error("Failed to change status");
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this ticket? This cannot be undone.")) return;
    try {
      await deleteTicket.mutateAsync(ticket.id);
      toast.success("Ticket deleted");
      closeDetail();
    } catch {
      toast.error("Failed to delete ticket");
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={closeDetail} />
      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-[var(--card)] border-l border-[var(--border)] z-50 overflow-y-auto">
        <div className="p-6">
          <div className="flex items-start justify-between mb-6">
            <div className="flex-1 mr-4">
              <h2 className="text-xl font-bold">{ticket.title}</h2>
              <div className="flex items-center gap-2 mt-2">
                <select
                  value={ticket.status}
                  onChange={(e) => handleStatusChange(e.target.value)}
                  disabled={transition.isPending}
                  className={cn(
                    "text-xs px-2 py-1 rounded-full border-none outline-none cursor-pointer appearance-none",
                    status.color,
                    "bg-clip-padding",
                    transition.isPending && "opacity-50"
                  )}
                >
                  {allStatuses.map((s) => (
                    <option key={s} value={s}>
                      {statusLabels[s]?.label ?? s}
                    </option>
                  ))}
                </select>
                {ticket.priority && (
                  <span className="text-xs px-2 py-1 rounded-full bg-[var(--secondary)] text-[var(--secondary-foreground)]">
                    {ticket.priority}
                  </span>
                )}
                {ticket.complexity && (
                  <span className="text-xs px-2 py-1 rounded-full bg-[var(--secondary)] text-[var(--secondary-foreground)]">
                    {ticket.complexity}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={closeDetail}
              className="text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {ticket.description && (
            <Section title="Description">
              <p className="text-sm text-[var(--secondary-foreground)] whitespace-pre-wrap">
                {ticket.description}
              </p>
            </Section>
          )}

          {ticket.status === "planning" && (
            <Section title="Planning Conversation">
              <div className="h-[400px] flex flex-col">
                <PlanningChat projectId={projectId} ticketId={ticket.id} />
              </div>
            </Section>
          )}

          {ticket.refined_description && (
            <Section title="Refined Description (AI)">
              <p className="text-sm text-[var(--secondary-foreground)] whitespace-pre-wrap">
                {ticket.refined_description}
              </p>
            </Section>
          )}

          {ticket.acceptance_criteria && (
            <Section title="Acceptance Criteria">
              <p className="text-sm text-[var(--secondary-foreground)] whitespace-pre-wrap">
                {ticket.acceptance_criteria}
              </p>
            </Section>
          )}

          {ticket.triage_reasoning && (
            <Section title="Triage Reasoning">
              <p className="text-sm text-[var(--muted-foreground)] whitespace-pre-wrap">
                {ticket.triage_reasoning}
              </p>
            </Section>
          )}

          {(ticket.agent_type || ticket.runtime) && (
            <Section title="Agent Assignment">
              <div className="flex gap-4 text-sm">
                {ticket.agent_type && (
                  <div>
                    <span className="text-[var(--muted-foreground)]">Agent: </span>
                    <span className="font-medium">{ticket.agent_type}</span>
                  </div>
                )}
                {ticket.runtime && (
                  <div>
                    <span className="text-[var(--muted-foreground)]">Runtime: </span>
                    <span className="font-medium">{ticket.runtime}</span>
                  </div>
                )}
              </div>
            </Section>
          )}

          {ticket.pr_url && (
            <Section title="Pull Request">
              <a
                href={ticket.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[var(--primary)] hover:underline"
              >
                PR #{ticket.pr_number} - View on GitHub
              </a>
            </Section>
          )}

          {ticket.status === "ready" && (
            <div className="mt-6 space-y-2">
              <button
                onClick={handleApprove}
                disabled={approve.isPending}
                className="w-full px-4 py-3 rounded-lg bg-[var(--primary)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {approve.isPending ? "Starting..." : "Approve & Execute"}
              </button>
              <button
                onClick={handleReplan}
                disabled={reopen.isPending}
                className="w-full px-4 py-2.5 rounded-lg border border-[var(--border)] text-[var(--muted-foreground)] text-sm font-medium hover:text-[var(--foreground)] hover:border-[var(--foreground)] transition-colors disabled:opacity-50"
              >
                {reopen.isPending ? "Reopening..." : "Re-plan"}
              </button>
            </div>
          )}

          {executions && executions.length > 0 && (
            <Section title="Executions">
              <div className="space-y-2">
                {executions.map((exec) => (
                  <div
                    key={exec.id}
                    className="rounded-lg border border-[var(--border)] bg-[var(--background)] p-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium">
                        {exec.agent_type} / {exec.runtime}
                      </span>
                      <span
                        className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          exec.status === "completed"
                            ? "bg-green-500/20 text-green-400"
                            : exec.status === "running"
                              ? "bg-blue-500/20 text-blue-400"
                              : exec.status === "failed"
                                ? "bg-red-500/20 text-red-400"
                                : "bg-gray-500/20 text-gray-400"
                        )}
                      >
                        {exec.status}
                      </span>
                    </div>
                    <div className="flex gap-4 text-xs text-[var(--muted-foreground)]">
                      {exec.duration_seconds != null && (
                        <span>{exec.duration_seconds}s</span>
                      )}
                      {exec.total_cost > 0 && (
                        <span>${exec.total_cost.toFixed(4)}</span>
                      )}
                      {exec.total_tokens > 0 && (
                        <span>{exec.total_tokens.toLocaleString()} tokens</span>
                      )}
                    </div>
                    {exec.error_message && (
                      <p className="text-xs text-red-400 mt-1">{exec.error_message}</p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          <div className="mt-6 flex items-center justify-between">
            <div className="text-xs text-[var(--muted-foreground)]">
              Created {new Date(ticket.created_at).toLocaleString()}
            </div>
            <button
              onClick={handleDelete}
              disabled={deleteTicket.isPending}
              className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
            >
              {deleteTicket.isPending ? "Deleting..." : "Delete ticket"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}
