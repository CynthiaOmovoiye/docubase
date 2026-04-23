/**
 * TwinDetailPage — the hub for a single twin.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────┐
 *   │  Topbar: twin name + status + action buttons │
 *   ├──────────────────────┬──────────────────────┤
 *   │                      │  Sources sidebar     │
 *   │   Chat area          │  (collapsed on       │
 *   │                      │   small screens)     │
 *   └──────────────────────┴──────────────────────┘
 *
 * Sources list is shown in a right panel. Chat is the primary focus.
 * If no sources exist yet, the chat area shows a helpful empty state.
 */

import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { useTwin, useMemoryBrief, useTriggerMemoryGeneration } from "@/hooks/useTwins";
import { useSources } from "@/hooks/useSources";
import { useChat, useTwinSessions } from "@/features/chat/hooks/useChat";
import {
  AssistantMarkdown,
  RichConversationPanel,
  SessionHistoryPanel,
} from "@/features/chat/components/RichConversationPanel";
import type { Source } from "@/types";

// ─── Source type labels & icons ───────────────────────────────────────────────
const SOURCE_LABEL: Record<string, string> = {
  github_repo: "GitHub",
  gitlab_repo: "GitLab",
  pdf:         "PDF",
  markdown:    "Markdown",
  url:         "Website",
  manual:      "Manual",
};

const STATUS_COLOR: Record<string, string> = {
  ready:        "var(--color-teal)",
  ingesting:    "var(--color-iris)",
  processing:   "var(--color-iris)",
  pending:      "var(--color-amber)",
  failed:       "var(--color-rose)",
  needs_resync: "var(--color-amber)",
};

