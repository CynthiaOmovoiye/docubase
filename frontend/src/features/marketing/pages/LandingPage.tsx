/**
 * Landing page — the main conversion surface for docbase.
 *
 * Two audiences:
 *   1. Owner of the work — wants to share outcomes without exposing private material
 *   2. Recruiter/client/visitor — landed from a shared twin link, curious about the product
 *
 * Structure:
 *   Hero → Social proof → Features → Use cases → How it works → CTA → Footer
 */

import { Link } from "react-router-dom";
import { useIsMobile } from "@/hooks/useIsMobile";
import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

export default function LandingPage() {
  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />

      <main>
        <Hero />
        <LogoBar />
        <Features />
        <UseCases />
        <HowItWorks />
        <SecuritySection />
        <FinalCTA />
      </main>

      <MarketingFooter />
    </div>
  );
}

/* ── Hero ────────────────────────────────────────────── */
function Hero() {
  return (
    <section style={{
      paddingTop: "calc(var(--nav-height) + var(--space-24))",
      paddingBottom: "var(--space-24)",
      paddingLeft: "var(--space-6)",
      paddingRight: "var(--space-6)",
      textAlign: "center",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Background orb */}
      <div style={{
        position: "absolute",
        top: "10%",
        left: "50%",
        transform: "translateX(-50%)",
        width: "600px",
        height: "400px",
        background: "var(--gradient-brand)",
        filter: "blur(120px)",
        opacity: 0.12,
        pointerEvents: "none",
        borderRadius: "var(--radius-full)",
      }} />

      <div style={{ position: "relative", maxWidth: "var(--max-width-prose)", margin: "0 auto" }}>
        {/* Badge */}
        <div style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--space-2)",
          padding: "var(--space-1) var(--space-3)",
          background: "var(--color-iris-muted)",
          borderRadius: "var(--radius-full)",
          marginBottom: "var(--space-6)",
          border: "1px solid rgba(99,102,241,0.2)",
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "var(--radius-full)", background: "var(--color-iris)", display: "inline-block" }} />
          <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-iris)", letterSpacing: "0.02em" }}>
            NOW IN EARLY ACCESS
          </span>
        </div>

        <h1 style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(36px, 6vw, 56px)",
          fontWeight: 700,
          lineHeight: 1.1,
          letterSpacing: "-0.03em",
          color: "var(--color-text-primary)",
          marginBottom: "var(--space-6)",
        }}>
          Your work,{" "}
          <span style={{ background: "var(--gradient-brand)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            in conversation.
          </span>
        </h1>

        <p style={{
          fontSize: "clamp(16px, 2vw, 20px)",
          lineHeight: 1.6,
          color: "var(--color-text-secondary)",
          marginBottom: "var(--space-10)",
          maxWidth: "540px",
          margin: "0 auto var(--space-10)",
        }}>
          docbase turns your documents, portfolios, and career profiles into intelligent AI twins — shareable links that answer questions about your work without exposing private drafts or sensitive details.
        </p>

        <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "center", flexWrap: "wrap" }}>
          <CTAButton href="/register" primary>
            Create your first twin →
          </CTAButton>
          <CTAButton href="#how-it-works">
            See how it works
          </CTAButton>
        </div>

        <p style={{ marginTop: "var(--space-5)", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
          Free to start. No credit card required.
        </p>
      </div>

      {/* Hero chat demo */}
      <div style={{
        maxWidth: "680px",
        margin: "var(--space-16) auto 0",
        background: "var(--color-surface)",
        borderRadius: "var(--radius-xl)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--shadow-lg)",
        overflow: "hidden",
        textAlign: "left",
      }}>
        <div style={{
          padding: "var(--space-4) var(--space-5)",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
        }}>
          <div style={{ display: "flex", gap: "6px" }}>
            {["#F43F5E","#F59E0B","#14B8A6"].map(c => (
              <div key={c} style={{ width: 10, height: 10, borderRadius: "var(--radius-full)", background: c }} />
            ))}
          </div>
          <span style={{ fontSize: "13px", color: "var(--color-text-secondary)", fontWeight: 500 }}>
            docbase.io/t/jane-brand-work
          </span>
        </div>

        <div style={{ padding: "var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <ChatBubble role="user" text="What was the main goal of this engagement?" />
          <ChatBubble role="assistant" text="The brief was to refresh the visual system and tighten messaging for a mid-size product launch. The twin is grounded in the strategy deck, creative guidelines, and weekly status notes you connected — so answers stay aligned with what you approved, not guesswork." />
          <ChatBubble role="user" text="Can I add more material later?" />
          <ChatBubble role="assistant" text="Yes. You can attach new PDFs or connect a cloud folder so the twin stays current as the work evolves." />
        </div>

        <div style={{
          padding: "var(--space-4) var(--space-5)",
          borderTop: "1px solid var(--color-border)",
          display: "flex",
          gap: "var(--space-3)",
        }}>
          <input
            readOnly
            value="Ask anything about this body of work..."
            style={{
              flex: 1,
              padding: "10px var(--space-4)",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--color-border)",
              fontSize: "14px",
              color: "var(--color-text-tertiary)",
              background: "var(--color-surface-raised)",
              cursor: "default",
              outline: "none",
            }}
          />
          <button style={{
            padding: "10px var(--space-4)",
            background: "var(--color-iris)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius-sm)",
            fontSize: "14px",
            fontWeight: 600,
            cursor: "pointer",
          }}>
            Send
          </button>
        </div>
      </div>
    </section>
  );
}

/* ── Logo bar ────────────────────────────────────────── */
function LogoBar() {
  const isMobile = useIsMobile();
  const kinds = ["PDFs & documents", "Cloud folders", "Briefs & decks", "Portfolios", "Resumes", "Case studies"];
  return (
    <section style={{
      padding: isMobile ? "var(--space-6) var(--space-5)" : "var(--space-8) var(--space-6)",
      textAlign: "center",
      borderTop: "1px solid var(--color-border)",
      borderBottom: "1px solid var(--color-border)",
    }}>
      <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)", marginBottom: "var(--space-4)", letterSpacing: "0.05em", fontWeight: 500 }}>
        START FROM CONTENT YOU ALREADY HAVE
      </p>
      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(6, auto)",
        gap: isMobile ? "var(--space-3) var(--space-4)" : "var(--space-8)",
        justifyContent: isMobile ? undefined : "center",
        alignItems: "center",
      }}>
        {kinds.map((k) => (
          <span key={k} style={{ fontSize: isMobile ? "13px" : "15px", fontWeight: 600, color: "var(--color-text-tertiary)", fontFamily: "var(--font-display)", textAlign: "center" }}>{k}</span>
        ))}
      </div>
    </section>
  );
}

