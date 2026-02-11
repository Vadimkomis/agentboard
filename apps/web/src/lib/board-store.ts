"use client";

import { create } from "zustand";
import type { Ticket } from "./types";

interface BoardState {
  activeTicketId: string | null;
  selectedTicket: Ticket | null;
  detailOpen: boolean;
  setActiveTicket: (id: string | null) => void;
  openDetail: (ticket: Ticket) => void;
  closeDetail: () => void;
}

export const useBoardStore = create<BoardState>((set) => ({
  activeTicketId: null,
  selectedTicket: null,
  detailOpen: false,
  setActiveTicket: (id) => set({ activeTicketId: id }),
  openDetail: (ticket) => set({ selectedTicket: ticket, detailOpen: true }),
  closeDetail: () => set({ selectedTicket: null, detailOpen: false }),
}));