export default function TwinDetailPage() {
  const { twinId } = useParams<{ twinId: string }>();
  const navigate = useNavigate();
  const { data: twin, isLoading, error } = useTwin(twinId ?? "");
  const { data: sources = [] } = useSources(twinId ?? "");

  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);
  const [sidebarMode, setSidebarMode] = useState<"sources" | "sessions" | null>("sources");

  const {
    messages,
    isLoading: isSending,
    error: chatError,
    sendMessage,
    startNewSession,
  } = useChat({ twinId, resumeSessionId });

  const { data: sessions = [] } = useTwinSessions(twinId);

  const [inputValue, setInputValue] = useState("");

  function resumeSession(id: string) {
    setResumeSessionId(id);
    setSidebarMode("sources");
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
      handleSend();
    }
  }

  // ── Loading / error states ──────────────────────────────────────────────────
  if (isLoading) {
    return (
      <AppShell>
        <div style={s.loadingWrap}>
          <div style={s.spinner} />
        </div>
      </AppShell>
    );
  }

  if (error || !twin) {
    return (
      <AppShell>
        <div style={s.loadingWrap}>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 14 }}>
            Twin not found.{" "}
            <span
              style={{ color: "var(--color-iris)", cursor: "pointer" }}
              onClick={() => navigate("/dashboard")}
            >
              Back to dashboard
            </span>
          </p>
        </div>
      </AppShell>
    );
  }

  const accentColor = twin.config?.accent_color ?? "var(--color-iris)";
  const hasSources = sources.length > 0;
  const displayName = twin.config?.display_name || twin.name;

  return (
    <AppShell>
      <div style={s.page}>
        {/* ── Topbar ─────────────────────────────────────────────────────── */}
        <div style={s.topbar}>
          <div style={s.topbarLeft}>
            {/* Avatar */}
            <div style={{ ...s.twinAvatar, background: accentColor }}>
              {displayName[0]?.toUpperCase() ?? "T"}
            </div>

            <div style={s.topbarMeta}>
              <h1 style={s.twinName}>{displayName}</h1>
              <div style={s.metaRow}>
                {twin.slug && (
                  <span style={s.slugChip}>@{twin.slug}</span>
                )}
                <StatusDot active={twin.is_active} />
                {twin.config?.is_public && (
                  <span style={s.badge_public}>Public</span>
                )}
              </div>
            </div>
          </div>

          <div style={s.topbarActions}>
            {resumeSessionId && (
              <button style={s.actionBtn} onClick={handleNewChat} title="Start a new chat">
                + New chat
              </button>
            )}
            <Link to={`/twin/${twin.id}/sources`} style={s.actionBtn}>
              <IconDatabase />
              Sources
              {sources.length > 0 && (
                <span style={s.sourceCount}>{sources.length}</span>
              )}
            </Link>
            <Link to={`/twin/${twin.id}/config`} style={s.actionBtn}>
              <IconSettings />
              Config
            </Link>
            <button
              style={{ ...s.actionBtn, ...(sidebarMode === "sessions" ? s.actionBtnActive : {}) }}
              onClick={() => setSidebarMode((m) => m === "sessions" ? "sources" : "sessions")}
              title="Session history"
            >
              <IconHistory />
              History
              {sessions.length > 0 && (
                <span style={s.sourceCount}>{sessions.length}</span>
              )}
            </button>
            <button
              style={{ ...s.actionBtn, ...(sidebarMode === "sources" ? s.actionBtnActive : {}) }}
              onClick={() => setSidebarMode((m) => m === "sources" ? null : "sources")}
              title="Toggle sources panel"
            >
              <IconPanel />
            </button>
          </div>
        </div>

        {/* ── Body: chat + sidebar ───────────────────────────────────────── */}
        <div style={s.body}>
          <RichConversationPanel
            messages={messages}
            isSending={isSending}
            chatError={chatError}
            inputValue={inputValue}
            onInputChange={setInputValue}
            onKeyDown={handleKeyDown}
            onSend={handleSend}
            placeholder={`Ask ${displayName} anything…`}
            accentColor={accentColor}
            avatarLetter={displayName[0]?.toUpperCase() ?? "T"}
            emptyState={
              !hasSources
                ? <NoSourcesPrompt twinId={twin.id} />
                : <MemoryBriefPanel twinId={twin.id} displayName={displayName} />
            }
          />

          {/* Right sidebar — sources or session history */}
          {sidebarMode === "sources" && (
            <aside style={s.sidebar}>
              <div style={s.sidebarHeader}>
                <span style={s.sidebarTitle}>Sources</span>
                <Link to={`/twin/${twin.id}/sources`} style={s.sidebarManageLink}>
                  Manage
                </Link>
              </div>

              {sources.length === 0 ? (
                <div style={s.sidebarEmpty}>
                  <p style={s.sidebarEmptyText}>No sources connected yet.</p>
                  <Link to={`/twin/${twin.id}/sources`} style={s.sidebarAddLink}>
                    + Add a source
                  </Link>
                </div>
              ) : (
                <ul style={s.sourceList}>
                  {sources.map((src) => (
                    <SourceRow key={src.id} source={src} />
                  ))}
                </ul>
              )}

              <div style={s.policyNote}>
                <IconShield />
                <span>
                  Answers are grounded in approved sources only. Raw content is never exposed.
                </span>
              </div>
            </aside>
          )}

          {sidebarMode === "sessions" && (
            <aside style={s.sidebar}>
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

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ active }: { active: boolean }) {
  return (
    <span style={s.statusRow}>
      <span
        style={{
          ...s.statusDot,
          background: active ? "var(--color-teal)" : "var(--color-text-tertiary)",
        }}
      />
      <span style={s.statusLabel}>{active ? "Active" : "Inactive"}</span>
    </span>
  );
}

function SourceRow({ source }: { source: Source }) {
  return (
    <li style={s.sourceRow}>
      <span
        style={{
          ...s.sourceStatusDot,
          background: STATUS_COLOR[source.status] ?? "var(--color-text-tertiary)",
        }}
      />
      <div style={s.sourceRowContent}>
        <span style={s.sourceRowName}>{source.name}</span>
        <span style={s.sourceRowType}>{SOURCE_LABEL[source.source_type] ?? source.source_type}</span>
      </div>
    </li>
  );
}

function NoSourcesPrompt({ twinId }: { twinId: string }) {
  return (
    <div style={s.promptCard}>
      <div style={s.promptOrb}>
        <IconDatabase />
      </div>
      <h2 style={s.promptTitle}>Connect a source to get started</h2>
      <p style={s.promptBody}>
        This twin has no knowledge sources yet. Add a GitHub repo, PDF, website, or other source so it can answer questions.
      </p>
      <Link to={`/twin/${twinId}/sources`} style={s.promptCta}>
        Add first source
      </Link>
    </div>
  );
}

function MemoryBriefPanel({
  twinId,
  displayName,
}: {
  twinId: string;
  displayName: string;
}) {
  const { data: brief, isLoading, isError } = useMemoryBrief(twinId);
  const trigger = useTriggerMemoryGeneration();

  // "ready" — show the brief
  if (brief?.status === "ready" && brief.brief) {
    return (
      <div style={s.briefPanel}>
        <div style={s.briefHeader}>
          <span style={s.briefLabel}>Engineering Memory</span>
          <span style={s.briefTimestamp}>
            {brief.generated_at
              ? `Generated ${new Date(brief.generated_at).toLocaleDateString()}`
              : ""}
          </span>
          <button
            style={s.briefRegenerateBtn}
            onClick={() => trigger.mutate(twinId)}
            disabled={trigger.isPending}
            title="Regenerate Memory Brief"
          >
            {trigger.isPending ? "Queued…" : "Regenerate"}
          </button>
        </div>
        <div style={s.briefContent}>
          <AssistantMarkdown content={brief.brief} />
        </div>
        <p style={s.briefFooter}>
          Start typing below to ask {displayName} a question.
        </p>
      </div>
    );
  }

  // "generating" — show spinner
  if (brief?.status === "generating") {
    return (
      <div style={s.promptCard}>
        <div style={{ ...s.promptOrb, background: "var(--color-iris-muted)" }}>
          <span style={s.spinnerSmall} />
        </div>
        <h2 style={s.promptTitle}>Generating engineering memory…</h2>
        <p style={s.promptBody}>
          Analysing architecture, risks, and recent changes for {displayName}. This takes 30–90 seconds.
        </p>
      </div>
    );
  }

  // No brief yet, or failed — prompt to generate
  return (
    <div style={s.promptCard}>
      <div style={s.promptOrb}>
        <IconMemory />
      </div>
      <h2 style={s.promptTitle}>No engineering memory yet</h2>
      <p style={s.promptBody}>
        Generate a structured overview of {displayName} — architecture, risks, recent changes, and onboarding path. Takes 30–90 seconds.
      </p>
      {brief?.status === "failed" && (
        <p style={{ ...s.promptBody, color: "var(--color-rose)", marginTop: 0 }}>
          Previous generation failed. Try again.
        </p>
      )}
      <button
        style={s.promptCta as React.CSSProperties}
        onClick={() => trigger.mutate(twinId)}
        disabled={trigger.isPending || isLoading}
      >
        {trigger.isPending ? "Queued…" : "Generate Memory Brief"}
      </button>
      <p style={s.promptBodySmall}>
        Or start chatting — questions are answered from your connected sources.
      </p>
    </div>
  );
}

// ─── Session History Panel ────────────────────────────────────────────────────

// ─── Inline SVG icons ─────────────────────────────────────────────────────────

function IconDatabase() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
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

function IconHistory() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 .49-4.95" />
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

function IconChat() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconMemory() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a4 4 0 0 1 4 4v1h1a3 3 0 0 1 0 6h-1v1a4 4 0 0 1-8 0v-1H7a3 3 0 0 1 0-6h1V6a4 4 0 0 1 4-4z" />
      <path d="M9 12h6" />
      <path d="M12 9v6" />
    </svg>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    background: "var(--color-bg)",
    overflow: "hidden",
  },

  // Topbar
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
  twinAvatar: {
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
  twinName: {
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
  },
  slugChip: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    fontFamily: "var(--font-mono)",
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 4,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: "50%",
    display: "inline-block",
  },
  statusLabel: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
  },
  badge_public: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--color-teal)",
    background: "rgba(20,184,166,0.1)",
    padding: "1px 6px",
    borderRadius: 4,
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
  },
  topbarActions: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
  },
  actionBtn: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-secondary)",
    fontSize: 13,
    fontFamily: "var(--font-body)",
    cursor: "pointer",
    textDecoration: "none",
    transition: "background 0.1s, border-color 0.1s",
  },
  actionBtnActive: {
    background: "var(--color-iris-muted)",
    borderColor: "var(--color-iris)",
    color: "var(--color-iris)",
  },
  sourceCount: {
    background: "var(--color-iris-muted)",
    color: "var(--color-iris)",
    fontSize: 10,
    fontWeight: 700,
    padding: "1px 5px",
    borderRadius: 10,
    marginLeft: 2,
  },

  // Body layout
  body: {
    flex: 1,
    display: "flex",
    overflow: "hidden",
    minHeight: 0
    
  },

  // Chat column
  chatCol: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minWidth: 0,
  },
  messagesList: {
    flex: 1,
    overflowY: "auto",
    padding: "24px 32px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  emptyChat: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 0",
  },
  messageBubbleWrap: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
  },
  messageAvatar: {
    width: 28,
    height: 28,
    borderRadius: 8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    fontWeight: 700,
    fontSize: 12,
    flexShrink: 0,
  },
  messageBubble: {
    padding: "10px 14px",
    borderRadius: 12,
    fontSize: 14,
    lineHeight: 1.6,
    maxWidth: 600,
    wordBreak: "break-word" as const,
  },
  typingDots: {
    display: "inline-flex",
    gap: 4,
    alignItems: "center",
    height: 16,
  },
  chatError: {
    margin: "0 32px 8px",
    padding: "10px 14px",
    background: "rgba(244,63,94,0.08)",
    border: "1px solid rgba(244,63,94,0.2)",
    borderRadius: 8,
    color: "var(--color-rose)",
    fontSize: 13,
  },

  // Input bar
  inputBar: {
    padding: "16px 32px 20px",
    borderTop: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    flexShrink: 0,
  },
  inputWrap: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 12,
    padding: "10px 12px",
  },
  textarea: {
    flex: 1,
    background: "transparent",
    border: "none",
    outline: "none",
    fontFamily: "var(--font-body)",
    fontSize: 14,
    color: "var(--color-text-primary)",
    resize: "none" as const,
    lineHeight: 1.5,
    maxHeight: 160,
    overflowY: "auto" as const,
  },
  sendBtn: {
    width: 32,
    height: 32,
    borderRadius: 8,
    border: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    flexShrink: 0,
    transition: "background 0.1s",
  },
  inputHint: {
    margin: "6px 0 0",
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    textAlign: "center" as const,
  },

  // Sources sidebar
  sidebar: {
    // width: 280,
    minWidth: 280,
    borderLeft: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  sidebarHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px 12px",
    borderBottom: "1px solid var(--color-border)",
    flexShrink: 0,
  },
  sidebarTitle: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: 13,
    color: "var(--color-text-primary)",
  },
  sidebarManageLink: {
    fontSize: 12,
    color: "var(--color-iris)",
    textDecoration: "none",
  },
  sidebarEmpty: {
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
    alignItems: "flex-start",
  },
  sidebarEmptyText: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    margin: 0,
  },
  sidebarAddLink: {
    fontSize: 13,
    color: "var(--color-iris)",
    textDecoration: "none",
    fontWeight: 600,
  },
  sourceList: {
    listStyle: "none",
    margin: 0,
    padding: "8px 0",
    overflowY: "auto",
    flex: 1,
  },
  sourceRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 20px",
  },
  sourceStatusDot: {
    width: 7,
    height: 7,
    borderRadius: "50%",
    flexShrink: 0,
  },
  sourceRowContent: {
    display: "flex",
    flexDirection: "column",
    gap: 1,
    minWidth: 0,
  },
  sourceRowName: {
    fontSize: 13,
    color: "var(--color-text-primary)",
    fontWeight: 500,
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  sourceRowType: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
  },
  policyNote: {
    display: "flex",
    alignItems: "flex-start",
    gap: 6,
    padding: "12px 20px 16px",
    borderTop: "1px solid var(--color-border)",
    flexShrink: 0,
    color: "var(--color-text-tertiary)",
    fontSize: 11,
    lineHeight: 1.5,
  },

  // Empty/prompt states
  promptCard: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center" as const,
    maxWidth: 400,
    margin: "0 auto",
    gap: 12,
  },
  promptOrb: {
    width: 56,
    height: 56,
    borderRadius: 16,
    background: "var(--color-iris-muted)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "var(--color-iris)",
    fontSize: 24,
    marginBottom: 4,
  },
  promptTitle: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: 18,
    color: "var(--color-text-primary)",
    margin: 0,
  },
  promptBody: {
    fontSize: 14,
    color: "var(--color-text-secondary)",
    lineHeight: 1.6,
    margin: 0,
  },
  promptCta: {
    marginTop: 4,
    display: "inline-block",
    padding: "9px 20px",
    borderRadius: 8,
    background: "var(--color-iris)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    textDecoration: "none",
  },

  // Routing hint
  routingHint: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    marginTop: 6,
  },

  // ── Markdown body ───────────────────────────────────────────────────────
  mdBody: {
    fontSize: 14,
    lineHeight: 1.65,
    color: "var(--color-text-primary)",
  },
  mdP: { margin: "0 0 10px" },
  mdH1: { fontSize: 17, fontWeight: 700, margin: "14px 0 6px", color: "var(--color-text-primary)" },
  mdH2: { fontSize: 15, fontWeight: 700, margin: "12px 0 6px", color: "var(--color-text-primary)" },
  mdH3: { fontSize: 14, fontWeight: 600, margin: "10px 0 4px", color: "var(--color-text-primary)" },
  mdUl: { margin: "0 0 10px", paddingLeft: 20 },
  mdOl: { margin: "0 0 10px", paddingLeft: 20 },
  mdLi: { marginBottom: 4, lineHeight: 1.6 },
  mdBlockquote: {
    borderLeft: "3px solid var(--color-border)",
    margin: "10px 0",
    paddingLeft: 14,
    color: "var(--color-text-secondary)",
    fontStyle: "italic",
  },
  mdTable: { width: "100%", borderCollapse: "collapse" as const, fontSize: 13 },
  mdTh: {
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    padding: "7px 12px",
    textAlign: "left" as const,
    fontWeight: 600,
    fontSize: 12,
  },
  mdTd: {
    border: "1px solid var(--color-border)",
    padding: "7px 12px",
    fontSize: 13,
  },
  mdLink: { color: "var(--color-iris)", textDecoration: "underline" },

  // ── Code blocks ─────────────────────────────────────────────────────────
  codeBlock: {
    margin: "10px 0",
    borderRadius: 8,
    overflow: "hidden",
    border: "1px solid var(--color-border)",
  },
  codeHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "var(--color-bg)",
    borderBottom: "1px solid var(--color-border)",
    padding: "5px 12px",
  },
  codeLang: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--color-text-tertiary)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    fontFamily: "var(--font-mono)",
  },
  codeHighlighter: {
    margin: 0,
    padding: "12px 16px",
    fontSize: 13,
    background: "var(--color-surface)",
    fontFamily: "var(--font-mono)",
    borderRadius: 0,
  },
  inlineCode: {
    fontFamily: "var(--font-mono)",
    fontSize: "0.88em",
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 4,
    padding: "1px 5px",
    color: "var(--color-text-primary)",
  },
  copyBtn: {
    background: "none",
    border: "1px solid var(--color-border)",
    borderRadius: 4,
    padding: "2px 8px",
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    cursor: "pointer",
    fontFamily: "inherit",
  },

  // ── Memory Brief Panel ───────────────────────────────────────────────────
  briefPanel: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    width: "100%",
    maxWidth: 720,
    margin: "0 auto",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 12,
    overflow: "hidden",
  },
  briefHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "12px 20px",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    flexShrink: 0,
  },
  briefLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--color-iris)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.07em",
    fontFamily: "var(--font-display)",
  },
  briefTimestamp: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    flex: 1,
  },
  briefRegenerateBtn: {
    background: "none",
    border: "1px solid var(--color-border)",
    borderRadius: 6,
    padding: "3px 10px",
    fontSize: 11,
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  briefContent: {
    padding: "16px 24px",
    overflowY: "auto" as const,
    maxHeight: "50vh",
  },
  briefFooter: {
    padding: "10px 24px 14px",
    fontSize: 12,
    color: "var(--color-text-tertiary)",
    margin: 0,
    borderTop: "1px solid var(--color-border)",
    textAlign: "center" as const,
  },
  promptBodySmall: {
    fontSize: 12,
    color: "var(--color-text-tertiary)",
    margin: 0,
    lineHeight: 1.5,
  },
  spinnerSmall: {
    display: "inline-block",
    width: 20,
    height: 20,
    borderRadius: "50%",
    border: "2.5px solid var(--color-iris-muted)",
    borderTopColor: "var(--color-iris)",
    animation: "spin 0.7s linear infinite",
  },

  // Loading
  loadingWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
  },
  spinner: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    border: "3px solid var(--color-border)",
    borderTopColor: "var(--color-iris)",
    animation: "spin 0.7s linear infinite",
  },
};
