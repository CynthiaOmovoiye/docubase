import { useState } from "react";
import { MarketingNav, MarketingFooter } from "../components/MarketingNav";

type Status = "idle" | "sending" | "sent" | "error";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", subject: "general", message: "" });
  const [status, setStatus] = useState<Status>("idle");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus("sending");
    // TODO: wire to backend contact endpoint
    await new Promise(r => setTimeout(r, 800));
    setStatus("sent");
  };

  return (
    <div style={{ fontFamily: "var(--font-body)", background: "var(--color-bg)", color: "var(--color-text-primary)", minHeight: "100vh" }}>
      <MarketingNav />
      <main style={{ paddingTop: "calc(var(--nav-height) + var(--space-16))", paddingBottom: "var(--space-24)" }}>
        <div style={{ maxWidth: "560px", margin: "0 auto", padding: "0 var(--space-6)" }}>
          <p style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.08em", color: "var(--color-iris)", textTransform: "uppercase", marginBottom: "var(--space-3)" }}>Contact</p>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(28px, 4vw, 40px)", fontWeight: 700, letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: "var(--space-4)" }}>
            Get in touch.
          </h1>
          <p style={{ fontSize: "16px", color: "var(--color-text-secondary)", lineHeight: 1.6, marginBottom: "var(--space-10)" }}>
            Questions, feedback, partnership enquiries, or requests for student or open source pricing — we read every message.
          </p>

          {status === "sent" ? (
            <div style={{
              padding: "var(--space-8)",
              background: "var(--color-surface)",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--color-border)",
              textAlign: "center",
            }}>
              <div style={{ fontSize: "32px", marginBottom: "var(--space-4)" }}>✓</div>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 600, marginBottom: "var(--space-2)" }}>Message sent.</h2>
              <p style={{ fontSize: "14px", color: "var(--color-text-secondary)" }}>We will get back to you within one business day.</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <Field label="Name" required>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  required
                  placeholder="Your name"
                  style={inputStyle}
                />
              </Field>
              <Field label="Email" required>
                <input
                  type="email"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  required
                  placeholder="you@example.com"
                  style={inputStyle}
                />
              </Field>
              <Field label="What's this about?">
                <select
                  value={form.subject}
                  onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                  style={{ ...inputStyle, cursor: "pointer" }}
                >
                  <option value="general">General question</option>
                  <option value="feedback">Product feedback</option>
                  <option value="security">Security concern</option>
                  <option value="pricing">Pricing or billing</option>
                  <option value="student">Student / open source discount</option>
                  <option value="partnership">Partnership or integration</option>
                </select>
              </Field>
              <Field label="Message" required>
                <textarea
                  value={form.message}
                  onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                  required
                  placeholder="Tell us what you're thinking..."
                  rows={5}
                  style={{ ...inputStyle, resize: "vertical", minHeight: "120px" }}
                />
              </Field>

              <button
                type="submit"
                disabled={status === "sending"}
                style={{
                  padding: "12px var(--space-5)",
                  background: "var(--color-iris)",
                  color: "#fff",
                  border: "none",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "15px",
                  fontWeight: 600,
                  cursor: status === "sending" ? "not-allowed" : "pointer",
                  opacity: status === "sending" ? 0.7 : 1,
                  transition: "background var(--duration-base), box-shadow var(--duration-base), opacity var(--duration-base)",
                  fontFamily: "var(--font-body)",
                }}
                onMouseEnter={e => {
                  if (status !== "sending") {
                    (e.currentTarget as HTMLElement).style.background = "var(--color-iris-dim)";
                    (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-iris)";
                  }
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "var(--color-iris)";
                  (e.currentTarget as HTMLElement).style.boxShadow = "none";
                }}
              >
                {status === "sending" ? "Sending..." : "Send message"}
              </button>
            </form>
          )}

          <div style={{ marginTop: "var(--space-12)", paddingTop: "var(--space-8)", borderTop: "1px solid var(--color-border)" }}>
            <p style={{ fontSize: "13px", color: "var(--color-text-tertiary)" }}>
              For urgent security issues, email <a href="mailto:security@docbase.io" style={{ color: "var(--color-iris)" }}>security@docbase.io</a> directly.
            </p>
          </div>
        </div>
      </main>
      <MarketingFooter />
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px var(--space-4)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
  color: "var(--color-text-primary)",
  background: "var(--color-surface)",
  outline: "none",
  fontFamily: "var(--font-body)",
  boxSizing: "border-box",
  transition: "border-color var(--duration-base), box-shadow var(--duration-base)",
};

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <label style={{ fontSize: "14px", fontWeight: 500, color: "var(--color-text-primary)" }}>
        {label}{required && <span style={{ color: "var(--color-rose)", marginLeft: 2 }}>*</span>}
      </label>
      {children}
    </div>
  );
}
