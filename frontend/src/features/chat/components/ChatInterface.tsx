/**
 * ChatInterface component.
 *
 * Reusable chat UI — works for:
 * - Authenticated single-twin chat
 * - Authenticated workspace-wide chat
 * - Public share page chat (no auth)
 * - Embed widget chat
 *
 * Assistant messages are rendered as full Markdown with:
 * - GFM tables, task lists, strikethrough
 * - Syntax-highlighted fenced code blocks (via react-syntax-highlighter)
 * - Inline code styling
 * - Proper heading hierarchy
 */

import { useState, useRef, useEffect, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useChat } from "../hooks/useChat";
import type { Message } from "@/types";

interface ChatInterfaceProps {
  twinId?: string;
  workspaceId?: string;
  publicSlug?: string;
  placeholder?: string;
  twinName?: string;
  accentColor?: string;
}

export function ChatInterface({
  twinId,
  workspaceId,
  publicSlug,
  placeholder = "Ask anything about this project...",
  twinName = "Twin",
  accentColor,
}: ChatInterfaceProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { messages, isLoading, error, sendMessage, startSession } = useChat({
    twinId,
    workspaceId,
    publicSlug,
  });

  useEffect(() => {
    startSession();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    const content = input.trim();
    setInput("");
    await sendMessage(content);
  };

  const accent = accentColor ?? "#6366F1";

  return (
    <div style={s.root}>
      {/* Messages */}
      <div style={s.messageList}>
        {messages.length === 0 && (
          <div style={s.empty}>
            <div style={{ ...s.emptyOrb, background: accent }}>
              {twinName.charAt(0).toUpperCase()}
            </div>
            <p style={s.emptyName}>{twinName}</p>
            <p style={s.emptyHint}>Ask me anything about this project.</p>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            twinName={twinName}
            accent={accent}
          />
        ))}

        {isLoading && (
          <div style={s.thinkingRow}>
            <ThinkingDots />
          </div>
        )}

        {error && <div style={s.errorBanner}>{error}</div>}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={s.inputArea}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          disabled={isLoading}
          style={s.input}
          onFocus={(e) => { e.currentTarget.style.borderColor = accent; }}
          onBlur={(e) => { e.currentTarget.style.borderColor = "#E5E7EB"; }}
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          style={{ ...s.sendBtn, background: accent }}
        >
          <SendIcon />
        </button>
      </form>
    </div>
  );
}

// ─── MessageBubble ─────────────────────────────────────────────────────────

function MessageBubble({
  message,
  twinName,
  accent,
}: {
  message: Message;
  twinName: string;
  accent: string;
}) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div style={s.userRow}>
        <div style={{ ...s.userBubble, background: accent }}>
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div style={s.assistantRow}>
      <div style={{ ...s.avatar, background: accent }}>
        {twinName.charAt(0).toUpperCase()}
      </div>
      <div style={s.assistantBubble}>
        <span style={s.assistantName}>{twinName}</span>
        <MarkdownContent content={message.content} />
        {message.routed_twin_id && (
          <span style={s.routingHint}>↳ via workspace routing</span>
        )}
      </div>
    </div>
  );
}

