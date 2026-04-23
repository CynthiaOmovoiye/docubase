/**
 * ConnectAccountsPage
 *
 * Lets users connect and manage their OAuth accounts for GitHub, GitLab, and
 * Google Drive.  Connected accounts are used when attaching sources to twins —
 * the user must authorize before any source can pull from their repos or Drive.
 *
 * Layout:
 *   Three provider cards, each showing connection state + connect/disconnect action.
 *   A success/error banner appears when returning from an OAuth callback.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import {
  useConnectedAccounts,
  useConnectAccount,
  useDisconnectAccount,
} from "@/hooks/useIntegrations";
import type { ConnectedAccount, OAuthProvider } from "@/types";

const PROVIDERS: {
  id: OAuthProvider;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
}[] = [
  {
    id: "github",
    label: "GitHub",
    description: "Connect repositories, enable push-based sync, and browse your repos when attaching sources.",
    icon: <GitHubIcon />,
    color: "#24292e",
  },
  {
    id: "gitlab",
    label: "GitLab",
    description: "Connect GitLab projects (gitlab.com or self-hosted), with incremental sync on every push.",
    icon: <GitLabIcon />,
    color: "#fc6d26",
  },
  {
    id: "google_drive",
    label: "Google Drive",
    description: "Attach Drive files and folders as sources. The twin syncs whenever you update a file.",
    icon: <DriveIcon />,
    color: "#4285F4",
  },
];

export default function ConnectAccountsPage() {
  const [params] = useSearchParams();
  const [banner, setBanner] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const { data: accounts = [], isLoading } = useConnectedAccounts();
  const connect = useConnectAccount();
  const disconnect = useDisconnectAccount();

  // Show banner when returning from OAuth callback
  useEffect(() => {
    const connected = params.get("connected");
    const error = params.get("error");
    if (connected) {
      setBanner({ type: "success", msg: `${_providerLabel(connected)} connected successfully.` });
    } else if (error) {
      setBanner({ type: "error", msg: `Could not connect: ${error}` });
    }
  }, [params]);

  function accountForProvider(provider: OAuthProvider): ConnectedAccount | null {
    return accounts.find((a) => a.provider === provider) ?? null;
  }

  return (
    <AppShell>
      <div style={s.page}>
        <div style={s.header}>
          <h1 style={s.title}>Connected Accounts</h1>
          <p style={s.subtitle}>
            Connect your accounts to authorize docubase to read from your repositories
            and files. You control exactly which sources you attach to each twin.
          </p>
        </div>

        {banner && (
          <div style={{ ...s.banner, ...(banner.type === "error" ? s.bannerError : s.bannerSuccess) }}>
            <span>{banner.type === "success" ? "✓" : "✕"}</span>
            <span>{banner.msg}</span>
            <button style={s.bannerClose} onClick={() => setBanner(null)}>✕</button>
          </div>
        )}

        {isLoading ? (
          <div style={s.loadingRow}>Loading…</div>
        ) : (
          <div style={s.cards}>
            {PROVIDERS.map((provider) => {
              const account = accountForProvider(provider.id);
              const isConnected = !!account;
              const isConnecting = connect.isPending;
              const isDisconnecting = disconnect.isPending;

              return (
                <div key={provider.id} style={s.card}>
                  <div style={s.cardHeader}>
                    <div style={{ ...s.providerIcon, background: provider.color }}>
                      {provider.icon}
                    </div>
                    <div style={s.cardTitle}>
                      <span style={s.providerLabel}>{provider.label}</span>
                      {isConnected && (
                        <span style={s.connectedBadge}>
                          ● Connected
                          {account.provider_username ? ` as ${account.provider_username}` : ""}
                        </span>
                      )}
                    </div>
                  </div>

                  <p style={s.cardDescription}>{provider.description}</p>

                  {isConnected ? (
                    <button
                      style={{ ...s.btn, ...s.btnOutline }}
                      disabled={isDisconnecting}
                      onClick={() => {
                        if (confirm(`Disconnect ${provider.label}? Sources using this account will stop syncing.`)) {
                          disconnect.mutate(account.id, {
                            onSuccess: () =>
                              setBanner({ type: "success", msg: `${provider.label} disconnected.` }),
                            onError: () =>
                              setBanner({ type: "error", msg: `Failed to disconnect ${provider.label}.` }),
                          });
                        }
                      }}
                    >
                      {isDisconnecting ? "Disconnecting…" : "Disconnect"}
                    </button>
                  ) : (
                    <button
                      style={{ ...s.btn, ...s.btnPrimary }}
                      disabled={isConnecting}
                      onClick={() => connect.mutate(provider.id)}
                    >
                      {isConnecting ? "Redirecting…" : `Connect ${provider.label}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div style={s.securityNote}>
          <span style={s.lockIcon}>🔒</span>
          <span>
            OAuth tokens are stored encrypted at rest and never shared. You can disconnect
            at any time — this immediately revokes all ingestion access for that provider.
          </span>
        </div>
      </div>
    </AppShell>
  );
}

// ─── Provider icons ───────────────────────────────────────────────────────────

function GitHubIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
      <path d="M12 2C6.477 2 2 6.484 2 12.021c0 4.428 2.865 8.185 6.839 9.504.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.202 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.2 22 16.447 22 12.021 22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function GitLabIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
      <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51L23 13.45a.84.84 0 0 1-.35.94z" />
    </svg>
  );
}

function DriveIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
      <path d="M7.71 3.5L1.15 15l3.43 5.96L10.14 9.5 7.71 3.5zm8.58 0L13.86 9.5l5.56 11.46 3.43-5.96L16.29 3.5zm-8.58 0h8.58L12 9.5l-3.87-6zM1.15 15l3.43 5.96h14.84L22.85 15H1.15z" />
    </svg>
  );
}

function _providerLabel(provider: string): string {
  const labels: Record<string, string> = {
    github: "GitHub",
    gitlab: "GitLab",
    google_drive: "Google Drive",
  };
  return labels[provider] ?? provider;
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 860,
    margin: "0 auto",
    padding: "40px 24px 60px",
  },
  header: {
    marginBottom: 32,
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    color: "var(--color-text-primary)",
    margin: 0,
    letterSpacing: "-0.02em",
  },
  subtitle: {
    marginTop: 8,
    fontSize: 15,
    color: "var(--color-text-secondary)",
    lineHeight: 1.6,
    maxWidth: 560,
  },
  banner: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "12px 16px",
    borderRadius: 10,
    fontSize: 14,
    marginBottom: 24,
  },
  bannerSuccess: {
    background: "rgba(20,184,166,0.1)",
    border: "1px solid rgba(20,184,166,0.3)",
    color: "var(--color-teal)",
  },
  bannerError: {
    background: "rgba(239,68,68,0.08)",
    border: "1px solid rgba(239,68,68,0.25)",
    color: "var(--color-rose)",
  },
  bannerClose: {
    marginLeft: "auto",
    background: "transparent",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    opacity: 0.6,
    color: "inherit",
  },
  loadingRow: {
    padding: 40,
    textAlign: "center",
    color: "var(--color-text-secondary)",
    fontSize: 14,
  },
  cards: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
    gap: 20,
    marginBottom: 32,
  },
  card: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 14,
    padding: "24px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    gap: 14,
  },
  providerIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  cardTitle: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
  },
  providerLabel: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  connectedBadge: {
    fontSize: 12,
    color: "var(--color-teal)",
    fontWeight: 500,
  },
  cardDescription: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    lineHeight: 1.55,
    margin: 0,
    flex: 1,
  },
  btn: {
    padding: "9px 16px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.15s",
    border: "none",
    width: "100%",
  },
  btnPrimary: {
    background: "var(--gradient-brand)",
    color: "#fff",
  },
  btnOutline: {
    background: "transparent",
    border: "1px solid var(--color-border)",
    color: "var(--color-text-secondary)",
  },
  securityNote: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    padding: "14px 16px",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 10,
    fontSize: 13,
    color: "var(--color-text-secondary)",
    lineHeight: 1.55,
  },
  lockIcon: {
    fontSize: 16,
    flexShrink: 0,
    marginTop: 1,
  },
};
