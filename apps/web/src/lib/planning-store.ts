"use client";

import { create } from "zustand";

interface PlanningState {
  streamingMessages: Record<string, string>;
  appendDelta: (messageId: string, delta: string) => void;
  completeMessage: (messageId: string) => void;
  reset: () => void;
}

export const usePlanningStore = create<PlanningState>((set) => ({
  streamingMessages: {},
  appendDelta: (messageId, delta) =>
    set((state) => ({
      streamingMessages: {
        ...state.streamingMessages,
        [messageId]: (state.streamingMessages[messageId] || "") + delta,
      },
    })),
  completeMessage: (messageId) =>
    set((state) => {
      const { [messageId]: _, ...rest } = state.streamingMessages;
      return { streamingMessages: rest };
    }),
  reset: () => set({ streamingMessages: {} }),
}));