/* ── Features ────────────────────────────────────────── */
function Features() {
  const isMobile = useIsMobile();
  const features = [
    {
      icon: "◎",
      title: "One twin per project",
      description: "Connect Drive files, a PDF, or a document to a twin. Each twin has its own identity, config, and shareable link.",
    },
    {
      icon: "⬡",
      title: "Safe by default",
      description: "Secrets and credentials are always blocked at ingestion. Verbatim excerpts from private files stay off unless you explicitly allow scoped sharing.",
    },
    {
      icon: "⇄",
      title: "Workspace-wide chat",
      description: "Ask across all your twins at once. docbase routes your question to the most relevant project automatically.",
    },
    {
      icon: "↗",
      title: "Share a link",
      description: "Every twin gets a public URL. Send it to a recruiter, client, or collaborator. No login required to chat.",
    },
    {
      icon: "⌗",
      title: "Embed anywhere",
      description: "Drop a widget onto your portfolio, documentation site, or personal site. One script tag.",
    },
    {
      icon: "◑",
      title: "Career twin",
      description: "Connect your resume, highlights, and case studies. Let docbase hold career conversations for you while you focus on work.",
    },
  ];

  return (
    <section id="features" style={{
      padding: isMobile ? "var(--space-12) var(--space-5)" : "var(--space-24) var(--space-6)",
      maxWidth: "var(--max-width-content)",
      margin: "0 auto",
    }}>
      <SectionLabel>Features</SectionLabel>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: isMobile ? "var(--space-8)" : "var(--space-12)", lineHeight: 1.15 }}>
        Everything you need to share your work intelligently.
      </h2>

      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fit, minmax(300px, 1fr))",
        gap: "var(--space-4)",
      }}>
        {features.map((f) => (
          <FeatureCard key={f.title} {...f} />
        ))}
      </div>
    </section>
  );
}

