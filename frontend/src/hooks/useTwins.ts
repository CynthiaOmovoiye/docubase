/**
 * Twin API hooks — React Query wrappers.
 */

import { useQuery, useMutation, useQueryClient, useQueries } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MemoryBrief, Twin, TwinConfig, Workspace } from "@/types";

// ─── Query keys ───────────────────────────────────────────────────────────────
export const twinKeys = {
  all: (workspaceId: string) => ["twins", workspaceId] as const,
  detail: (id: string) => ["twin", id] as const,
  config: (id: string) => ["twin", id, "config"] as const,
};

// ─── Queries ──────────────────────────────────────────────────────────────────
export function useTwins(workspaceId: string) {
  return useQuery({
    queryKey: twinKeys.all(workspaceId),
    queryFn: async () => {
      const { data } = await api.get<Twin[]>("/twins/", {
        params: { workspace_id: workspaceId },
      });
      return data;
    },
    enabled: !!workspaceId,
  });
}

export function useTwinsForWorkspaces(workspaces: Workspace[]) {
  const results = useQueries({
    queries: workspaces.map((workspace) => ({
      queryKey: twinKeys.all(workspace.id),
      queryFn: async (): Promise<Twin[]> => {
        const { data } = await api.get<Twin[]>("/twins/", {
          params: { workspace_id: workspace.id },
        });
        return data;
      },
      enabled: !!workspace.id,
      staleTime: 15_000,
    })),
  });

  return workspaces.map((workspace, index) => ({
    workspace,
    twins: results[index]?.data ?? [],
    isLoading: results[index]?.isLoading ?? false,
  }));
}

export function useTwin(twinId: string) {
  return useQuery({
    queryKey: twinKeys.detail(twinId),
    queryFn: async () => {
      const { data } = await api.get<Twin>(`/twins/${twinId}`);
      return data;
    },
    enabled: !!twinId,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────────
export function useCreateTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      name: string;
      description?: string;
      workspace_id: string;
    }) => {
      const { data } = await api.post<Twin>("/twins/", payload);
      return data;
    },
    onSuccess: (twin) => {
      qc.invalidateQueries({ queryKey: twinKeys.all(twin.workspace_id) });
    },
  });
}

export function useUpdateTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      twinId,
      ...payload
    }: {
      twinId: string;
      name?: string;
      description?: string;
      is_active?: boolean;
    }) => {
      const { data } = await api.patch<Twin>(`/twins/${twinId}`, payload);
      return data;
    },
    onSuccess: (twin) => {
      qc.invalidateQueries({ queryKey: twinKeys.detail(twin.id) });
      qc.invalidateQueries({ queryKey: twinKeys.all(twin.workspace_id) });
    },
  });
}

export function useDeleteTwin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      twinId,
      workspaceId,
    }: {
      twinId: string;
      workspaceId: string;
    }) => {
      await api.delete(`/twins/${twinId}`);
      return workspaceId;
    },
    onSuccess: (workspaceId) => {
      qc.invalidateQueries({ queryKey: twinKeys.all(workspaceId) });
    },
  });
}

export function useUpdateTwinConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      twinId,
      ...payload
    }: {
      twinId: string;
      allow_code_snippets?: boolean;
      is_public?: boolean;
      display_name?: string;
      accent_color?: string;
      custom_context?: string;
    }) => {
      const { data } = await api.patch<TwinConfig>(
        `/twins/${twinId}/config`,
        payload
      );
      return data;
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: twinKeys.detail(vars.twinId) });
      qc.invalidateQueries({ queryKey: twinKeys.config(vars.twinId) });
    },
  });
}

// ─── Engineering Memory hooks ─────────────────────────────────────────────────

export function useMemoryBrief(twinId: string) {
  return useQuery({
    queryKey: ["twin", twinId, "memory-brief"] as const,
    queryFn: async () => {
      const { data } = await api.get<MemoryBrief>(
        `/twins/${twinId}/memory/brief`
      );
      return data;
    },
    enabled: !!twinId,
    retry: false, // 404 before generation should not retry exhaustively
    refetchInterval: (query) => {
      // Poll every 5 seconds while generation is in progress
      return query.state.data?.status === "generating" ? 5000 : false;
    },
  });
}

export function useTriggerMemoryGeneration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (twinId: string) => {
      const { data } = await api.post<{ status: string; twin_id: string }>(
        `/twins/${twinId}/memory/generate`
      );
      return data;
    },
    onSuccess: (_, twinId) => {
      // Status is already "generating" (set synchronously by the API endpoint),
      // so invalidate immediately — the next poll shows the spinner right away.
      qc.invalidateQueries({ queryKey: ["twin", twinId, "memory-brief"] });
    },
  });
}
