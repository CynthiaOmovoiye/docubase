import { useEffect, useRef, useState, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";

import type { ChatSessionSummary, Message } from "@/types";

interface RichConversationPanelProps {
  messages: Message[];
  isSending: boolean;
  chatError: string | null;
  inputValue: string;
  onInputChange: (value: string) => void;
  onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement>;
  onSend: () => void;
  placeholder: string;
  accentColor: string;
  avatarLetter: string;
  emptyState: React.ReactNode;
  inputHint?: string;
}

export function RichConversationPanel({
  messages,
  isSending,
  chatError,
  inputValue,
  onInputChange,
  onKeyDown,
  onSend,
  placeholder,
  accentColor,
  avatarLetter,
  emptyState,
  inputHint = "Enter to send · Shift+Enter for new line",
}: RichConversationPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  return (
    <div style={s.chatCol}>
      <div style={s.messagesList}>
        {messages.length === 0 && (
          <div style={s.emptyChat}>{emptyState}</div>
        )}

        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            accentColor={accentColor}
            avatarLetter={avatarLetter}
          />
        ))}

        {isSending && (
          <TypingIndicator accentColor={accentColor} avatarLetter={avatarLetter} />
        )}

        <div ref={bottomRef} />
      </div>

      {chatError && <div style={s.chatError}>{chatError}</div>}

      <div style={s.inputBar}>
        <div style={s.inputWrap}>
          <textarea
            ref={inputRef}
            style={s.textarea}
            placeholder={placeholder}
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            disabled={isSending}
          />
          <button
            style={{
              ...s.sendBtn,
              background: inputValue.trim() ? accentColor : "var(--color-border)",
              cursor: inputValue.trim() ? "pointer" : "default",
            }}
            onClick={onSend}
            disabled={!inputValue.trim() || isSending}
          >
            <IconSend />
          </button>
        </div>
        <p style={s.inputHint}>{inputHint}</p>
      </div>
    </div>
  );
}

