"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useBackendToken } from "./use-backend-token";
import type { Project } from "@/lib/types";

export function useProjects() {
  const { token } = useBackendToken();
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get<Project[]>("/api/projects", { token: token! }),
    enabled: !!token,
  });
}

export function useProject(id: string) {
  const { token } = useBackendToken();
  return useQuery({
    queryKey: ["project", id],
    queryFn: () => api.get<Project>(`/api/projects/${id}`, { token: token! }),
    enabled: !!token && !!id,
  });
}

export function useCreateProject() {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      repo_full_name: string;
      repo_url: string;
      default_branch?: string;
    }) => api.post<Project>("/api/projects", data, { token: token! }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
  });
}

export function useDeleteProject() {
  const { token } = useBackendToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.delete(`/api/projects/${id}`, { token: token! }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
  });
}