// ─── MarkdownContent ───────────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <div style={s.markdownBody}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // ── Code blocks ──────────────────────────────────────────────────
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className ?? "");
            const isBlock = !!match || String(children).includes("\n");
            const codeStr = String(children).replace(/\n$/, "");

            if (isBlock) {
              const lang = match?.[1] ?? "text";
              return (
                <div style={s.codeBlock}>
                  <div style={s.codeHeader}>
                    <span style={s.codeLang}>{lang}</span>
                    <CopyButton text={codeStr} />
                  </div>
                  <SyntaxHighlighter
                    style={oneLight}
                    language={lang}
                    PreTag="div"
                    customStyle={s.codeHighlighter}
                    codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
                  >
                    {codeStr}
                  </SyntaxHighlighter>
                </div>
              );
            }

            // Inline code
            return (
              <code style={s.inlineCode} {...props}>
                {children}
              </code>
            );
          },

          // ── Headings ──────────────────────────────────────────────────
          h1: ({ children }) => <h1 style={s.h1}>{children}</h1>,
          h2: ({ children }) => <h2 style={s.h2}>{children}</h2>,
          h3: ({ children }) => <h3 style={s.h3}>{children}</h3>,

          // ── Paragraphs & lists ───────────────────────────────────────
          p: ({ children }) => <p style={s.p}>{children}</p>,
          ul: ({ children }) => <ul style={s.ul}>{children}</ul>,
          ol: ({ children }) => <ol style={s.ol}>{children}</ol>,
          li: ({ children }) => <li style={s.li}>{children}</li>,

          // ── Block elements ────────────────────────────────────────────
          blockquote: ({ children }) => (
            <blockquote style={s.blockquote}>{children}</blockquote>
          ),
          hr: () => <hr style={s.hr} />,

          // ── Tables (GFM) ──────────────────────────────────────────────
          table: ({ children }) => (
            <div style={s.tableWrapper}>
              <table style={s.table}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th style={s.th}>{children}</th>,
          td: ({ children }) => <td style={s.td}>{children}</td>,

          // ── Links ─────────────────────────────────────────────────────
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={s.link}
            >
              {children}
            </a>
          ),

          // ── Strong / em ───────────────────────────────────────────────
          strong: ({ children }) => (
            <strong style={{ fontWeight: 600 }}>{children}</strong>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ─── CopyButton ────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button onClick={copy} style={s.copyBtn}>
      {copied ? "✓ Copied" : "Copy"}
    </button>
  );
}

// ─── ThinkingDots ──────────────────────────────────────────────────────────

