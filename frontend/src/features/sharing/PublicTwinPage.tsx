/**
 * Public twin share page.
 *
 * Accessible at /t/:slug — no auth required.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { PublicChatShell } from "@/features/sharing/PublicChatShell";

interface PublicSurfaceInfo {
  surface_type: string;
  public_slug: string;
  doctwin_name: string | null;
  doctwin_description: string | null;
  workspace_name: string | null;
  display_name: string | null;
  accent_color: string | null;
  is_active: boolean;
}

export default function PublicTwinPage() {
  const { slug } = useParams<{ slug: string }>();
  const [info, setInfo] = useState<PublicSurfaceInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    api
      .get<PublicSurfaceInfo>(`/share/public/${slug}`)
      .then((res) => setInfo(res.data))
      .catch(() => setError("This twin is not available."))
      .finally(() => setIsLoading(false));
  }, [slug]);

  if (isLoading) {
    return (
      <div style={s.center}>
        <div style={s.spinner} />
      </div>
    );
  }

  if (error || !info || !slug) {
    return (
      <div style={s.center}>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 15 }}>
          {error || "This page is not available."}
        </p>
      </div>
    );
  }

  const displayName = info.display_name || info.doctwin_name || info.workspace_name || "Digital Twin";
  const accentColor = info.accent_color || "#6366F1";

  return (
    <div style={s.page}>
      <PublicChatShell
        publicSlug={slug}
        displayName={displayName}
        accentColor={accentColor}
        placeholder={`Ask me about ${displayName}…`}
        eyebrow="Public twin"
        subtitle={info.doctwin_description || null}
        emptyState={
          <div style={s.promptCard}>
            <div style={{ ...s.promptOrb, color: accentColor, borderColor: `${accentColor}44` }}>
              {displayName.charAt(0).toUpperCase()}
            </div>
            <h2 style={s.promptTitle}>Ask {displayName}</h2>
            <p style={s.promptBody}>
              Answers are grounded in the sources the owner approved for this twin. Use Visitor ID
              if you want to keep or resume this conversation later.
            </p>
          </div>
        }
      />

      <footer style={s.footer}>
        <p style={s.footerText}>Powered by docbase</p>
      </footer>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    background: "var(--color-bg)",
    color: "var(--color-text-primary)",
  },
  center: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  spinner: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    border: "3px solid var(--color-border)",
    borderTopColor: "var(--color-iris)",
    animation: "spin 0.7s linear infinite",
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
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 22,
    fontWeight: 700,
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
  footer: {
    padding: "10px 20px",
    borderTop: "1px solid var(--color-border)",
    textAlign: "center",
    flexShrink: 0,
    background: "var(--color-surface)",
  },
  footerText: {
    fontSize: 12,
    color: "var(--color-text-secondary)",
    margin: 0,
  },
};
