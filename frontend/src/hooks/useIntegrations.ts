/**
 * useIntegrations — React Query hooks for OAuth-connected accounts.
 *
 * Covers:
 *   - Listing connected accounts for the current user
 *   - Initiating OAuth (redirecting to the provider)
 *   - Disconnecting a connected account
 *   - Browsing repos / Drive files for a connected account
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ConnectedAccount,
  DriveFileItem,
  OAuthProvider,
  RepoItem,
} from "@/types";

// ─── Query keys ───────────────────────────────────────────────────────────────

const KEYS = {
  accounts: () => ["integrations", "accounts"] as const,
  repos: (accountId: string) =>
    ["integrations", "repos", accountId] as const,
  drive: (accountId: string, folderId?: string) =>
    ["integrations", "drive", accountId, folderId ?? "root"] as const,
};

// ─── Connected accounts ───────────────────────────────────────────────────────

export function useConnectedAccounts() {
  return useQuery({
    queryKey: KEYS.accounts(),
    queryFn: async () => {
      const { data } = await api.get<ConnectedAccount[]>("/integrations");
      return data;
    },
    staleTime: 30_000,
  });
}

/** Returns the connected account for a specific provider, or undefined. */
export function useConnectedAccount(provider: OAuthProvider) {
  const query = useConnectedAccounts();
  const account = query.data?.find((a) => a.provider === provider) ?? null;
  return { ...query, account };
}

// ─── Connect / Disconnect ─────────────────────────────────────────────────────

/**
 * Redirect the user to the provider's OAuth authorization page.
 * The backend issues the URL; we navigate to it directly.
 */
export function useConnectAccount() {
  return useMutation({
    mutationFn: async (provider: OAuthProvider) => {
      const { data } = await api.get<{ auth_url: string }>(
        `/integrations/${provider}/connect`
      );
      // Hard redirect — OAuth is an external page
      window.location.href = data.auth_url;
    },
  });
}

export function useDisconnectAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (accountId: string) => {
      await api.delete(`/integrations/${accountId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.accounts() });
    },
  });
}

// ─── Resource browsers ────────────────────────────────────────────────────────

/** List repos / projects accessible to a GitHub or GitLab connected account. */
export function useAccountRepos(accountId: string | null | undefined) {
  return useQuery({
    queryKey: KEYS.repos(accountId ?? ""),
    enabled: !!accountId,
    queryFn: async () => {
      const account = await _getAccountProvider(accountId!);
      const provider = account?.provider;
      // GitHub → /integrations/github/repos
      // GitLab → /integrations/gitlab/projects
      const path =
        provider === "gitlab"
          ? "/integrations/gitlab/projects"
          : "/integrations/github/repos";
      const { data } = await api.get<RepoItem[]>(path);
      return data;
    },
    staleTime: 60_000,
  });
}

/** List Google Drive files / folders (root or a specific folder). */
export function useAccountDriveFiles(
  accountId: string | null | undefined,
  folderId?: string
) {
  return useQuery({
    queryKey: KEYS.drive(accountId ?? "", folderId),
    enabled: !!accountId,
    queryFn: async () => {
      // account_id is not passed — the backend derives it from the JWT.
      // folder_id scopes the listing; omit for the root.
      const params = new URLSearchParams();
      if (folderId) params.set("folder_id", folderId);
      const qs = params.toString();
      const { data } = await api.get<DriveFileItem[]>(
        `/integrations/google_drive/files${qs ? `?${qs}` : ""}`
      );
      return data;
    },
    staleTime: 30_000,
  });
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Fetch the accounts list and return the entry matching accountId.
 * React Query caches `/integrations` so this is typically a cache hit.
 */
async function _getAccountProvider(
  accountId: string
): Promise<ConnectedAccount | undefined> {
  const { data } = await api.get<ConnectedAccount[]>("/integrations");
  return data.find((a) => a.id === accountId);
}