function FeatureCard({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div style={{
      padding: "var(--space-6)",
      background: "var(--color-surface)",
      borderRadius: "var(--radius-lg)",
      border: "1px solid var(--color-border)",
      transition: "box-shadow var(--duration-smooth) var(--ease-out), border-color var(--duration-smooth)",
      cursor: "default",
    }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)";
        (e.currentTarget as HTMLElement).style.borderColor = "rgba(99,102,241,0.3)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.boxShadow = "none";
        (e.currentTarget as HTMLElement).style.borderColor = "var(--color-border)";
      }}
    >
      <div style={{ fontSize: "20px", marginBottom: "var(--space-4)", color: "var(--color-iris)" }}>{icon}</div>
      <h3 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 600, marginBottom: "var(--space-2)", letterSpacing: "-0.01em" }}>{title}</h3>
      <p style={{ fontSize: "14px", lineHeight: 1.6, color: "var(--color-text-secondary)" }}>{description}</p>
    </div>
  );
}

/* ── Use cases ───────────────────────────────────────── */
function UseCases() {
  const isMobile = useIsMobile();
  const cases = [
    {
      id: "creators",
      label: "For creators & consultants",
      headline: "Stop explaining the same project twice.",
      body: "Connect your briefs, decks, and supporting notes to a twin. When a colleague, client, or interviewer asks how it works — send them a link. They can ask anything. The twin answers from your plans, deliverables, and summaries. Your private files stay private.",
      cta: "Create a project twin",
    },
    {
      id: "career",
      label: "Career twin",
      headline: "Let your work speak for itself.",
      body: "Connect your resume, portfolio, and best projects. Recruiters and hiring managers chat with your twin instead of skimming a PDF. They ask real questions — what you have shipped, where your strengths are, which outcomes you are proudest of — and get grounded answers.",
      cta: "Build your career twin",
    },
    {
      id: "teams",
      label: "For teams",
      headline: "Give clients visibility without access.",
      body: "Consultants and agencies can create a workspace twin for each client engagement. The client asks questions about the work in flight — decisions, status, delivery approach — without needing direct access to your internal folders or a meeting.",
      cta: "Create a team workspace",
    },
  ];

  return (
    <section style={{
      padding: isMobile ? "var(--space-12) var(--space-5)" : "var(--space-24) var(--space-6)",
      background: "var(--color-surface)",
      borderTop: "1px solid var(--color-border)",
      borderBottom: "1px solid var(--color-border)",
    }}>
      <div style={{ maxWidth: "var(--max-width-content)", margin: "0 auto" }}>
        <SectionLabel>Use cases</SectionLabel>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: isMobile ? "var(--space-8)" : "var(--space-12)", lineHeight: 1.15 }}>
          Who uses docbase.
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {cases.map(c => (
            <div key={c.id} id={c.id} style={{
              padding: isMobile ? "var(--space-6)" : "var(--space-8)",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--color-border)",
              background: "var(--color-bg)",
              display: "grid",
              gridTemplateColumns: isMobile ? "1fr" : "1fr 2fr",
              gap: isMobile ? "var(--space-4)" : "var(--space-8)",
              alignItems: "start",
            }}>
              <div>
                <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-iris)", letterSpacing: "0.05em" }}>{c.label.toUpperCase()}</span>
                <h3 style={{ fontFamily: "var(--font-display)", fontSize: isMobile ? "22px" : "clamp(20px, 3vw, 28px)", fontWeight: 700, letterSpacing: "-0.02em", marginTop: "var(--space-2)", lineHeight: 1.2 }}>{c.headline}</h3>
              </div>
              <div>
                <p style={{ fontSize: isMobile ? "15px" : "16px", lineHeight: 1.7, color: "var(--color-text-secondary)", marginBottom: "var(--space-5)" }}>{c.body}</p>
                <Link to="/register" style={{
                  display: "inline-flex",
                  padding: "10px var(--space-5)",
                  background: "var(--color-iris)",
                  color: "#fff",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "14px",
                  fontWeight: 600,
                  textDecoration: "none",
                  transition: "background var(--duration-base), box-shadow var(--duration-base)",
                }}
                  onMouseEnter={e => {
                    (e.target as HTMLElement).style.background = "var(--color-iris-dim)";
                    (e.target as HTMLElement).style.boxShadow = "var(--shadow-iris)";
                  }}
                  onMouseLeave={e => {
                    (e.target as HTMLElement).style.background = "var(--color-iris)";
                    (e.target as HTMLElement).style.boxShadow = "none";
                  }}
                >
                  {c.cta} →
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── How it works ────────────────────────────────────── */
function HowItWorks() {
  const isMobile = useIsMobile();
  const steps = [
    { n: "01", title: "Create a twin", body: "Give your twin a name and connect a source — a cloud folder, PDF resume, or written brief." },
    { n: "02", title: "docbase processes it safely", body: "We read structure, outlines, and summaries from what you connect. Sensitive credentials are never touched. Detailed excerpts stay off by default." },
    { n: "03", title: "Share a link", body: "Your twin gets a public URL. Anyone with the link can chat. No login needed. You stay in control." },
    { n: "04", title: "Revoke anytime", body: "Deactivate a share link instantly. The twin stays yours." },
  ];

  return (
    <section id="how-it-works" style={{ padding: isMobile ? "var(--space-12) var(--space-5)" : "var(--space-24) var(--space-6)", maxWidth: "var(--max-width-content)", margin: "0 auto" }}>
      <SectionLabel>How it works</SectionLabel>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: isMobile ? "var(--space-8)" : "var(--space-12)", lineHeight: 1.15 }}>
        Up and running in minutes.
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(auto-fit, minmax(220px, 1fr))", gap: "var(--space-4)" }}>
        {steps.map(s => (
          <div key={s.n} style={{ padding: isMobile ? "var(--space-4)" : "var(--space-6)", borderRadius: "var(--radius-lg)", border: "1px solid var(--color-border)", background: "var(--color-surface)" }}>
            <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-iris)", letterSpacing: "0.08em", display: "block", marginBottom: "var(--space-3)" }}>{s.n}</span>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: isMobile ? "15px" : "18px", fontWeight: 600, marginBottom: "var(--space-2)", letterSpacing: "-0.01em" }}>{s.title}</h3>
            <p style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--color-text-secondary)" }}>{s.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Security section ────────────────────────────────── */
function SecuritySection() {
  const isMobile = useIsMobile();
  return (
    <section style={{
      padding: isMobile ? "var(--space-12) var(--space-5)" : "var(--space-16) var(--space-6)",
      background: "var(--color-surface)",
      borderTop: "1px solid var(--color-border)",
      borderBottom: "1px solid var(--color-border)",
    }}>
      <div style={{ maxWidth: "var(--max-width-content)", margin: "0 auto", display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: isMobile ? "var(--space-8)" : "var(--space-16)", alignItems: "center" }}>
        <div>
          <SectionLabel>Security</SectionLabel>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(24px, 3vw, 32px)", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-5)", lineHeight: 1.2 }}>
            Your private material stays under your control.
          </h2>
          <p style={{ fontSize: "16px", lineHeight: 1.7, color: "var(--color-text-secondary)", marginBottom: "var(--space-6)" }}>
            docbase applies a layered content policy at ingestion, retrieval, and answer generation. Secrets are never indexed. Verbatim excerpts stay private unless you explicitly allow scoped sharing.
          </p>
          <Link to="/security" style={{ fontSize: "14px", fontWeight: 600, color: "var(--color-iris)", textDecoration: "none" }}>
            Read our security model →
          </Link>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {[
            { label: "Always blocked", desc: "Secrets, keys, and credentials — never read, never indexed", color: "#F43F5E" },
            { label: "Off by default", desc: "Detailed excerpts — you control whether scoped sections appear in answers", color: "#F59E0B" },
            { label: "Always available", desc: "Structure, outlines, summaries, and approved narrative context", color: "#14B8A6" },
          ].map(t => (
            <div key={t.label} style={{
              padding: "var(--space-4) var(--space-5)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-bg)",
              display: "flex",
              gap: "var(--space-4)",
              alignItems: "flex-start",
            }}>
              <div style={{ width: 8, height: 8, borderRadius: "var(--radius-full)", background: t.color, marginTop: 6, flexShrink: 0 }} />
              <div>
                <p style={{ fontSize: "14px", fontWeight: 600, marginBottom: "var(--space-1)" }}>{t.label}</p>
                <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.5 }}>{t.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Final CTA ───────────────────────────────────────── */
function FinalCTA() {
  const isMobile = useIsMobile();
  return (
    <section style={{
      padding: isMobile ? "var(--space-12) var(--space-5)" : "var(--space-24) var(--space-6)",
      textAlign: "center",
      maxWidth: "var(--max-width-prose)",
      margin: "0 auto",
    }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: "var(--space-5)", lineHeight: 1.15 }}>
        Your work deserves<br />a better introduction.
      </h2>
      <p style={{ fontSize: "18px", color: "var(--color-text-secondary)", lineHeight: 1.6, marginBottom: "var(--space-8)" }}>
        Create your first twin in minutes. Free to start.
      </p>
      <CTAButton href="/register" primary large>
        Get started free →
      </CTAButton>
    </section>
  );
}

/* ── Shared components ───────────────────────────────── */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{
      fontSize: "12px",
      fontWeight: 600,
      letterSpacing: "0.08em",
      color: "var(--color-iris)",
      textTransform: "uppercase",
      marginBottom: "var(--space-3)",
    }}>
      {children}
    </p>
  );
}

