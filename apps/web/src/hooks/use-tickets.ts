"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "./use-backend-token";
import type { Ticket } from "@/lib/types";

export function useTickets(projectId: string) {
  const { token } = useBackendToken();
  return useQuery({
    queryKey: ["tickets", projectId],
    queryFn: () =>
      api.get<Ticket[]>(`/api/projects/${projectId}/tickets`, {
        token: token!,
      }),
    enabled: !!token && !!projectId,
  });
}

export function useCreateTicket(projectId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      title: string;
      description?: string;
      column_id: string;
    }) =>
      api.post<Ticket>(`/api/projects/${projectId}/tickets`, data, {
        token: token!,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}

export function useMoveTicket(projectId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticketId,
      column_id,
      position,
    }: {
      ticketId: string;
      column_id: string;
      position: number;
    }) =>
      api.post<Ticket>(
        `/api/projects/${projectId}/tickets/${ticketId}/move`,
        { column_id, position },
        { token: token! }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}

export function useApproveTicket(projectId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) =>
      api.post<Ticket>(
        `/api/projects/${projectId}/tickets/${ticketId}/approve`,
        {},
        { token: token! }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}

export function useDeleteTicket(projectId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) =>
      api.delete(`/api/projects/${projectId}/tickets/${ticketId}`, {
        token: token!,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}
