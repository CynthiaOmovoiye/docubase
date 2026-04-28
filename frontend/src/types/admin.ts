/**
 * Types for `/api/v1/admin/*` (superuser-only).
 */

export interface AdminPlatformStats {
  users: number;
  workspaces: number;
  twins: number;
  sources_total: number;
  sources_by_status: Record<string, number>;
}

export interface AdminIngestionLogsResponse {
  items: unknown[];
  note: string;
}

export interface AdminTwinMaintenanceResponse {
  doctwin_id: string;
  action: string;
  detail: Record<string, unknown>;
}

export interface AdminUserRow {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface AdminUserListResponse {
  users: AdminUserRow[];
}
