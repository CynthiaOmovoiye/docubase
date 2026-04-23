import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

const LAST_UPDATED = "April 15, 2026";

export default function TermsPage() {
  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />
      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))", paddingBottom: "var(--space-24)" }}>
        <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto", padding: "0 var(--space-6)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>Legal</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: "var(--space-3)" }}>
            Terms of Service
          </h1>
          <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)", marginBottom: "var(--space-10)" }}>Last updated: {LAST_UPDATED}</p>

          <LegalSection title="1. Agreement">
            <p>By creating an account or using docubase, you agree to these Terms. If you are using docubase on behalf of an organisation, you represent that you have authority to bind that organisation to these Terms.</p>
          </LegalSection>

          <LegalSection title="2. The service">
            <p>docubase provides tools to create AI-powered conversational interfaces ("twins") grounded in knowledge sources you connect. We are not responsible for the accuracy of answers generated from your source content, and you are responsible for the knowledge sources you connect.</p>
          </LegalSection>

          <LegalSection title="3. Your content">
            <p>You own the content you connect to docubase. You grant us a limited licence to process that content solely for the purpose of operating your twins and providing the service to you. We do not claim any ownership over your repositories, documents, or profile data.</p>
            <p>You are responsible for ensuring you have the right to connect any source to docubase. Do not connect repositories or documents you do not own or are not authorised to share.</p>
          </LegalSection>

          <LegalSection title="4. Acceptable use">
            <p>You may not use docubase to: impersonate others, create twins intended to deceive or mislead visitors, distribute malware, violate applicable law, scrape or extract data from other users' twins, or attempt to circumvent the platform's safety controls.</p>
            <p>We may suspend or terminate accounts that violate these terms without prior notice.</p>
          </LegalSection>

          <LegalSection title="5. Public share surfaces">
            <p>When you create a public share link, you are making that twin's conversational interface accessible to anyone with the link. You are responsible for ensuring the content your twin can surface is appropriate for the audience you share it with. You can revoke any public link at any time.</p>
          </LegalSection>

          <LegalSection title="6. Limitations of liability">
            <p>The service is provided "as is." We make no warranties about uptime, accuracy of generated responses, or fitness for any particular purpose. To the maximum extent permitted by law, our total liability to you for any claims arising from use of the service is limited to the amount you paid us in the 12 months preceding the claim.</p>
          </LegalSection>

          <LegalSection title="7. Changes">
            <p>We may update these Terms. For material changes, we will give you at least 14 days' notice by email. Continued use after the effective date constitutes acceptance.</p>
          </LegalSection>

          <LegalSection title="8. Contact">
            <p>Legal questions: <a href="mailto:legal@docubase.io" style={{ color: "var(--color-iris)" }}>legal@docubase.io</a></p>
          </LegalSection>
        </div>
      </main>
      <MarketingFooter />
    </div>
  );
}

function LegalSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "var(--space-8)" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 600, marginBottom: "var(--space-4)", letterSpacing: "-0.01em" }}>{title}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", fontSize: "15px", lineHeight: 1.8, color: "var(--color-text-secondary)" }}>
        {children}
      </div>
    </div>
  );
}
