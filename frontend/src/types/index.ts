/**
 * Global TypeScript types for docbase.
 *
 * These mirror the backend Pydantic schemas.
 * Backend returns snake_case — these match exactly.
 */

// ─── Users ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

// ─── Workspaces ───────────────────────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

// ─── Twins ────────────────────────────────────────────────────────────────────

export type MemoryBriefStatus = "pending" | "generating" | "ready" | "failed";

export interface TwinConfig {
  id: string;
  doctwin_id: string;
  allow_code_snippets: boolean;
  is_public: boolean;
  display_name: string | null;
  accent_color: string | null;
  custom_context: string | null;
  updated_at: string;
  // Engineering Memory fields (owner-only, not present on public responses)
  memory_brief_status: MemoryBriefStatus | null;
  memory_brief_generated_at: string | null;
  memory_brief: string | null;
}

export interface MemoryBrief {
  doctwin_id: string;
  status: MemoryBriefStatus | null;
  generated_at: string | null;
  brief: string | null;
}

export interface Twin {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  is_active: boolean;
  workspace_id: string;
  config: TwinConfig | null;
  created_at: string;
  updated_at: string;
}

// ─── Sources ──────────────────────────────────────────────────────────────────

export type SourceType =
  | "google_drive"
  | "pdf"
  | "markdown"
  | "url"
  | "manual";

export type SourceStatus =
  | "pending"
  | "ingesting"
  | "processing"
  | "ready"
  | "failed"
  | "needs_resync";

export type SourceIndexMode = "legacy" | "strict";

export interface SourceIndexHealth {
  snapshot_id: string | null;
  snapshot_root_hash: string | null;
  strict_evidence_supported: boolean;
  strict_evidence_ready: boolean;
  index_mode: SourceIndexMode;
  backfill_required: boolean;
  legacy_reasons: string[];
  policy: {
    allow_code_snippets?: boolean;
  };
  coverage: {
    files_received: number;
    files_processed: number;
    files_blocked: number;
    files_secret_flagged: number;
    chunks_created: number;
    chunks_embedded: number;
  };
  contract: {
    total_chunks: number;
    strict_chunk_total: number;
    strict_chunk_ready: number;
    strict_coverage_ratio: number;
  };
  freshness?: {
    last_indexed_at?: string | null;
    stale_after_hours?: number;
    age_hours?: number | null;
    age_minutes?: number | null;
    is_stale?: boolean;
    label?: string;
    reason?: string | null;
  };
  implementation_index?: {
    schema_version?: number;
    ready?: boolean;
    files_indexed?: number;
    symbols_indexed?: number;
    relationships_indexed?: number;
    code_files_indexed?: number;
    parser_supported_files?: number;
    parser_relationship_files?: number;
    parser_coverage_ratio?: number;
    parser_coverage_percent?: number;
    languages?: string[];
    expected_total_files?: number;
  };
}

export interface Source {
  id: string;
  name: string;
  source_type: SourceType;
  status: SourceStatus;
  doctwin_id: string;
  last_error: string | null;
  snapshot_id: string | null;
  snapshot_root_hash: string | null;
  index_mode: SourceIndexMode;
  index_health: SourceIndexHealth;
  created_at: string;
  updated_at: string;
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  routed_doctwin_id: string | null;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  workspace_id: string;
  doctwin_id: string | null;
  created_at: string;
}

export interface ChatSessionSummary {
  session_id: string;
  created_at: string;
  last_message_at: string | null;
  message_count: number;
  preview: string | null;
}

// ─── Sharing ──────────────────────────────────────────────────────────────────

export type ShareSurfaceType = "doctwin_page" | "workspace_page" | "embed";

export interface ShareSurface {
  id: string;
  public_url: string;
  surface_type: ShareSurfaceType;
  public_slug: string;
  is_active: boolean;
  doctwin_id: string | null;
  workspace_id: string | null;
  embed_config: Record<string, unknown>;
  created_at: string;
}

// ─── Integrations ─────────────────────────────────────────────────────────────

export type OAuthProvider = "google_drive";

export interface ConnectedAccount {
  id: string;
  provider: OAuthProvider;
  provider_username: string | null;
  scopes: string | null;
  is_active: boolean;
  created_at: string;
}

export interface DriveFileItem {
  id: string;
  name: string;
  mime_type: string;
  modified_time: string | null;
  is_folder: boolean;
}

// ─── API ──────────────────────────────────────────────────────────────────────

export interface APIError {
  error: string;
  message: string;
  detail: string | null;
}
