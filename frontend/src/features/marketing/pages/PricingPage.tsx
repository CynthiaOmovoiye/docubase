/**
 * Pricing page.
 *
 * Tiers are intentionally flexible — exact limits TBD.
 * Structure is solid so numbers can be updated without rework.
 * Uses a "Free + Pro + Team" model as the starting assumption.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

type Billing = "monthly" | "annual";

interface Tier {
  name: string;
  price: { monthly: string; annual: string };
  annualNote?: string;
  description: string;
  cta: string;
  ctaHref: string;
  highlighted?: boolean;
  features: string[];
}

const TIERS: Tier[] = [
  {
    name: "Free",
    price: { monthly: "$0", annual: "$0" },
    description: "For developers exploring the platform and sharing personal projects.",
    cta: "Start for free",
    ctaHref: "/register",
    features: [
      "1 workspace",
      "2 twins",
      "3 sources per twin",
      "GitHub & PDF connectors",
      "Public share links",
      "1,000 chat messages / month",
      "Community support",
    ],
  },
  {
    name: "Pro",
    price: { monthly: "$19", annual: "$15" },
    annualNote: "per month, billed annually",
    description: "For professionals building career twins and sharing multiple projects.",
    cta: "Start Pro trial",
    ctaHref: "/register?plan=pro",
    highlighted: true,
    features: [
      "1 workspace",
      "Unlimited twins",
      "Unlimited sources per twin",
      "All connectors (GitHub, GitLab, PDF, URL, Markdown)",
      "Custom twin branding & accent color",
      "Embed widget",
      "10,000 chat messages / month",
      "Code snippet visibility control",
      "Priority support",
    ],
  },
  {
    name: "Team",
    price: { monthly: "$49", annual: "$39" },
    annualNote: "per month, billed annually",
    description: "For teams giving clients and stakeholders visibility into their work.",
    cta: "Start Team trial",
    ctaHref: "/register?plan=team",
    features: [
      "Unlimited workspaces",
      "Unlimited twins",
      "Unlimited sources",
      "All connectors",
      "Workspace-wide public pages",
      "Multiple workspace members",
      "Custom domain for public pages",
      "50,000 chat messages / month",
      "Admin dashboard & usage logs",
      "Dedicated support",
    ],
  },
];

const FAQ = [
  {
    q: "What counts as a 'source'?",
    a: "A source is any knowledge input connected to a twin — a GitHub repo, a PDF file, a markdown document, a URL, or a manual note. Each connection is one source.",
  },
  {
    q: "Is my code actually sent to your servers?",
    a: "docubase reads your repository structure, documentation, and architecture signals to build a knowledge index. Raw code is processed in our ingestion pipeline but never stored in an API-accessible format. Secrets and .env files are always blocked at ingestion — they are never read.",
  },
  {
    q: "Can I enable code snippet visibility?",
    a: "Yes, on Pro and Team plans you can enable scoped code snippet visibility per twin. This allows relevant sections of code to appear in answers — but never full file dumps, and secrets are always blocked regardless.",
  },
  {
    q: "What happens when I hit the message limit?",
    a: "Chat on your public share pages will show a limit message and invite visitors to try again later. Your own dashboard access is not affected. You can upgrade at any time.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. Cancel anytime from your account settings. You keep access until the end of your billing period. No questions asked.",
  },
  {
    q: "Do you offer a discount for students or open source projects?",
    a: "Yes. Reach out via the contact page and we will set you up with a discounted or complimentary plan.",
  },
];

export default function PricingPage() {
  const [billing, setBilling] = useState<Billing>("annual");

  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />

      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))" }}>
        {/* Header */}
        <div style={{ textAlign: "center", padding: "0 var(--space-6) var(--space-12)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>Pricing</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(32px, 5vw, 48px)", fontWeight: 700, letterSpacing: "-0.03em", marginBottom: "var(--space-4)", lineHeight: 1.1 }}>
            Simple, honest pricing.
          </h1>
          <p style={{ fontSize: "18px", color: "var(--color-text-secondary)", maxWidth: "480px", margin: "0 auto var(--space-8)", lineHeight: 1.6 }}>
            Start free. Upgrade when you need more twins, sources, or team features.
          </p>

          {/* Billing toggle */}
          <div style={{
            display: "inline-flex",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-full)",
            padding: "var(--space-1)",
            gap: "var(--space-1)",
          }}>
            {(["monthly", "annual"] as Billing[]).map(b => (
              <button
                key={b}
                onClick={() => setBilling(b)}
                style={{
                  padding: "var(--space-2) var(--space-4)",
                  borderRadius: "var(--radius-full)",
                  border: "none",
                  fontSize: "14px",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "background var(--duration-base), color var(--duration-base)",
                  background: billing === b ? "var(--color-iris)" : "transparent",
                  color: billing === b ? "#fff" : "var(--color-text-secondary)",
                }}
              >
                {b === "monthly" ? "Monthly" : "Annual"}
                {b === "annual" && (
                  <span style={{
                    marginLeft: "var(--space-2)",
                    fontSize: "11px",
                    fontWeight: 700,
                    background: billing === "annual" ? "rgba(255,255,255,0.2)" : "var(--color-iris-muted)",
                    color: billing === "annual" ? "#fff" : "var(--color-iris)",
                    padding: "2px 6px",
                    borderRadius: "var(--radius-full)",
                  }}>
                    Save 20%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Tier cards */}
        <div style={{
          maxWidth: "var(--max-width-content)",
          margin: "0 auto",
          padding: "0 var(--space-6) var(--space-24)",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "var(--space-4)",
          alignItems: "start",
        }}>
          {TIERS.map(tier => (
            <TierCard key={tier.name} tier={tier} billing={billing} />
          ))}
        </div>

        {/* Feature comparison note */}
        <div style={{
          textAlign: "center",
          padding: "0 var(--space-6) var(--space-16)",
          color: "var(--color-text-secondary)",
          fontSize: "14px",
        }}>
          All plans include a <strong style={{ color: "var(--color-text-primary)" }}>14-day free trial</strong> of Pro features. No credit card required to start.
        </div>

        {/* FAQ */}
        <div style={{
          maxWidth: "680px",
          margin: "0 auto",
          padding: "0 var(--space-6) var(--space-24)",
        }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "28px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-8)", textAlign: "center" }}>
            Frequently asked questions
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            {FAQ.map(item => (
              <FAQItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </div>
      </main>

      <MarketingFooter />
    </div>
  );
}

function TierCard({ tier, billing }: { tier: Tier; billing: Billing }) {
  const price = tier.price[billing];
  const isFree = price === "$0";

  return (
    <div style={{
      padding: "var(--space-6)",
      background: tier.highlighted ? "var(--color-iris)" : "var(--color-surface)",
      borderRadius: "var(--radius-lg)",
      border: tier.highlighted ? "none" : "1px solid var(--color-border)",
      boxShadow: tier.highlighted ? "var(--shadow-iris)" : "var(--shadow-sm)",
      color: tier.highlighted ? "#fff" : "var(--color-text-primary)",
      position: "relative",
    }}>
      {tier.highlighted && (
        <div style={{
          position: "absolute",
          top: "-12px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--color-teal)",
          color: "#fff",
          fontSize: "11px",
          fontWeight: 700,
          padding: "4px 12px",
          borderRadius: "var(--radius-full)",
          letterSpacing: "0.05em",
          whiteSpace: "nowrap",
        }}>
          MOST POPULAR
        </div>
      )}

      <p style={{ fontSize: "14px", fontWeight: 600, marginBottom: "var(--space-4)", opacity: tier.highlighted ? 0.85 : 1 }}>{tier.name}</p>

      <div style={{ marginBottom: "var(--space-2)" }}>
        <span style={{ fontFamily: "var(--font-display)", fontSize: "40px", fontWeight: 700, letterSpacing: "-0.03em" }}>{price}</span>
        {!isFree && <span style={{ fontSize: "14px", opacity: 0.7, marginLeft: "var(--space-1)" }}>/mo</span>}
      </div>

      {tier.annualNote && billing === "annual" && (
        <p style={{ fontSize: "12px", opacity: 0.65, marginBottom: "var(--space-4)" }}>{tier.annualNote}</p>
      )}

      <p style={{ fontSize: "14px", lineHeight: 1.6, opacity: tier.highlighted ? 0.85 : undefined, color: tier.highlighted ? undefined : "var(--color-text-secondary)", marginBottom: "var(--space-6)" }}>
        {tier.description}
      </p>

      <Link
        to={tier.ctaHref}
        style={{
          display: "block",
          textAlign: "center",
          padding: "10px var(--space-4)",
          borderRadius: "var(--radius-sm)",
          fontSize: "14px",
          fontWeight: 600,
          textDecoration: "none",
          marginBottom: "var(--space-6)",
          background: tier.highlighted ? "#fff" : "var(--color-iris)",
          color: tier.highlighted ? "var(--color-iris)" : "#fff",
          transition: "opacity var(--duration-base)",
        }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.opacity = "0.9"}
        onMouseLeave={e => (e.currentTarget as HTMLElement).style.opacity = "1"}
      >
        {tier.cta}
      </Link>

      <div style={{ borderTop: `1px solid ${tier.highlighted ? "rgba(255,255,255,0.2)" : "var(--color-border)"}`, paddingTop: "var(--space-5)" }}>
        <p style={{ fontSize: "12px", fontWeight: 600, opacity: 0.65, marginBottom: "var(--space-3)", letterSpacing: "0.05em" }}>INCLUDES</p>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {tier.features.map(f => (
            <li key={f} style={{ display: "flex", gap: "var(--space-2)", alignItems: "flex-start", fontSize: "14px", opacity: tier.highlighted ? 0.9 : undefined, color: tier.highlighted ? undefined : "var(--color-text-secondary)" }}>
              <span style={{ color: tier.highlighted ? "rgba(255,255,255,0.7)" : "var(--color-teal)", flexShrink: 0, marginTop: "2px" }}>✓</span>
              {f}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function FAQItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      borderRadius: "var(--radius-md)",
      border: "1px solid var(--color-border)",
      background: "var(--color-surface)",
      overflow: "hidden",
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "var(--space-5)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "15px",
          fontWeight: 500,
          color: "var(--color-text-primary)",
          fontFamily: "var(--font-body)",
          gap: "var(--space-4)",
        }}
        aria-expanded={open}
      >
        {q}
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "18px", flexShrink: 0, transition: "transform var(--duration-base)", transform: open ? "rotate(45deg)" : "rotate(0)" }}>+</span>
      </button>
      {open && (
        <div style={{ padding: "0 var(--space-5) var(--space-5)", fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.7 }}>
          {a}
        </div>
      )}
    </div>
  );
}
