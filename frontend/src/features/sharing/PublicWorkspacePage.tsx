/**
 * Public workspace share page.
 *
 * Accessible at /w/:slug — no auth required.
 * Renders a single workspace-wide chat surface. The backend routes each message
 * to the most relevant twin within the workspace.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ChatInterface } from "@/features/chat/components/ChatInterface";
import { api } from "@/lib/api";

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

export default function PublicWorkspacePage() {
  const { slug } = useParams<{ slug: string }>();
  const [info, setInfo] = useState<PublicSurfaceInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    api
      .get<PublicSurfaceInfo>(`/share/public/${slug}`)
      .then((res) => setInfo(res.data))
      .catch(() => setError("This workspace is not available."))
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
        <p style={s.errorText}>{error || "Workspace not found."}</p>
      </div>
    );
  }

  const workspaceName = info.display_name || info.workspace_name || "Workspace";
  const accentColor = info.accent_color || "#6366F1";

  return (
    <div style={{ ...s.page, "--accent": accentColor } as React.CSSProperties}>
      <header style={s.hero}>
        <div style={s.heroInner}>
          <p style={s.eyebrow}>Public workspace chat</p>
          <h1 style={s.title}>{workspaceName}</h1>
          <p style={s.subtitle}>
            Ask across the projects in this workspace. docbase routes each question to the
            most relevant twin and answers from approved project knowledge only.
          </p>
        </div>
      </header>

      <main style={s.main}>
        <div style={s.chatWrap}>
          <ChatInterface
            publicSlug={slug}
            twinName={workspaceName}
            accentColor={accentColor}
            placeholder="Ask anything across this workspace..."
          />
        </div>
      </main>

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
    background:
      "radial-gradient(circle at top left, rgba(99,102,241,0.12), transparent 30%), var(--color-bg)",
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
  errorText: {
    color: "var(--color-text-secondary)",
    fontSize: 15,
  },
  hero: {
    padding: "40px 24px 20px",
  },
  heroInner: {
    maxWidth: 980,
    margin: "0 auto",
  },
  eyebrow: {
    margin: 0,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--accent)",
  },
  title: {
    margin: "10px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 34,
    letterSpacing: "-0.03em",
    color: "var(--color-text-primary)",
  },
  subtitle: {
    margin: "12px 0 0",
    maxWidth: 720,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
    fontSize: 15,
  },
  main: {
    flex: 1,
    padding: "0 24px 32px",
  },
  chatWrap: {
    maxWidth: 980,
    margin: "0 auto",
    minHeight: 640,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 20,
    overflow: "hidden",
    boxShadow: "var(--shadow-sm)",
  },
  footer: {
    padding: "12px 24px 24px",
    textAlign: "center",
  },
  footerText: {
    margin: 0,
    color: "var(--color-text-secondary)",
    fontSize: 12,
  },
};
