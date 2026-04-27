import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import AppShell from "@/components/AppShell";
import { useIsMobile } from "@/hooks/useIsMobile";
import {
  RichConversationPanel,
  SessionHistoryPanel,
} from "@/features/chat/components/RichConversationPanel";
import { useChat, useWorkspaceSessions } from "@/features/chat/hooks/useChat";
import { useWorkspace } from "@/hooks/useWorkspaces";
import { useTwins } from "@/hooks/useTwins";

export default function WorkspaceChatPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { data: workspace, isLoading: workspaceLoading, error } = useWorkspace(workspaceId ?? "");
  const { data: twins = [], isLoading: twinsLoading } = useTwins(workspaceId ?? "");
  const { data: sessions = [] } = useWorkspaceSessions(workspaceId);

  const isMobile = useIsMobile();
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);
  const [sidebarMode, setSidebarMode] = useState<"twins" | "sessions" | null>("twins");
  const [inputValue, setInputValue] = useState("");

  const {
    messages,
    isLoading: isSending,
    error: chatError,
    sendMessage,
    startNewSession,
  } = useChat({ workspaceId, resumeSessionId });

  function resumeSession(id: string) {
    setResumeSessionId(id);
    setSidebarMode("twins");
  }

  function handleNewChat() {
    setResumeSessionId(null);
    startNewSession();
  }

  async function handleSend() {
    if (!inputValue.trim() || isSending) return;
    const text = inputValue.trim();
    setInputValue("");
    await sendMessage(text);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  if (workspaceLoading) {
    return (
      <AppShell>
        <div style={s.loadingWrap}>
          <div style={s.spinner} />
        </div>
      </AppShell>
    );
  }

  if (error || !workspace) {
    return (
      <AppShell>
        <div style={s.loadingWrap}>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 14 }}>
            Workspace not found.{" "}
            <Link to="/workspaces" style={s.inlineLink}>
              Back to workspaces
            </Link>
          </p>
        </div>
      </AppShell>
    );
  }

  const accentColor = "var(--color-teal)";
  const avatarLetter = workspace.name[0]?.toUpperCase() ?? "W";

  return (
    <AppShell>
      <div style={s.page}>
        <div style={{ ...s.topbar, paddingLeft: isMobile ? 58 : 24 }}>
          <div style={s.topbarLeft}>
            <div style={{ ...s.workspaceAvatar, background: accentColor }}>
              {avatarLetter}
            </div>

            <div style={s.topbarMeta}>
              <h1 style={s.workspaceName}>{workspace.name}</h1>
              <div style={s.metaRow}>
                {workspace.slug && <span style={s.slugChip}>/{workspace.slug}</span>}
                {!isMobile && <span style={s.routeBadge}>Workspace routing</span>}
                <span style={s.metaLabel}>{twins.length} twin{twins.length === 1 ? "" : "s"}</span>
              </div>
            </div>
          </div>

          <div style={s.topbarActions}>
            {resumeSessionId && (
              <button style={s.actionBtn} onClick={handleNewChat} title="Start a new chat">
                {isMobile ? "+" : "+ New chat"}
              </button>
            )}
            {!isMobile && (
              <>
                <Link to="/workspaces" style={s.actionBtn}>
                  <IconLayers />
                  Workspaces
                </Link>
                <Link to={`/twins?workspace=${workspace.id}`} style={s.actionBtn}>
                  <IconTwin />
                  Twins
                  {twins.length > 0 && <span style={s.countPill}>{twins.length}</span>}
                </Link>
              </>
            )}
            <button
              style={{ ...s.actionBtn, ...(sidebarMode === "sessions" ? s.actionBtnActive : {}) }}
              onClick={() => setSidebarMode((mode) => mode === "sessions" ? "twins" : "sessions")}
              title="Session history"
            >
              <IconHistory />
              {!isMobile && "History"}
              {sessions.length > 0 && <span style={s.countPill}>{sessions.length}</span>}
            </button>
            <button
              style={{ ...s.actionBtn, ...(sidebarMode === "twins" ? s.actionBtnActive : {}) }}
              onClick={() => setSidebarMode((mode) => mode === "twins" ? null : "twins")}
              title="Toggle workspace sidebar"
            >
              <IconPanel />
            </button>
          </div>
        </div>

        {/* Mobile sidebar backdrop */}
        {isMobile && sidebarMode && (
          <div
            style={s.mobileSidebarBackdrop}
            onClick={() => setSidebarMode(null)}
            aria-hidden="true"
          />
        )}

        <div style={{
          ...s.body,
          gridTemplateColumns: isMobile ? "1fr" : "minmax(0, 1fr) 320px",
        }}>
          <RichConversationPanel
            messages={messages}
            isSending={isSending}
            chatError={chatError}
            inputValue={inputValue}
            onInputChange={setInputValue}
            onKeyDown={handleKeyDown}
            onSend={() => { void handleSend(); }}
            placeholder={`Ask ${workspace.name} anything…`}
            accentColor={accentColor}
            avatarLetter={avatarLetter}
            emptyState={
              twins.length === 0
                ? <NoTwinsPrompt workspaceId={workspace.id} />
                : <WorkspacePrompt workspaceName={workspace.name} twinCount={twins.length} />
            }
          />

          {sidebarMode === "twins" && (
            <aside style={{
              ...s.sidebar,
              ...(isMobile ? s.sidebarMobileOverlay : {}),
            }}>
              <div style={s.sidebarHeader}>
                <span style={s.sidebarTitle}>Twins in this workspace</span>
                <Link to={`/twins?workspace=${workspace.id}`} style={s.sidebarManageLink}>
                  Manage
                </Link>
              </div>

              {twinsLoading ? (
                <div style={s.sidebarEmpty}>
                  <p style={s.sidebarEmptyText}>Loading twins…</p>
                </div>
              ) : twins.length === 0 ? (
                <div style={s.sidebarEmpty}>
                  <p style={s.sidebarEmptyText}>No twins connected to this workspace yet.</p>
                  <Link to={`/twins?workspace=${workspace.id}`} style={s.sidebarAddLink}>
                    + Add a twin
                  </Link>
                </div>
              ) : (
                <ul style={s.twinList}>
                  {twins.map((twin) => (
                    <li key={twin.id} style={s.twinRow}>
                      <Link to={`/twin/${twin.id}`} style={s.twinLink}>
                        <div style={s.twinAvatar}>
                          {(twin.config?.display_name || twin.name).charAt(0).toUpperCase()}
                        </div>
                        <div style={s.twinMeta}>
                          <span style={s.twinName}>{twin.config?.display_name || twin.name}</span>
                          <span style={s.twinDescription}>
                            {twin.description || "No description yet."}
                          </span>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}

              <div style={s.policyNote}>
                <IconShield />
                <span>
                  Workspace chat routes each question to the best twin, but replies still come
                  only from that twin’s approved knowledge.
                </span>
              </div>
            </aside>
          )}

          {sidebarMode === "sessions" && (
            <aside style={{
              ...s.sidebar,
              ...(isMobile ? s.sidebarMobileOverlay : {}),
            }}>
              <div style={s.sidebarHeader}>
                <span style={s.sidebarTitle}>Chat history</span>
                <button style={s.sidebarManageLink} onClick={handleNewChat}>
                  + New
                </button>
              </div>
              <SessionHistoryPanel
                sessions={sessions}
                activeSessionId={resumeSessionId}
                onResume={resumeSession}
              />
            </aside>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function NoTwinsPrompt({ workspaceId }: { workspaceId: string }) {
  return (
    <div style={s.promptCard}>
      <div style={s.promptOrb}>
        <IconTwin />
      </div>
      <h2 style={s.promptTitle}>Add a twin to start workspace chat</h2>
      <p style={s.promptBody}>
        Workspace chat needs at least one twin so it has somewhere to route the question.
        Create a twin inside this workspace first, then attach sources to ground it.
      </p>
      <Link to={`/twins?workspace=${workspaceId}`} style={s.promptCta}>
        Add first twin
      </Link>
    </div>
  );
}

function WorkspacePrompt({
  workspaceName,
  twinCount,
}: {
  workspaceName: string;
  twinCount: number;
}) {
  return (
    <div style={s.promptCard}>
      <div style={s.promptOrb}>
        <IconRoute />
      </div>
      <h2 style={s.promptTitle}>Ask across {workspaceName}</h2>
      <p style={s.promptBody}>
        Each message is routed to the most relevant twin in this workspace. That keeps the
        experience broad like a workspace, while answers stay grounded like a twin chat.
      </p>
      <div style={s.promptMetaRow}>
        <span style={s.promptTag}>{twinCount} twin{twinCount === 1 ? "" : "s"} available</span>
        <span style={s.promptTag}>Routed per message</span>
      </div>
    </div>
  );
}

function IconLayers() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 2 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </svg>
  );
}

function IconTwin() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 7a4 4 0 1 1 8 0v10a4 4 0 0 1-8 0V7Z" />
      <path d="M8 11h8" />
      <path d="M12 17v4" />
    </svg>
  );
}

function IconHistory() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-4.95" />
    </svg>
  );
}

function IconPanel() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M15 3v18" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function IconRoute() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="12" cy="18" r="3" />
      <path d="M8.59 8.59 10.5 14" />
      <path d="M15.41 8.59 13.5 14" />
    </svg>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    background: "var(--color-bg)",
    overflow: "hidden",
  },
  loadingWrap: {
    height: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  spinner: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    border: "3px solid var(--color-border)",
    borderTopColor: "var(--color-teal)",
    animation: "spin 0.8s linear infinite",
  },
  inlineLink: {
    color: "var(--color-iris)",
    textDecoration: "none",
  },
  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 24px",
    height: 60,
    background: "var(--color-surface)",
    borderBottom: "1px solid var(--color-border)",
    flexShrink: 0,
    gap: 12,
  },
  topbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
  },
  workspaceAvatar: {
    width: 36,
    height: 36,
    borderRadius: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    fontWeight: 700,
    fontSize: 16,
    flexShrink: 0,
  },
  topbarMeta: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    minWidth: 0,
  },
  workspaceName: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: 15,
    color: "var(--color-text-primary)",
    margin: 0,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  metaRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  slugChip: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    fontFamily: "var(--font-mono)",
  },
  routeBadge: {
    padding: "2px 7px",
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 700,
    background: "rgba(15,118,110,0.1)",
    color: "var(--color-teal)",
  },
  metaLabel: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
  },
  topbarActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  actionBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    height: 34,
    padding: "0 12px",
    borderRadius: 10,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-primary)",
    fontSize: 13,
    fontWeight: 600,
    textDecoration: "none",
    cursor: "pointer",
  },
  actionBtnActive: {
    borderColor: "rgba(99,102,241,0.18)",
    background: "var(--color-iris-muted)",
    color: "var(--color-iris)",
  },
  countPill: {
    minWidth: 18,
    height: 18,
    padding: "0 6px",
    borderRadius: 999,
    background: "rgba(99,102,241,0.12)",
    color: "var(--color-iris)",
    fontSize: 10,
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  body: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 320px",
    minHeight: 0,
    flex: 1,
  },
  mobileSidebarBackdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.38)",
    zIndex: 199,
    backdropFilter: "blur(2px)",
  },
  sidebar: {
    background: "var(--color-surface)",
    borderLeft: "1px solid var(--color-border)",
    padding: "16px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    overflowY: "auto",
  },
  sidebarMobileOverlay: {
    position: "fixed",
    right: 0,
    top: 60,
    bottom: 0,
    width: "min(88vw, 320px)",
    zIndex: 200,
    boxShadow: "-4px 0 28px rgba(15,23,42,0.14)",
    borderLeft: "1px solid var(--color-border)",
  },
  sidebarHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  sidebarTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  sidebarManageLink: {
    border: "none",
    background: "transparent",
    color: "var(--color-iris)",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    textDecoration: "none",
    padding: 0,
  },
  sidebarEmpty: {
    padding: "16px 14px",
    borderRadius: 12,
    border: "1px dashed var(--color-border)",
    background: "var(--color-bg)",
  },
  sidebarEmptyText: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  sidebarAddLink: {
    display: "inline-block",
    marginTop: 8,
    fontSize: 13,
    fontWeight: 700,
    color: "var(--color-iris)",
    textDecoration: "none",
  },
  twinList: {
    listStyle: "none",
    margin: 0,
    padding: 0,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  twinRow: {
    margin: 0,
  },
  twinLink: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start",
    padding: "12px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    textDecoration: "none",
  },
  twinAvatar: {
    width: 34,
    height: 34,
    borderRadius: 10,
    background: "linear-gradient(135deg, rgba(15,118,110,0.18), rgba(15,23,42,0.12))",
    color: "var(--color-text-primary)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    flexShrink: 0,
  },
  twinMeta: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  twinName: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  twinDescription: {
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--color-text-secondary)",
  },
  policyNote: {
    marginTop: "auto",
    display: "flex",
    gap: 8,
    alignItems: "flex-start",
    padding: "12px 14px",
    borderRadius: 12,
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  promptCard: {
    maxWidth: 520,
    padding: "28px 26px",
    borderRadius: 20,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    boxShadow: "var(--shadow-sm)",
    textAlign: "center",
  },
  promptOrb: {
    width: 56,
    height: 56,
    borderRadius: 18,
    margin: "0 auto 18px",
    background: "rgba(15,118,110,0.1)",
    color: "var(--color-teal)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  promptTitle: {
    margin: 0,
    fontFamily: "var(--font-display)",
    fontSize: 24,
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  promptBody: {
    margin: "12px 0 0",
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  promptCta: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 18,
    padding: "10px 16px",
    borderRadius: 12,
    background: "var(--color-teal)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    textDecoration: "none",
  },
  promptMetaRow: {
    marginTop: 16,
    display: "flex",
    justifyContent: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  promptTag: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    color: "var(--color-text-secondary)",
  },
};
