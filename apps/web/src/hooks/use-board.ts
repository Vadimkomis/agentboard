"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "./use-backend-token";
import type { Board } from "@/lib/types";

export function useBoard(projectId: string) {
  const { token } = useBackendToken();
  return useQuery({
    queryKey: ["board", projectId],
    queryFn: async () => {
      const boards = await api.get<Board[]>(
        `/api/projects/${projectId}/boards`,
        { token: token! }
      );
      return boards[0] || null;
    },
    enabled: !!token && !!projectId,
  });
}
