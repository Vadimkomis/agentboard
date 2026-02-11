"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "./use-backend-token";
import type { PlanningMessage } from "@/lib/types";

export function usePlanningMessages(projectId: string, ticketId: string) {
  const { token } = useBackendToken();
  return useQuery({
    queryKey: ["planning-messages", projectId, ticketId],
    queryFn: () =>
      api.get<PlanningMessage[]>(
        `/api/projects/${projectId}/tickets/${ticketId}/planning/messages`,
        { token: token! }
      ),
    enabled: !!token && !!projectId && !!ticketId,
  });
}

export function useSendPlanningMessage(projectId: string, ticketId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) =>
      api.post<PlanningMessage>(
        `/api/projects/${projectId}/tickets/${ticketId}/planning/messages`,
        { content },
        { token: token! }
      ),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["planning-messages", projectId, ticketId],
      });
    },
  });
}

export function useFinalizePlan(projectId: string, ticketId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<PlanningMessage>(
        `/api/projects/${projectId}/tickets/${ticketId}/planning/finalize`,
        {},
        { token: token! }
      ),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["planning-messages", projectId, ticketId],
      });
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}

export function useReopenPlan(projectId: string, ticketId: string) {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<PlanningMessage>(
        `/api/projects/${projectId}/tickets/${ticketId}/planning/reopen`,
        {},
        { token: token! }
      ),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["planning-messages", projectId, ticketId],
      });
      qc.invalidateQueries({ queryKey: ["tickets", projectId] });
    },
  });
}
