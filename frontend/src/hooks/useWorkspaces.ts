/**
 * Workspace API hooks — React Query wrappers.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Workspace } from "@/types";

// ─── Query keys ───────────────────────────────────────────────────────────────
export const workspaceKeys = {
  all: ["workspaces"] as const,
  detail: (id: string) => ["workspaces", id] as const,
};

// ─── Queries ──────────────────────────────────────────────────────────────────
export function useWorkspaces() {
  return useQuery({
    queryKey: workspaceKeys.all,
    queryFn: async () => {
      const { data } = await api.get<Workspace[]>("/workspaces/");
      return data;
    },
  });
}

export function useWorkspace(id: string) {
  return useQuery({
    queryKey: workspaceKeys.detail(id),
    queryFn: async () => {
      const { data } = await api.get<Workspace>(`/workspaces/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────────
export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => {
      const { data } = await api.post<Workspace>("/workspaces/", payload);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: workspaceKeys.all }),
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) => {
      await api.delete(`/workspaces/${workspaceId}`);
      return workspaceId;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: workspaceKeys.all });
      qc.invalidateQueries({ queryKey: ["twins"] });
      qc.invalidateQueries({ queryKey: ["sharing", "workspace"] });
    },
  });
}
