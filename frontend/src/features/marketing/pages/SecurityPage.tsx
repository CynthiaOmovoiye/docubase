/**
 * Security page.
 *
 * Critical for a product that asks users to connect their repos.
 * Explains the three-tier content policy, what we store, and what we don't.
 * Written for both technical and non-technical readers.
 */

import { Link } from "react-router-dom";
import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

export default function SecurityPage() {
  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />
      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))", paddingBottom: "var(--space-24)" }}>
        <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto", padding: "0 var(--space-6)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>Security</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: "var(--space-6)" }}>
            Security and privacy,<br />by design.
          </h1>
          <p style={{ fontSize: "18px", color: "var(--color-text-secondary)", lineHeight: 1.7, marginBottom: "var(--space-12)" }}>
            docubase is built around a core promise: your code and private information stay private. Here is exactly how that works.
          </p>

          {/* Three tier policy */}
          <Section title="Content policy — three tiers">
            <p>Every piece of content that passes through docubase is governed by a three-tier policy, enforced at ingestion, at retrieval, and as a final pass before any response is generated.</p>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", margin: "var(--space-6) 0" }}>
              {[
                {
                  color: "#F43F5E",
                  label: "Always blocked",
                  desc: ".env files, .env.local, .env.*, private keys (*.pem, *.key, *.p12), credential files, and any file matching secret patterns. These are never read, never ingested, never indexed. This cannot be overridden by any configuration.",
                },
                {
                  color: "#F59E0B",
                  label: "Off by default — owner opt-in",
                  desc: "Code snippets. If you enable snippet visibility in your twin config, relevant scoped sections of code may appear in answers. Full file dumps are never permitted even when this is enabled. Secrets are still blocked regardless.",
                },
                {
                  color: "#14B8A6",
                  label: "Always available",
                  desc: "Repository structure, documentation, README files, architecture summaries, feature descriptions, dependency signals, and tooling information. This is the knowledge layer docubase is designed to work from.",
                },
              ].map(t => (
                <div key={t.label} style={{
                  padding: "var(--space-5)",
                  background: "var(--color-surface)",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border)",
                  display: "flex",
                  gap: "var(--space-4)",
                }}>
                  <div style={{ width: 8, height: 8, borderRadius: "var(--radius-full)", background: t.color, marginTop: 7, flexShrink: 0 }} />
                  <div>
                    <p style={{ fontSize: "14px", fontWeight: 600, marginBottom: "var(--space-1)" }}>{t.label}</p>
                    <p style={{ fontSize: "14px", color: "var(--color-text-secondary)", lineHeight: 1.6 }}>{t.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="What we store">
            <p>docubase stores derived knowledge representations — structured summaries, architecture descriptions, and documentation chunks extracted from your source content. We do not store raw source files. We do not store the full text of your repository files in an API-accessible database.</p>
            <p>What is stored: chunk embeddings and their associated metadata (module name, file reference, chunk type). What is never stored: raw file contents, secrets, environment values, or full source code.</p>
          </Section>

          <Section title="Secret scanning">
            <p>During ingestion, every file passes through an automated secret scanner before any content is indexed. The scanner checks for common patterns: API keys, bearer tokens, private key headers, AWS access key IDs, GitHub and GitLab personal access tokens, and general password assignment patterns.</p>
            <p>If a file triggers the scanner, it is skipped entirely — not partially indexed, fully skipped. The ingestion log records the skip reason for the owner's visibility.</p>
          </Section>

          <Section title="Prompt injection protection">
            <p>Source content — repository files, markdown, PDFs, website content — is treated as untrusted input. It passes through a sanitization layer before reaching the language model. We apply scoping and context boundaries to prevent injected instructions in source files from influencing the model's behavior.</p>
            <p>This is an active area of work. We are conservative rather than permissive on this boundary.</p>
          </Section>

          <Section title="Public share surfaces">
            <p>Public twin pages and workspace pages are strictly read-only. Visitors can only chat — they cannot access twin configuration, source connection details, or any owner-only information. Public sessions are anonymous and rate-limited by IP address.</p>
            <p>Share links can be revoked instantly from the owner dashboard. When revoked, the link returns a 404 immediately. The slug is retired.</p>
          </Section>

          <Section title="Multi-tenant isolation">
            <p>All data is strictly scoped to the owning workspace. Retrieval queries, API responses, and background jobs enforce workspace and twin ownership at every layer. Cross-workspace data access is not architecturally possible — it is not a configuration option or a privilege level.</p>
          </Section>

          <Section title="Infrastructure">
            <p>docubase runs on cloud infrastructure with encrypted data at rest (AES-256) and in transit (TLS 1.3). Secrets and API credentials are managed via environment-level secret stores — never hardcoded in application code or stored in the database.</p>
          </Section>

          <Section title="Reporting a security issue">
            <p>If you discover a security vulnerability, please email <a href="mailto:security@docubase.io" style={{ color: "var(--color-iris)" }}>security@docubase.io</a> directly. Do not open a public issue. We will acknowledge receipt within 24 hours and work with you on a responsible disclosure timeline.</p>
          </Section>

          <div style={{ marginTop: "var(--space-10)", paddingTop: "var(--space-8)", borderTop: "1px solid var(--color-border)" }}>
            <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)" }}>
              Questions about our security model? <Link to="/contact" style={{ color: "var(--color-iris)" }}>Contact us</Link>.
            </p>
          </div>
        </div>
      </main>
      <MarketingFooter />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "var(--space-10)" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "var(--space-4)" }}>{title}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", fontSize: "15px", lineHeight: 1.8, color: "var(--color-text-secondary)" }}>
        {children}
      </div>
    </div>
  );
}
