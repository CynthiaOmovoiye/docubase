/**
 * Sharing API hooks — React Query wrappers.
 *
 * Covers:
 * - List share surfaces for a twin
 * - Create a twin page share surface
 * - Create an embed share surface
 * - Revoke a share surface
 */

import { useQuery, useMutation, useQueryClient, useQueries } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ShareSurface, Workspace } from "@/types";

// ─── Query keys ───────────────────────────────────────────────────────────────
export const sharingKeys = {
  twinSurfaces: (twinId: string) => ["sharing", "twin", twinId] as const,
  workspaceSurfaces: (workspaceId: string) =>
    ["sharing", "workspace", workspaceId] as const,
};

// ─── Queries ──────────────────────────────────────────────────────────────────

export function useTwinShareSurfaces(twinId: string) {
  return useQuery({
    queryKey: sharingKeys.twinSurfaces(twinId),
    queryFn: async () => {
      const { data } = await api.get<ShareSurface[]>(`/share/twin/${twinId}`);
      return data;
    },
    enabled: !!twinId,
  });
}

export function useWorkspaceShareSurfaces(workspaceId: string) {
  return useQuery({
    queryKey: sharingKeys.workspaceSurfaces(workspaceId),
    queryFn: async () => {
      const { data } = await api.get<ShareSurface[]>(`/share/workspace/${workspaceId}`);
      return data;
    },
    enabled: !!workspaceId,
  });
}

export function useWorkspaceShareSurfacesForWorkspaces(workspaces: Workspace[]) {
  const results = useQueries({
    queries: workspaces.map((workspace) => ({
      queryKey: sharingKeys.workspaceSurfaces(workspace.id),
      queryFn: async (): Promise<ShareSurface[]> => {
        const { data } = await api.get<ShareSurface[]>(`/share/workspace/${workspace.id}`);
        return data;
      },
      enabled: !!workspace.id,
      staleTime: 15_000,
    })),
  });

  return workspaces.map((workspace, index) => ({
    workspace,
    surfaces: results[index]?.data ?? [],
    isLoading: results[index]?.isLoading ?? false,
  }));
}

// ─── Mutations ────────────────────────────────────────────────────────────────

export function useCreateTwinSharePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (twinId: string) => {
      const { data } = await api.post<ShareSurface>(`/share/twin/${twinId}/page`);
      return { surface: data, twinId };
    },
    onSuccess: ({ twinId }) => {
      qc.invalidateQueries({ queryKey: sharingKeys.twinSurfaces(twinId) });
    },
  });
}

export function useCreateEmbedSurface() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      twinId,
      allowed_origins = [],
    }: {
      twinId: string;
      allowed_origins?: string[];
    }) => {
      const { data } = await api.post<ShareSurface>(`/share/twin/${twinId}/embed`, {
        allowed_origins,
      });
      return { surface: data, twinId };
    },
    onSuccess: ({ twinId }) => {
      qc.invalidateQueries({ queryKey: sharingKeys.twinSurfaces(twinId) });
    },
  });
}

export function useCreateWorkspaceSharePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) => {
      const { data } = await api.post<ShareSurface>(`/share/workspace/${workspaceId}/page`);
      return { surface: data, workspaceId };
    },
    onSuccess: ({ workspaceId }) => {
      qc.invalidateQueries({ queryKey: sharingKeys.workspaceSurfaces(workspaceId) });
    },
  });
}

export function useRevokeShareSurface() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      surfaceId,
      twinId,
      workspaceId,
    }: {
      surfaceId: string;
      twinId?: string;
      workspaceId?: string;
    }) => {
      await api.delete(`/share/${surfaceId}`);
      return { twinId, workspaceId };
    },
    onSuccess: ({ twinId, workspaceId }) => {
      if (twinId) {
        qc.invalidateQueries({ queryKey: sharingKeys.twinSurfaces(twinId) });
      }
      if (workspaceId) {
        qc.invalidateQueries({ queryKey: sharingKeys.workspaceSurfaces(workspaceId) });
      }
    },
  });
}