export function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div style={s.mdBody}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children }) {
            const match = /language-(\w+)/.exec(className ?? "");
            const isBlock = !!match || String(children).includes("\n");
            const codeStr = String(children).replace(/\n$/, "");
            if (isBlock) {
              const lang = match?.[1] ?? "text";
              return (
                <div style={s.codeBlock}>
                  <div style={s.codeHeader}>
                    <span style={s.codeLang}>{lang}</span>
                    <CopyCodeButton text={codeStr} />
                  </div>
                  <SyntaxHighlighter
                    style={oneLight}
                    language={lang}
                    PreTag="div"
                    customStyle={s.codeHighlighter}
                  >
                    {codeStr}
                  </SyntaxHighlighter>
                </div>
              );
            }
            return <code style={s.inlineCode}>{children}</code>;
          },
          p: ({ children }) => <p style={s.mdP}>{children}</p>,
          h1: ({ children }) => <h1 style={s.mdH1}>{children}</h1>,
          h2: ({ children }) => <h2 style={s.mdH2}>{children}</h2>,
          h3: ({ children }) => <h3 style={s.mdH3}>{children}</h3>,
          ul: ({ children }) => <ul style={s.mdUl}>{children}</ul>,
          ol: ({ children }) => <ol style={s.mdOl}>{children}</ol>,
          li: ({ children }) => <li style={s.mdLi}>{children}</li>,
          blockquote: ({ children }) => <blockquote style={s.mdBlockquote}>{children}</blockquote>,
          table: ({ children }) => (
            <div style={{ overflowX: "auto", margin: "10px 0" }}>
              <table style={s.mdTable}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th style={s.mdTh}>{children}</th>,
          td: ({ children }) => <td style={s.mdTd}>{children}</td>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" style={s.mdLink}>
              {children}
            </a>
          ),
          strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function SessionHistoryPanel({
  sessions,
  activeSessionId,
  onResume,
}: {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  onResume: (id: string) => void;
}) {
  if (sessions.length === 0) {
    return (
      <div style={s.sidebarEmpty}>
        <p style={s.sidebarEmptyText}>No past conversations yet.</p>
        <p style={{ ...s.sidebarEmptyText, marginTop: 4, fontSize: 12 }}>
          Start chatting and your sessions will appear here.
        </p>
      </div>
    );
  }

  return (
    <ul style={s.historyList}>
      {sessions.map((session) => {
        const isActive = session.session_id === activeSessionId;
        const date = new Date(session.last_message_at ?? session.created_at);
        const dateLabel = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
        const timeLabel = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

        return (
          <li
            key={session.session_id}
            style={{
              ...s.sessionItem,
              background: isActive ? "var(--color-iris-muted)" : "transparent",
              borderLeft: isActive ? "2px solid var(--color-iris)" : "2px solid transparent",
            }}
            onClick={() => onResume(session.session_id)}
          >
            <div style={s.sessionMeta}>
              <span style={s.sessionDate}>{dateLabel} · {timeLabel}</span>
              <span style={s.sessionCount}>{session.message_count} msgs</span>
            </div>
            {session.preview && (
              <p style={s.sessionPreview}>
                {session.preview.length > 80
                  ? session.preview.slice(0, 80) + "…"
                  : session.preview}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function MessageBubble({
  message,
  accentColor,
  avatarLetter,
}: {
  message: Message;
  accentColor: string;
  avatarLetter: string;
}) {
  const isUser = message.role === "user";
  return (
    <div
      style={{
        ...s.messageBubbleWrap,
        justifyContent: isUser ? "flex-end" : "flex-start",
        alignItems: "flex-start",
      }}
    >
      {!isUser && (
        <div style={{ ...s.messageAvatar, background: accentColor }}>
          {avatarLetter}
        </div>
      )}
      <div
        style={{
          ...s.messageBubble,
          background: isUser ? accentColor : "var(--color-surface)",
          border: isUser ? "none" : "1px solid var(--color-border)",
          color: isUser ? "#fff" : "var(--color-text-primary)",
          marginLeft: isUser ? 48 : 0,
          marginRight: isUser ? 0 : 48,
          borderRadius: isUser ? "14px 14px 4px 14px" : "4px 14px 14px 14px",
        }}
      >
        {isUser ? (
          <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {message.content}
          </span>
        ) : (
          <AssistantMarkdown content={message.content} />
        )}
        {message.routed_twin_id && !isUser && (
          <div style={s.routingHint}>↳ via workspace routing</div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator({
  accentColor,
  avatarLetter,
}: {
  accentColor: string;
  avatarLetter: string;
}) {
  return (
    <div style={{ ...s.messageBubbleWrap, justifyContent: "flex-start", alignItems: "flex-end" }}>
      <div style={{ ...s.messageAvatar, background: accentColor }}>
        {avatarLetter}
      </div>
      <div
        style={{
          ...s.messageBubble,
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "4px 14px 14px 14px",
          padding: "12px 16px",
        }}
      >
        <span style={s.typingDots}>
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </span>
      </div>
    </div>
  );
}

function CopyCodeButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      style={s.copyBtn}
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
    >
      {copied ? "✓ Copied" : "Copy"}
    </button>
  );
}

function IconSend() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

const s: Record<string, CSSProperties> = {
  chatCol: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minWidth: 0,
    minHeight: 0,
    background: "var(--color-surface)",
  },
  messagesList: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "24px 24px 18px",
    display: "flex",
    flexDirection: "column",
    gap: 18,
  },
  emptyChat: {
    flex: 1,
    minHeight: 420,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  chatError: {
    margin: "0 20px 10px",
    padding: "10px 12px",
    borderRadius: 10,
    background: "rgba(239,68,68,0.08)",
    color: "var(--color-rose)",
    fontSize: 13,
    border: "1px solid rgba(239,68,68,0.16)",
  },
  inputBar: {
    padding: "0 20px 18px",
    flexShrink: 0,
  },
  inputWrap: {
    display: "flex",
    alignItems: "flex-end",
    gap: 10,
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 16,
    padding: "10px 12px 10px 14px",
  },
  textarea: {
    flex: 1,
    minHeight: 24,
    maxHeight: 180,
    resize: "none",
    border: "none",
    outline: "none",
    background: "transparent",
    color: "var(--color-text-primary)",
    fontSize: 14,
    fontFamily: "var(--font-body)",
    lineHeight: 1.5,
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 12,
    border: "none",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  inputHint: {
    margin: "8px 4px 0",
    fontSize: 11,
    color: "var(--color-text-tertiary)",
  },
  messageBubbleWrap: {
    display: "flex",
    gap: 12,
  },
  messageAvatar: {
    width: 34,
    height: 34,
    borderRadius: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    flexShrink: 0,
  },
  messageBubble: {
    maxWidth: "min(780px, calc(100% - 60px))",
    padding: "14px 16px",
    boxShadow: "var(--shadow-sm)",
    fontSize: 14,
    lineHeight: 1.6,
    wordBreak: "break-word",
  },
  routingHint: {
    marginTop: 12,
    fontSize: 11,
    color: "var(--color-text-tertiary)",
  },
  mdBody: {
    color: "inherit",
  },
  mdP: {
    margin: "0 0 12px",
  },
  mdH1: {
    margin: "8px 0 12px",
    fontSize: 20,
    lineHeight: 1.2,
    fontWeight: 700,
  },
  mdH2: {
    margin: "8px 0 10px",
    fontSize: 17,
    lineHeight: 1.3,
    fontWeight: 700,
  },
  mdH3: {
    margin: "8px 0 8px",
    fontSize: 15,
    lineHeight: 1.35,
    fontWeight: 700,
  },
  mdUl: {
    margin: "0 0 12px 18px",
    padding: 0,
  },
  mdOl: {
    margin: "0 0 12px 18px",
    padding: 0,
  },
  mdLi: {
    marginBottom: 6,
  },
  mdBlockquote: {
    margin: "12px 0",
    padding: "8px 0 8px 12px",
    borderLeft: "3px solid var(--color-border)",
    color: "var(--color-text-secondary)",
  },
  mdTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  mdTh: {
    textAlign: "left",
    padding: "8px 10px",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-bg)",
  },
  mdTd: {
    padding: "8px 10px",
    borderBottom: "1px solid var(--color-border)",
    verticalAlign: "top",
  },
  mdLink: {
    color: "var(--color-iris)",
    textDecoration: "underline",
  },
  codeBlock: {
    margin: "12px 0",
    borderRadius: 12,
    overflow: "hidden",
    border: "1px solid var(--color-border)",
    background: "#fff",
  },
  codeHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 10px",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-bg)",
  },
  codeLang: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--color-text-secondary)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  codeHighlighter: {
    margin: 0,
    padding: "14px 16px",
    background: "#fff",
    fontSize: 13,
    lineHeight: 1.6,
  },
  inlineCode: {
    fontFamily: "var(--font-mono)",
    fontSize: "0.92em",
    padding: "0.15em 0.35em",
    borderRadius: 6,
    background: "rgba(99,102,241,0.08)",
  },
  copyBtn: {
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    borderRadius: 8,
    padding: "5px 8px",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
  },
  typingDots: {
    display: "inline-flex",
    gap: 6,
    alignItems: "center",
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
  historyList: {
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
  sessionItem: {
    padding: "10px 14px",
    cursor: "pointer",
    borderRadius: 6,
    marginBottom: 2,
    transition: "background 0.1s",
  },
  sessionMeta: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  sessionDate: {
    fontSize: 11,
    color: "var(--color-text-secondary)",
    fontWeight: 500,
  },
  sessionCount: {
    fontSize: 10,
    color: "var(--color-text-secondary)",
    background: "var(--color-bg)",
    borderRadius: 10,
    padding: "1px 6px",
  },
  sessionPreview: {
    fontSize: 12,
    color: "var(--color-text-primary)",
    margin: 0,
    lineHeight: 1.4,
    opacity: 0.8,
  },
};
