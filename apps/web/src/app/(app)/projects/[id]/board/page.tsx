"use client";

import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { redirect } from "next/navigation";
import { useProject } from "@/hooks/use-projects";
import { useBoard } from "@/hooks/use-board";
import { useTickets } from "@/hooks/use-tickets";
import { useBackendToken } from "@/hooks/use-backend-token";
import { useSSE } from "@/hooks/use-sse";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { usePlanningStore } from "@/lib/planning-store";
import { KanbanBoard } from "@/components/board/kanban-board";
import Link from "next/link";

export default function BoardPage() {
  const params = useParams();
  const projectId = params.id as string;
  const { data: session, status } = useSession();
  const { token } = useBackendToken();
  const { data: project, isLoading: projectLoading } = useProject(projectId);
  const { data: board, isLoading: boardLoading } = useBoard(projectId);
  const { data: tickets, isLoading: ticketsLoading } = useTickets(projectId);
  const qc = useQueryClient();
  const { appendDelta, completeMessage } = usePlanningStore();

  const handleSSEEvent = useCallback(
    (event: { type: string; data: Record<string, unknown> }) => {
      // Planning conversation events
      if (event.type === "planning_message_new") {
        const ticketId = event.data.ticket_id as string;
        qc.invalidateQueries({
          queryKey: ["planning-messages", projectId, ticketId],
        });
      } else if (event.type === "planning_message_delta") {
        const messageId = event.data.message_id as string;
        const delta = event.data.content_delta as string;
        appendDelta(messageId, delta);
      } else if (event.type === "planning_message_complete") {
        const messageId = event.data.message_id as string;
        const ticketId = event.data.ticket_id as string;
        completeMessage(messageId);
        qc.invalidateQueries({
          queryKey: ["planning-messages", projectId, ticketId],
        });
      } else if (event.type === "plan_finalized") {
        qc.invalidateQueries({ queryKey: ["tickets", projectId] });
      }

      // Refetch tickets on any board-related event
      if (
        [
          "ticket_created",
          "ticket_moved",
          "ticket_updated",
          "triage_complete",
          "execution_started",
          "execution_completed",
          "execution_failed",
          "ticket_approved",
        ].includes(event.type)
      ) {
        qc.invalidateQueries({ queryKey: ["tickets", projectId] });
      }
    },
    [qc, projectId, appendDelta, completeMessage]
  );

  useSSE(projectId, token, handleSSEEvent);

  if (status === "loading" || projectLoading || boardLoading || ticketsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!session) {
    redirect("/auth/signin");
  }

  if (!project) {
    return (
      <div className="text-center py-16">
        <p className="text-[var(--muted-foreground)] mb-4">Project not found</p>
        <Link
          href="/projects"
          className="text-[var(--primary)] hover:underline"
        >
          Back to Projects
        </Link>
      </div>
    );
  }

  if (!board) {
    return (
      <div className="text-center py-16">
        <p className="text-[var(--muted-foreground)]">No board found</p>
      </div>
    );
  }

  return (
    <div className="h-full">
      <div className="flex items-center gap-3 mb-4">
        <Link
          href="/projects"
          className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
        </Link>
        <div>
          <h1 className="text-xl font-bold">{project.name}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {project.repo_full_name}
          </p>
        </div>
      </div>

      <KanbanBoard
        board={board}
        tickets={tickets || []}
        projectId={projectId}
      />
    </div>
  );
}