function CTAButton({ href, primary, large, children }: {
  href: string;
  primary?: boolean;
  large?: boolean;
  children: React.ReactNode;
}) {
  const pad = large ? "14px 32px" : "10px 20px";
  const fz = large ? "16px" : "14px";
  const style: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    padding: pad,
    borderRadius: "var(--radius-sm)",
    fontSize: fz,
    fontWeight: 600,
    fontFamily: "var(--font-body)",
    textDecoration: "none",
    transition: "background var(--duration-base), box-shadow var(--duration-base), color var(--duration-base)",
    background: primary ? "var(--color-iris)" : "var(--color-surface)",
    color: primary ? "#fff" : "var(--color-text-primary)",
    border: primary ? "none" : "1px solid var(--color-border)",
    boxShadow: primary ? "var(--shadow-sm)" : "none",
  };
  const onMouseEnter = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (primary) {
      e.currentTarget.style.background = "var(--color-iris-dim)";
      e.currentTarget.style.boxShadow = "var(--shadow-iris)";
    } else {
      e.currentTarget.style.background = "var(--color-surface-raised)";
    }
  };
  const onMouseLeave = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (primary) {
      e.currentTarget.style.background = "var(--color-iris)";
      e.currentTarget.style.boxShadow = "var(--shadow-sm)";
    } else {
      e.currentTarget.style.background = "var(--color-surface)";
    }
  };
  // Hash-only links: use a real <a> so the browser scrolls to #id. React Router <Link> does not.
  if (href.startsWith("#")) {
    return (
      <a href={href} style={style} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
        {children}
      </a>
    );
  }
  return (
    <Link to={href} style={style} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      {children}
    </Link>
  );
}

function ChatBubble({ role, text }: { role: "user" | "assistant"; text: string }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div style={{
        maxWidth: "80%",
        padding: "10px 14px",
        borderRadius: isUser ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
        background: isUser ? "var(--color-iris)" : "var(--color-surface-raised)",
        color: isUser ? "#fff" : "var(--color-text-primary)",
        fontSize: "13px",
        lineHeight: 1.6,
        border: isUser ? "none" : "1px solid var(--color-border)",
      }}>
        {text}
      </div>
    </div>
  );
}
