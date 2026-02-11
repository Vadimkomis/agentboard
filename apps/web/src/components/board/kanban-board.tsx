"use client";

import { useState, useCallback } from "react";
import {
  DndContext,
  DragOverlay,
  pointerWithin,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import type { Board, Ticket } from "@/lib/types";
import { useMoveTicket } from "@/hooks/use-tickets";
import { useBoardStore } from "@/lib/board-store";
import { BoardColumn } from "./board-column";
import { CreateTicketModal } from "./create-ticket-modal";
import { TicketDetailPanel } from "./ticket-detail-panel";

export function KanbanBoard({
  board,
  tickets,
  projectId,
}: {
  board: Board;
  tickets: Ticket[];
  projectId: string;
}) {
  const moveTicket = useMoveTicket(projectId);
  const setActiveTicket = useBoardStore((s) => s.setActiveTicket);
  const [createColumnId, setCreateColumnId] = useState<string | null>(null);
  const [draggedTicket, setDraggedTicket] = useState<Ticket | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  const ticketsByColumn = useCallback(
    (columnId: string) =>
      tickets
        .filter((t) => t.column_id === columnId)
        .sort((a, b) => a.position - b.position),
    [tickets]
  );

  const handleDragStart = (event: DragStartEvent) => {
    const ticket = tickets.find((t) => t.id === event.active.id);
    if (ticket) {
      setDraggedTicket(ticket);
      setActiveTicket(ticket.id);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setDraggedTicket(null);
    setActiveTicket(null);

    if (!over) return;

    const ticketId = active.id as string;
    const ticket = tickets.find((t) => t.id === ticketId);
    if (!ticket) return;

    // Determine target column - over could be a column or a ticket
    let targetColumnId = over.id as string;
    const overTicket = tickets.find((t) => t.id === over.id);
    if (overTicket) {
      targetColumnId = overTicket.column_id;
    }

    // Check if it's actually a column id
    const isColumn = board.columns.some((c) => c.id === targetColumnId);
    if (!isColumn) return;

    if (ticket.column_id === targetColumnId && !overTicket) return;

    const targetTickets = ticketsByColumn(targetColumnId);
    let position = targetTickets.length;
    if (overTicket) {
      position = overTicket.position;
    }

    moveTicket.mutate({
      ticketId,
      column_id: targetColumnId,
      position,
    });
  };

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={pointerWithin}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-4 overflow-x-auto pb-4 h-[calc(100vh-10rem)]">
          {board.columns
            .sort((a, b) => a.position - b.position)
            .map((col) => (
              <BoardColumn
                key={col.id}
                column={col}
                tickets={ticketsByColumn(col.id)}
                onAddTicket={(columnId) => setCreateColumnId(columnId)}
              />
            ))}
        </div>
        <DragOverlay>
          {draggedTicket ? (
            <div className="rounded-lg border border-[var(--primary)] bg-[var(--card)] p-3 shadow-xl w-72 opacity-90">
              <p className="text-sm font-medium">{draggedTicket.title}</p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      <TicketDetailPanel projectId={projectId} />

      {createColumnId && (
        <CreateTicketModal
          projectId={projectId}
          columnId={createColumnId}
          onClose={() => setCreateColumnId(null)}
        />
      )}
    </>
  );
}