function ThinkingDots() {
  return (
    <div style={s.dots}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            ...s.dot,
            animationDelay: `${i * 0.18}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes dotBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ─── Icons ─────────────────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
    </svg>
  );
}

// ─── Styles ────────────────────────────────────────────────────────────────

const FONT_MONO =
  '"JetBrains Mono", "Fira Code", "Cascadia Code", ui-monospace, SFMono-Regular, monospace';

const s: Record<string, CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    background: "#FAFAFA",
  },

  // ── Message list ───────────────────────────────────────────────────────
  messageList: {
    flex: 1,
    overflowY: "auto",
    padding: "24px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },

  // ── Empty state ────────────────────────────────────────────────────────
  empty: {
    margin: "auto",
    textAlign: "center",
    paddingTop: 48,
  },
  emptyOrb: {
    width: 52,
    height: 52,
    borderRadius: "50%",
    color: "#fff",
    fontSize: 22,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    margin: "0 auto 12px",
  },
  emptyName: {
    fontWeight: 600,
    fontSize: 16,
    color: "#111827",
    margin: "0 0 4px",
  },
  emptyHint: {
    fontSize: 14,
    color: "#9CA3AF",
    margin: 0,
  },

  // ── User message ───────────────────────────────────────────────────────
  userRow: {
    display: "flex",
    justifyContent: "flex-end",
  },
  userBubble: {
    maxWidth: "72%",
    borderRadius: "18px 18px 4px 18px",
    padding: "10px 16px",
    fontSize: 14,
    lineHeight: "1.55",
    color: "#fff",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },

  // ── Assistant message ──────────────────────────────────────────────────
  assistantRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
  },
  avatar: {
    flexShrink: 0,
    width: 32,
    height: 32,
    borderRadius: "50%",
    color: "#fff",
    fontSize: 13,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  assistantBubble: {
    flex: 1,
    minWidth: 0,
    background: "#fff",
    border: "1px solid #E5E7EB",
    borderRadius: "4px 18px 18px 18px",
    padding: "12px 16px",
  },
  assistantName: {
    display: "block",
    fontSize: 11,
    fontWeight: 600,
    color: "#9CA3AF",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: 6,
  },
  routingHint: {
    display: "block",
    fontSize: 11,
    color: "#D1D5DB",
    marginTop: 8,
  },

  // ── Markdown body ──────────────────────────────────────────────────────
  markdownBody: {
    fontSize: 14,
    lineHeight: "1.65",
    color: "#1F2937",
  },

  // ── Prose elements ─────────────────────────────────────────────────────
  p: { margin: "0 0 10px" },
  h1: { fontSize: 18, fontWeight: 700, margin: "14px 0 8px", color: "#111827" },
  h2: { fontSize: 16, fontWeight: 700, margin: "14px 0 6px", color: "#111827" },
  h3: { fontSize: 14, fontWeight: 600, margin: "12px 0 4px", color: "#374151" },
  ul: { margin: "0 0 10px", paddingLeft: 20 },
  ol: { margin: "0 0 10px", paddingLeft: 20 },
  li: { marginBottom: 4 },
  blockquote: {
    borderLeft: "3px solid #E5E7EB",
    margin: "10px 0",
    paddingLeft: 14,
    color: "#6B7280",
    fontStyle: "italic",
  },
  hr: { border: "none", borderTop: "1px solid #F3F4F6", margin: "12px 0" },
  link: { color: "#6366F1", textDecoration: "underline" },

  // ── Code ───────────────────────────────────────────────────────────────
  codeBlock: {
    margin: "10px 0",
    borderRadius: 8,
    overflow: "hidden",
    border: "1px solid #E5E7EB",
  },
  codeHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "#F9FAFB",
    borderBottom: "1px solid #E5E7EB",
    padding: "6px 12px",
  },
  codeLang: {
    fontSize: 11,
    fontWeight: 600,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    fontFamily: FONT_MONO,
  },
  codeHighlighter: {
    margin: 0,
    padding: "14px 16px",
    fontSize: 13,
    background: "#FAFAFA",
    fontFamily: FONT_MONO,
  },
  inlineCode: {
    fontFamily: FONT_MONO,
    fontSize: "0.88em",
    background: "#F3F4F6",
    border: "1px solid #E5E7EB",
    borderRadius: 4,
    padding: "1px 5px",
    color: "#1F2937",
  },

  // ── Tables ─────────────────────────────────────────────────────────────
  tableWrapper: {
    overflowX: "auto",
    margin: "10px 0",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    background: "#F9FAFB",
    border: "1px solid #E5E7EB",
    padding: "8px 12px",
    textAlign: "left",
    fontWeight: 600,
    color: "#374151",
  },
  td: {
    border: "1px solid #E5E7EB",
    padding: "8px 12px",
    color: "#1F2937",
  },

  // ── Copy button ────────────────────────────────────────────────────────
  copyBtn: {
    background: "none",
    border: "1px solid #E5E7EB",
    borderRadius: 4,
    padding: "2px 8px",
    fontSize: 11,
    color: "#6B7280",
    cursor: "pointer",
    fontFamily: "inherit",
  },

  // ── Thinking indicator ─────────────────────────────────────────────────
  thinkingRow: {
    display: "flex",
    alignItems: "center",
    paddingLeft: 42,
  },
  dots: {
    display: "flex",
    gap: 5,
    alignItems: "center",
    padding: "10px 16px",
    background: "#fff",
    border: "1px solid #E5E7EB",
    borderRadius: "4px 18px 18px 18px",
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: "#9CA3AF",
    display: "inline-block",
    animation: "dotBounce 1.2s ease-in-out infinite",
  },

  // ── Error ──────────────────────────────────────────────────────────────
  errorBanner: {
    background: "#FEF2F2",
    border: "1px solid #FECACA",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13,
    color: "#DC2626",
  },

  // ── Input area ─────────────────────────────────────────────────────────
  inputArea: {
    display: "flex",
    gap: 8,
    padding: "12px 16px",
    borderTop: "1px solid #E5E7EB",
    background: "#fff",
  },
  input: {
    flex: 1,
    border: "1px solid #E5E7EB",
    borderRadius: 22,
    padding: "10px 18px",
    fontSize: 14,
    outline: "none",
    background: "#F9FAFB",
    transition: "border-color 0.15s",
    color: "#111827",
  },
  sendBtn: {
    width: 42,
    height: 42,
    borderRadius: "50%",
    border: "none",
    color: "#fff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    opacity: 1,
    transition: "opacity 0.15s",
  },
};
