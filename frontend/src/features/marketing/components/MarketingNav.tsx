import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useIsMobile } from "@/hooks/useIsMobile";

const NAV_LINKS = [
  { label: "Features", href: "/#features" },
  { label: "Pricing", href: "/pricing" },
  { label: "About", href: "/about" },
];

export function MarketingNav() {
  const isMobile = useIsMobile();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <header
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        height: "var(--nav-height)",
        display: "flex",
        alignItems: "center",
        padding: isMobile ? "0 var(--space-4)" : "0 var(--space-6)",
        background: scrolled
          ? "rgba(245,245,248,0.92)"
          : "transparent",
        backdropFilter: scrolled ? "blur(12px)" : "none",
        borderBottom: scrolled ? "1px solid var(--color-border)" : "1px solid transparent",
        transition: "background var(--duration-smooth) var(--ease-out), border-color var(--duration-smooth) var(--ease-out)",
      }}
    >
      <div
        style={{
          maxWidth: "var(--max-width-content)",
          width: "100%",
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        {/* Logo */}
        <Link to="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <DocbaseLogo />
          <span style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: "18px",
            color: "var(--color-text-primary)",
            letterSpacing: "-0.02em",
          }}>
            docbase
          </span>
        </Link>

        {/* Desktop nav — hidden on mobile */}
        {!isMobile && (
          <nav style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }} aria-label="Main navigation">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                to={link.href}
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "14px",
                  fontWeight: 500,
                  fontFamily: "var(--font-body)",
                  color: "var(--color-text-secondary)",
                  textDecoration: "none",
                  transition: "color var(--duration-base), background var(--duration-base)",
                }}
                onMouseEnter={e => {
                  (e.target as HTMLElement).style.color = "var(--color-text-primary)";
                  (e.target as HTMLElement).style.background = "var(--color-surface-raised)";
                }}
                onMouseLeave={e => {
                  (e.target as HTMLElement).style.color = "var(--color-text-secondary)";
                  (e.target as HTMLElement).style.background = "transparent";
                }}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        )}

        {/* CTA buttons — Sign in hidden on mobile */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          {!isMobile && (
            <Link
              to="/login"
              style={{
                padding: "var(--space-2) var(--space-4)",
                borderRadius: "var(--radius-sm)",
                fontSize: "14px",
                fontWeight: 500,
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                textDecoration: "none",
                transition: "color var(--duration-base)",
              }}
              onMouseEnter={e => (e.target as HTMLElement).style.color = "var(--color-text-primary)"}
              onMouseLeave={e => (e.target as HTMLElement).style.color = "var(--color-text-secondary)"}
            >
              Sign in
            </Link>
          )}
          <Link
            to="/register"
            style={{
              padding: isMobile ? "8px var(--space-3)" : "10px var(--space-4)",
              borderRadius: "var(--radius-sm)",
              fontSize: isMobile ? "13px" : "14px",
              fontWeight: 600,
              fontFamily: "var(--font-body)",
              background: "var(--color-iris)",
              color: "#FFFFFF",
              textDecoration: "none",
              boxShadow: "var(--shadow-sm)",
              transition: "background var(--duration-base), box-shadow var(--duration-base), transform var(--duration-fast)",
            }}
            onMouseEnter={e => {
              (e.target as HTMLElement).style.background = "var(--color-iris-dim)";
              (e.target as HTMLElement).style.boxShadow = "var(--shadow-iris)";
            }}
            onMouseLeave={e => {
              (e.target as HTMLElement).style.background = "var(--color-iris)";
              (e.target as HTMLElement).style.boxShadow = "var(--shadow-sm)";
            }}
          >
            {isMobile ? "Get started" : "Get started free"}
          </Link>
        </div>
      </div>
    </header>
  );
}

function DocbaseLogo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="28" height="28" rx="8" fill="url(#docbase-grad)" />
      <circle cx="14" cy="14" r="5" fill="white" fillOpacity="0.95" />
      <circle cx="14" cy="14" r="2.5" fill="url(#docbase-grad)" />
      <defs>
        <linearGradient id="docbase-grad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366F1" />
          <stop offset="1" stopColor="#14B8A6" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function MarketingFooter() {
  const isMobile = useIsMobile();
  return (
    <footer style={{
      borderTop: "1px solid var(--color-border)",
      padding: isMobile ? "var(--space-10) var(--space-5)" : "var(--space-12) var(--space-6)",
      marginTop: isMobile ? "var(--space-12)" : "var(--space-24)",
    }}>
      <div style={{
        maxWidth: "var(--max-width-content)",
        margin: "0 auto",
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 1fr 1fr",
        gap: isMobile ? "var(--space-8) var(--space-6)" : "var(--space-8)",
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-3)" }}>
            <DocbaseLogo />
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "16px", color: "var(--color-text-primary)", letterSpacing: "-0.02em" }}>docbase</span>
          </div>
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", lineHeight: 1.6, maxWidth: "200px" }}>
            Your work, in conversation.
          </p>
        </div>

        <FooterCol title="Product" links={[
          { label: "Features", href: "/#features" },
          { label: "Pricing", href: "/pricing" },
          { label: "Security", href: "/security" },
          { label: "Changelog", href: "/changelog" },
        ]} />
        <FooterCol title="Company" links={[
          { label: "About", href: "/about" },
          { label: "Contact", href: "/contact" },
          { label: "Privacy", href: "/privacy" },
          { label: "Terms", href: "/terms" },
        ]} />
        <FooterCol title="Use cases" links={[
          { label: "For creators & consultants", href: "/#creators" },
          { label: "Career twin", href: "/#career" },
          { label: "For teams", href: "/#teams" },
          { label: "Embed widget", href: "/#embed" },
        ]} />
      </div>

      <div style={{
        maxWidth: "var(--max-width-content)",
        margin: "var(--space-10) auto 0",
        paddingTop: "var(--space-6)",
        borderTop: "1px solid var(--color-border)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "var(--space-2)",
      }}>
        <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)" }}>
          © {new Date().getFullYear()} docbase. All rights reserved.
        </p>
        <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)" }}>
          Built with care.
        </p>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: { label: string; href: string }[] }) {
  return (
    <div>
      <p style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", marginBottom: "var(--space-3)", fontFamily: "var(--font-body)" }}>{title}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {links.map(link => (
          <Link key={link.href} to={link.href} style={{
            fontSize: "13px",
            color: "var(--color-text-secondary)",
            textDecoration: "none",
            transition: "color var(--duration-base)",
          }}
            onMouseEnter={e => (e.target as HTMLElement).style.color = "var(--color-text-primary)"}
            onMouseLeave={e => (e.target as HTMLElement).style.color = "var(--color-text-secondary)"}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
