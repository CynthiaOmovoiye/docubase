/**
 * ConnectAccountsPage
 *
 * Google Drive OAuth for attaching Drive files/folders as twin sources.
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
            Connect Google Drive to attach files or folders as twin sources. You choose exactly what to sync.
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

function DriveIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
      <path d="M7.71 3.5L1.15 15l3.43 5.96L10.14 9.5 7.71 3.5zm8.58 0L13.86 9.5l5.56 11.46 3.43-5.96L16.29 3.5zm-8.58 0h8.58L12 9.5l-3.87-6zM1.15 15l3.43 5.96h14.84L22.85 15H1.15z" />
    </svg>
  );
}

function _providerLabel(provider: string): string {
  const labels: Record<string, string> = {
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
