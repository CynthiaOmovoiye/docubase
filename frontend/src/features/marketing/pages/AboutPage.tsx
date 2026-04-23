/**
 * About page.
 *
 * Tells the product story. Builds trust with developers and with
 * recruiters/clients who land here after visiting a public twin.
 * Honest about what the product is and what it is not.
 */

import { Link } from "react-router-dom";
import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

export default function AboutPage() {
  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />

      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))" }}>
        {/* Header */}
        <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto", padding: "0 var(--space-6) var(--space-16)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>About</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(32px, 5vw, 48px)", fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: "var(--space-6)" }}>
            We built the introduction<br />your work deserves.
          </h1>
          <p style={{ fontSize: "18px", color: "var(--color-text-secondary)", lineHeight: 1.7 }}>
            Great work speaks for itself — but only if someone can hear it. docbase gives your repositories, portfolios, and career profiles a voice that's intelligent, safe, and always available.
          </p>
        </div>

        {/* Story */}
        <div style={{
          background: "var(--color-surface)",
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          padding: "var(--space-16) var(--space-6)",
        }}>
          <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto" }}>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: "28px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-6)" }}>The problem we kept running into</h2>

            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", fontSize: "16px", lineHeight: 1.8, color: "var(--color-text-secondary)" }}>
              <p>
                Developers spend enormous effort building systems — but when it comes time to explain that work to someone outside the team, the options are: share a private repo and hope they can read code, write a long document nobody reads, or spend an hour on a call answering the same questions.
              </p>
              <p>
                None of those are good answers. The repo is too much. The document is too static. The call is too expensive to repeat.
              </p>
              <p>
                The same problem shows up in hiring. A developer's best work is often locked inside a private codebase they can't share. A recruiter gets a PDF resume that says nothing about how they actually think. The interview is the first real conversation — but it shouldn't be.
              </p>
              <p>
                docbase is the layer between your work and the people who need to understand it. An AI twin that knows your project, speaks for it accurately, and never exposes what shouldn't be exposed.
              </p>
            </div>
          </div>
        </div>

        {/* Principles */}
        <div style={{ padding: "var(--space-16) var(--space-6)", maxWidth: "var(--max-width-content)", margin: "0 auto" }}>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: "28px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-8)", textAlign: "center" }}>
            What we believe
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "var(--space-4)" }}>
            {[
              {
                title: "Your code is yours",
                body: "We are not in the business of collecting or reselling your knowledge. docbase is a layer of safe presentation — not a data broker.",
              },
              {
                title: "Safe defaults matter",
                body: "Secrets should never surface. Proprietary logic should never leak. We enforce this at every layer, not just at the UI.",
              },
              {
                title: "Understanding beats access",
                body: "Most of the time, people don't need to read your code. They need to understand your system. Those are different things and they deserve different tools.",
              },
              {
                title: "Quality takes honesty",
                body: "docbase won't make up answers or speculate beyond what it knows. When it doesn't have enough context, it says so.",
              },
            ].map(p => (
              <div key={p.title} style={{
                padding: "var(--space-6)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--color-border)",
              }}>
                <h3 style={{ fontFamily: "var(--font-display)", fontSize: "17px", fontWeight: 600, marginBottom: "var(--space-3)", letterSpacing: "-0.01em" }}>{p.title}</h3>
                <p style={{ fontSize: "14px", lineHeight: 1.7, color: "var(--color-text-secondary)" }}>{p.body}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Product direction */}
        <div style={{
          background: "var(--color-surface)",
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          padding: "var(--space-16) var(--space-6)",
        }}>
          <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto" }}>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: "28px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-6)" }}>Where we are going</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", fontSize: "16px", lineHeight: 1.8, color: "var(--color-text-secondary)" }}>
              <p>
                docbase started as a tool for repositories. But the underlying idea — a safe, conversational AI twin for any knowledge source — applies far beyond code.
              </p>
              <p>
                We are building toward a broader platform where a twin can represent a project, a career, a team's delivery record, a product's knowledge base, or any structured body of work. The core principle stays constant: approved knowledge, safe exposure, grounded answers.
              </p>
              <p>
                We are a small team building carefully. We are more interested in getting the product right than in growing fast. If you have feedback, we actually want to hear it.
              </p>
            </div>
            <div style={{ marginTop: "var(--space-8)" }}>
              <Link to="/contact" style={{
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
                  (e.currentTarget as HTMLElement).style.background = "var(--color-iris-dim)";
                  (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-iris)";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "var(--color-iris)";
                  (e.currentTarget as HTMLElement).style.boxShadow = "none";
                }}
              >
                Get in touch →
              </Link>
            </div>
          </div>
        </div>
      </main>

      <MarketingFooter />
    </div>
  );
}
