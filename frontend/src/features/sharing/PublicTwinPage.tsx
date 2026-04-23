/**
 * Public twin share page.
 *
 * Accessible at /t/:slug — no auth required.
 * Fetches twin display info and renders a chat interface.
 * This is what visitors see when someone shares a twin link.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatInterface } from "@/features/chat/components/ChatInterface";

// PublicSurfaceInfoResponse shape — mirrors backend schema
interface PublicSurfaceInfo {
  surface_type: string;
  public_slug: string;
  twin_name: string | null;
  twin_description: string | null;
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

  if (error || !info) {
    return (
      <div style={s.center}>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 15 }}>
          {error || "This page is not available."}
        </p>
      </div>
    );
  }

  const displayName = info.display_name || info.twin_name || info.workspace_name || "Digital Twin";
  const accentColor = info.accent_color || "#6366F1";

  return (
    <div style={{ ...s.page, "--accent": accentColor } as React.CSSProperties}>
      {/* Header */}
      <header style={s.header}>
        <h1 style={s.title}>{displayName}</h1>
        {info.twin_description && (
          <p style={s.subtitle}>{info.twin_description}</p>
        )}
      </header>

      {/* Chat */}
      <main style={s.main}>
        <ChatInterface
          publicSlug={slug}
          twinName={displayName}
          accentColor={accentColor}
          placeholder={`Ask me about ${displayName}...`}
        />
      </main>

      {/* Footer */}
      <footer style={s.footer}>
        <p style={s.footerText}>Powered by docubase</p>
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
  header: {
    borderBottom: "1px solid var(--color-border)",
    padding: "20px 28px",
  },
  title: {
    fontSize: 20,
    fontWeight: 600,
    margin: 0,
  },
  subtitle: {
    fontSize: 14,
    color: "var(--color-text-secondary)",
    margin: "4px 0 0",
  },
  main: {
    flex: 1,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  },
  footer: {
    padding: "12px 28px",
    borderTop: "1px solid var(--color-border)",
    textAlign: "center",
  },
  footerText: {
    fontSize: 12,
    color: "var(--color-text-secondary)",
    margin: 0,
  },
};
