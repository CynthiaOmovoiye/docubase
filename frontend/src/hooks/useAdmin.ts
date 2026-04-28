/**
 * Superuser admin API hooks.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type {
  AdminIngestionLogsResponse,
  AdminPlatformStats,
  AdminTwinMaintenanceResponse,
  AdminUserListResponse,
  AdminUserRow,
} from "@/types/admin";

/** Prefix for any admin user-list query (role filter is the next key segment). */
export const adminUsersQueryPrefix = ["admin", "users"] as const;

export const adminKeys = {
  stats: ["admin", "stats"] as const,
  ingestionLogs: ["admin", "ingestion-logs"] as const,
  /** All accounts including platform operators */
  usersAll: [...adminUsersQueryPrefix, "all"] as const,
  /** Consumer signups only (`is_superuser` false); operators excluded */
  usersConsumers: [...adminUsersQueryPrefix, "consumers"] as const,
};

export function useAdminPlatformStats() {
  return useQuery({
    queryKey: adminKeys.stats,
    queryFn: async () => {
      const { data } = await api.get<AdminPlatformStats>("/admin/stats");
      return data;
    },
  });
}

export function useAdminIngestionLogs() {
  return useQuery({
    queryKey: adminKeys.ingestionLogs,
    queryFn: async () => {
      const { data } = await api.get<AdminIngestionLogsResponse>("/admin/ingestion-logs");
      return data;
    },
  });
}

export function useAdminTwinRagDiagnostics() {
  return useMutation({
    mutationFn: async (params: { twinId: string; q?: string }) => {
      const search = params.q?.trim()
        ? `?q=${encodeURIComponent(params.q.trim())}`
        : "";
      const { data } = await api.get<Record<string, unknown>>(
        `/admin/twins/${params.twinId}/rag-diagnostics${search}`
      );
      return data;
    },
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: adminKeys.usersAll,
    queryFn: async () => {
      const { data } = await api.get<AdminUserListResponse>("/admin/users");
      return data;
    },
  });
}

/** Consumer accounts for the Signups table (excludes platform operators). */
export function useAdminConsumerSignups() {
  return useQuery({
    queryKey: adminKeys.usersConsumers,
    queryFn: async () => {
      const { data } = await api.get<AdminUserListResponse>("/admin/users", {
        params: { consumers_only: true },
      });
      return data;
    },
  });
}

export function useAdminUpdateUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { userId: string; is_superuser: boolean }) => {
      const { data } = await api.patch<AdminUserRow>(`/admin/users/${params.userId}`, {
        is_superuser: params.is_superuser,
      });
      return data;
    },
    onSuccess: async (data) => {
      qc.invalidateQueries({ queryKey: adminUsersQueryPrefix });
      qc.invalidateQueries({ queryKey: adminKeys.stats });
      const me = useAuthStore.getState().user?.id;
      if (me && data.id === me) {
        await useAuthStore.getState().fetchMe();
      }
    },
  });
}

export function useAdminCreateOperator() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      email: string;
      password: string;
      display_name?: string | null;
    }) => {
      const { data } = await api.post<AdminUserRow>("/admin/users/operators", {
        email: payload.email.trim().toLowerCase(),
        password: payload.password,
        display_name: payload.display_name?.trim() || undefined,
      });
      return data;
    },
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: adminUsersQueryPrefix });
      qc.invalidateQueries({ queryKey: adminKeys.stats });
    },
  });
}

export function useAdminRebuildTwinMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (twinId: string) => {
      const { data } = await api.post<AdminTwinMaintenanceResponse>(
        `/admin/twins/${twinId}/memory/rebuild`
      );
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: adminKeys.stats });
    },
  });
}
