import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

const LAST_UPDATED = "April 15, 2026";

export default function PrivacyPage() {
  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />
      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))", paddingBottom: "var(--space-24)" }}>
        <div style={{ maxWidth: "var(--max-width-prose)", margin: "0 auto", padding: "0 var(--space-6)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>Legal</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: "var(--space-3)" }}>
            Privacy Policy
          </h1>
          <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)", marginBottom: "var(--space-10)" }}>Last updated: {LAST_UPDATED}</p>

          <LegalSection title="1. What we collect">
            <p>When you create an account, we collect your email address and a hashed password. We do not store plaintext passwords. We do not collect payment card details — payments are handled by a third-party processor.</p>
            <p>When you connect a source (repository, PDF, or document), we process that content to build a knowledge index for your twin. We do not store raw source files. See our <a href="/security" style={{ color: "var(--color-iris)" }}>Security page</a> for detail on what is and is not retained.</p>
            <p>When visitors use a public twin or workspace page, sessions are anonymous. We log the session for rate-limiting and abuse prevention but do not track visitor identity.</p>
          </LegalSection>

          <LegalSection title="2. How we use it">
            <p>We use your email to send account-related communications: verification, password reset, billing notifications. We do not send marketing email without your explicit opt-in.</p>
            <p>Source content is processed solely to build your twin's knowledge index. It is not used to train models, sold to third parties, or made available to other users.</p>
            <p>Usage data (message counts, source sync events) is used to operate the service, enforce plan limits, and improve reliability.</p>
          </LegalSection>

          <LegalSection title="3. Data retention">
            <p>Account data is retained while your account is active. When you delete your account, your data is deleted within 30 days.</p>
            <p>When you delete a twin or detach a source, the associated knowledge index (chunks and embeddings) is deleted immediately.</p>
          </LegalSection>

          <LegalSection title="4. Third parties">
            <p>We use a small set of third-party services to operate: a cloud infrastructure provider for hosting and storage, a payment processor for billing, and an email delivery service for transactional emails. We do not sell data to or share data with advertising networks.</p>
            <p>When you connect a GitHub or GitLab source, authentication happens via OAuth. We store an OAuth token reference — not the token itself — in our database. The token is stored in an encrypted secret store.</p>
          </LegalSection>

          <LegalSection title="5. Cookies">
            <p>We use a single session cookie for authentication. We do not use third-party tracking cookies or advertising cookies.</p>
          </LegalSection>

          <LegalSection title="6. Your rights">
            <p>You may request a copy of the personal data we hold about you, request deletion of your account and data, or ask us to correct inaccurate information. To make a request, email <a href="mailto:privacy@docubase.io" style={{ color: "var(--color-iris)" }}>privacy@docubase.io</a>.</p>
          </LegalSection>

          <LegalSection title="7. Changes to this policy">
            <p>If we make material changes to this policy, we will notify registered users by email at least 14 days before the changes take effect. Continued use of the service after that date constitutes acceptance of the updated policy.</p>
          </LegalSection>

          <LegalSection title="8. Contact">
            <p>Questions about this policy: <a href="mailto:privacy@docubase.io" style={{ color: "var(--color-iris)" }}>privacy@docubase.io</a></p>
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
