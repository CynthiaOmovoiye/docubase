/**
 * Public share page chat — same conversation UI as authenticated workspace/twin chat,
 * plus optional visitor id (opaque) for listing and resuming sessions.
 */

import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  RichConversationPanel,
  SessionHistoryPanel,
} from "@/features/chat/components/RichConversationPanel";
import { useChat, usePublicChatSessions } from "@/features/chat/hooks/useChat";
import {
  clearStoredVisitorId,
  generateVisitorId,
  getStoredVisitorId,
  setStoredVisitorId,
} from "@/lib/publicVisitorId";

export interface PublicChatShellProps {
  publicSlug: string;
  displayName: string;
  accentColor: string;
  placeholder: string;
  emptyState: React.ReactNode;
  eyebrow?: string;
  subtitle?: string | null;
}

export function PublicChatShell({
  publicSlug,
  displayName,
  accentColor,
  placeholder,
  emptyState,
  eyebrow = "Public chat",
  subtitle,
}: PublicChatShellProps) {
  const qc = useQueryClient();
  const [visitorId, setVisitorId] = useState<string | null>(null);
  const [draftVisitor, setDraftVisitor] = useState("");
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);
  const [sidebarMode, setSidebarMode] = useState<"settings" | "history" | null>(null);
  const [inputValue, setInputValue] = useState("");

  useEffect(() => {
    setVisitorId(getStoredVisitorId(publicSlug));
    setResumeSessionId(null);
    setDraftVisitor("");
    setSidebarMode(null);
  }, [publicSlug]);

  const {
    messages,
    isLoading: isSending,
    error: chatError,
    sendMessage,
    startNewSession,
  } = useChat({ publicSlug, visitorId, resumeSessionId });

  const { data: sessions = [], refetch: refetchSessions } = usePublicChatSessions(
    publicSlug,
    visitorId,
  );

  const avatarLetter = displayName.charAt(0).toUpperCase();

  function resumeSession(id: string) {
    setResumeSessionId(id);
    setSidebarMode("history");
  }

  function handleNewChat() {
    setResumeSessionId(null);
    startNewSession();
  }

  const afterSend = useCallback(() => {
    if (visitorId) {
      void refetchSessions();
      void qc.invalidateQueries({ queryKey: ["chat", "public-sessions", publicSlug, visitorId] });
    }
  }, [visitorId, publicSlug, qc, refetchSessions]);

  async function handleSend() {
    if (!inputValue.trim() || isSending) return;
    const text = inputValue.trim();
    setInputValue("");
    await sendMessage(text);
    afterSend();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function persistVisitor(next: string | null) {
    if (next && next.trim().length >= 8) {
      const v = next.trim();
      setStoredVisitorId(publicSlug, v);
      setVisitorId(v);
      setDraftVisitor("");
      handleNewChat();
      void qc.invalidateQueries({ queryKey: ["chat", "public-sessions", publicSlug, v] });
    } else {
      clearStoredVisitorId(publicSlug);
      setVisitorId(null);
      setDraftVisitor("");
      handleNewChat();
    }
  }

  function handleGenerate() {
    persistVisitor(generateVisitorId());
  }

  function handleApplyDraft() {
    const t = draftVisitor.trim();
    if (t.length >= 8) persistVisitor(t);
  }

  return (
    <div style={s.page}>
      <header style={s.topbar}>
        <div style={s.topbarLeft}>
          <div style={{ ...s.avatar, background: accentColor }}>{avatarLetter}</div>
          <div style={s.topbarMeta}>
            <p style={s.eyebrow}>{eyebrow}</p>
            <h1 style={s.title}>{displayName}</h1>
            {subtitle && <p style={s.subtitle}>{subtitle}</p>}
          </div>
        </div>
        <div style={s.topbarActions}>
          {resumeSessionId && (
            <button type="button" style={s.actionBtn} onClick={handleNewChat}>
              + New chat
            </button>
          )}
          <button
            type="button"
            style={{ ...s.actionBtn, ...(sidebarMode === "history" ? s.actionBtnActive : {}) }}
            onClick={() => setSidebarMode((m) => (m === "history" ? null : "history"))}
            title={visitorId ? "Past conversations" : "Save a visitor ID first"}
          >
            History
            {visitorId && sessions.length > 0 && <span style={s.countPill}>{sessions.length}</span>}
          </button>
          <button
            type="button"
            style={{ ...s.actionBtn, ...(sidebarMode === "settings" ? s.actionBtnActive : {}) }}
            onClick={() => setSidebarMode((m) => (m === "settings" ? null : "settings"))}
          >
            Visitor ID
          </button>
        </div>
      </header>

      <div style={sidebarMode ? s.bodyWithSidebar : s.bodyFull}>
        <RichConversationPanel
          messages={messages}
          isSending={isSending}
          chatError={chatError}
          inputValue={inputValue}
          onInputChange={setInputValue}
          onKeyDown={handleKeyDown}
          onSend={() => { void handleSend(); }}
          placeholder={placeholder}
          accentColor={accentColor}
          avatarLetter={avatarLetter}
          emptyState={emptyState}
          inputHint={
            visitorId
              ? "Enter to send · Shift+Enter for new line · chats are saved under your visitor ID"
              : "Enter to send · Shift+Enter for new line · without a visitor ID, refresh starts a new chat"
          }
        />

        {sidebarMode === "history" && (
          <aside style={s.sidebar}>
            <div style={s.sidebarHeader}>
              <span style={s.sidebarTitle}>Past chats</span>
              <button type="button" style={s.sidebarLink} onClick={handleNewChat}>
                + New
              </button>
            </div>
            {!visitorId ? (
              <div style={s.sidebarNote}>
                <p style={s.sidebarNoteText}>
                  Open the Visitor ID panel and save a random id (or generate one). Use the same id
                  on any device to list and resume conversations for this link.
                </p>
              </div>
            ) : (
              <SessionHistoryPanel
                sessions={sessions}
                activeSessionId={resumeSessionId}
                onResume={resumeSession}
              />
            )}
          </aside>
        )}

        {sidebarMode === "settings" && (
          <aside style={s.sidebar}>
            <div style={s.sidebarHeader}>
              <span style={s.sidebarTitle}>Visitor ID</span>
            </div>
            <p style={s.settingsIntro}>
              This is a random label, not personal information. It is stored only in your browser
              unless you copy it elsewhere. If you save one, new chats are tied to it so you can
              resume from History. Without it, leaving or refreshing clears the thread.
            </p>
            {visitorId ? (
              <div style={s.idBox}>
                <code style={s.idCode}>{visitorId}</code>
                <div style={s.idRow}>
                  <button type="button" style={s.secondaryBtn} onClick={() => navigator.clipboard.writeText(visitorId)}>
                    Copy
                  </button>
                  <button type="button" style={s.secondaryBtn} onClick={handleGenerate}>
                    New ID
                  </button>
                  <button
                    type="button"
                    style={s.dangerBtn}
                    onClick={() => {
                      persistVisitor(null);
                    }}
                  >
                    Clear
                  </button>
                </div>
              </div>
            ) : (
              <p style={s.muted}>No visitor ID yet — chats are ephemeral.</p>
            )}
            <div style={s.field}>
              <label style={s.label} htmlFor="visitor-import">Import or paste an ID</label>
              <input
                id="visitor-import"
                value={draftVisitor}
                onChange={(e) => setDraftVisitor(e.target.value)}
                style={s.input}
                placeholder="e.g. paste from another device"
                autoComplete="off"
              />
              <button
                type="button"
                style={s.primaryBtn}
                disabled={draftVisitor.trim().length < 8}
                onClick={handleApplyDraft}
              >
                Save ID
              </button>
            </div>
            {!visitorId && (
              <button type="button" style={s.primaryBtn} onClick={handleGenerate}>
                Generate &amp; save ID
              </button>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minHeight: 0,
    background: "var(--color-bg)",
    overflow: "hidden",
  },
  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 20px",
    minHeight: 60,
    background: "var(--color-surface)",
    borderBottom: "1px solid var(--color-border)",
    gap: 12,
    flexShrink: 0,
  },
  topbarLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    minWidth: 0,
  },
  avatar: {
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
    minWidth: 0,
  },
  eyebrow: {
    margin: 0,
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-text-tertiary)",
  },
  title: {
    margin: "2px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 17,
    fontWeight: 700,
    color: "var(--color-text-primary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  subtitle: {
    margin: "4px 0 0",
    fontSize: 12,
    color: "var(--color-text-secondary)",
    lineHeight: 1.45,
    maxWidth: 560,
    overflow: "hidden",
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
    cursor: "pointer",
  },
  actionBtnActive: {
    borderColor: "rgba(99,102,241,0.22)",
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
  bodyFull: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minHeight: 0,
  },
  bodyWithSidebar: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) min(320px, 92vw)",
    flex: 1,
    minHeight: 0,
    minWidth: 0,
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
  sidebarLink: {
    border: "none",
    background: "transparent",
    color: "var(--color-iris)",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    padding: 0,
  },
  sidebarNote: {
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px dashed var(--color-border)",
    background: "var(--color-bg)",
  },
  sidebarNoteText: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  settingsIntro: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.65,
    color: "var(--color-text-secondary)",
  },
  idBox: {
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
  },
  idCode: {
    display: "block",
    fontSize: 12,
    fontFamily: "var(--font-mono)",
    wordBreak: "break-all",
    color: "var(--color-text-primary)",
    marginBottom: 10,
  },
  idRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  secondaryBtn: {
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    color: "var(--color-text-primary)",
  },
  dangerBtn: {
    padding: "6px 12px",
    borderRadius: 8,
    border: "1px solid rgba(239,68,68,0.35)",
    background: "transparent",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    color: "var(--color-rose)",
  },
  muted: {
    margin: 0,
    fontSize: 13,
    color: "var(--color-text-tertiary)",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid var(--color-border)",
    fontSize: 13,
    fontFamily: "var(--font-mono)",
    background: "var(--color-bg)",
    color: "var(--color-text-primary)",
  },
  primaryBtn: {
    padding: "10px 14px",
    borderRadius: 10,
    border: "none",
    background: "var(--color-iris)",
    color: "#fff",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
  },
};
