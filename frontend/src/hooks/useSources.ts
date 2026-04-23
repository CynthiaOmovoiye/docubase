/**
 * Sources API hooks — React Query wrappers.
 *
 * Covers the full sources lifecycle:
 * - List sources for a twin
 * - Attach a new source (triggers background ingestion)
 * - Get a single source (for status polling)
 * - Detach a source
 * - Trigger re-sync
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Source, SourceType } from "@/types";

// ─── Query keys ───────────────────────────────────────────────────────────────
export const sourceKeys = {
  all: (twinId: string) => ["sources", twinId] as const,
  detail: (sourceId: string) => ["source", sourceId] as const,
};

// ─── Queries ──────────────────────────────────────────────────────────────────

export function useSources(twinId: string) {
  return useQuery({
    queryKey: sourceKeys.all(twinId),
    queryFn: async () => {
      const { data } = await api.get<Source[]>(`/sources/twin/${twinId}`);
      return data;
    },
    enabled: !!twinId,
    // Poll while any source is in an active processing state
    refetchInterval: (query) => {
      const sources = query.state.data;
      if (!sources) return false;
      const processing = sources.some(
        (s) => s.status === "ingesting" || s.status === "pending" || s.status === "processing"
      );
      return processing ? 3000 : false;
    },
  });
}

export function useSource(sourceId: string) {
  return useQuery({
    queryKey: sourceKeys.detail(sourceId),
    queryFn: async () => {
      const { data } = await api.get<Source>(`/sources/${sourceId}`);
      return data;
    },
    enabled: !!sourceId,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────────

export interface AttachSourcePayload {
  twinId: string;
  name: string;
  source_type: SourceType;
  connection_config: Record<string, string>;
  connected_account_id?: string;
}

export function useAttachSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ twinId, ...payload }: AttachSourcePayload) => {
      const { data } = await api.post<Source>(`/sources/twin/${twinId}`, payload);
      return { source: data, twinId };
    },
    onSuccess: ({ twinId }) => {
      qc.invalidateQueries({ queryKey: sourceKeys.all(twinId) });
    },
  });
}

export function useDetachSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ sourceId, twinId }: { sourceId: string; twinId: string }) => {
      await api.delete(`/sources/${sourceId}`);
      return twinId;
    },
    onSuccess: (twinId) => {
      qc.invalidateQueries({ queryKey: sourceKeys.all(twinId) });
    },
  });
}

export function useTriggerSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ sourceId, twinId }: { sourceId: string; twinId: string }) => {
      await api.post(`/sources/${sourceId}/sync`);
      return twinId;
    },
    onSuccess: (twinId) => {
      // Invalidate to pick up the pending status immediately
      qc.invalidateQueries({ queryKey: sourceKeys.all(twinId) });
    },
  });
}

export function useBackfillLegacySources() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ twinId }: { twinId: string }) => {
      const { data } = await api.post<{
        doctwin_id: string;
        queued_sources: number;
        source_ids: string[];
        message: string;
      }>(`/sources/twin/${twinId}/backfill-legacy`);
      return { twinId, result: data };
    },
    onSuccess: ({ twinId }) => {
      qc.invalidateQueries({ queryKey: sourceKeys.all(twinId) });
    },
  });
}

export interface UploadPdfPayload {
  twinId: string;
  name: string;
  file: File;
}

export function useUploadPdfSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ twinId, name, file }: UploadPdfPayload) => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", file);
      const { data } = await api.post<Source>(
        `/sources/twin/${twinId}/upload-pdf`,
        formData,
        // Let the browser set the correct multipart boundary automatically
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return { source: data, twinId };
    },
    onSuccess: ({ twinId }) => {
      qc.invalidateQueries({ queryKey: sourceKeys.all(twinId) });
    },
  });
}
