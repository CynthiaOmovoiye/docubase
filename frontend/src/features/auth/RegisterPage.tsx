import { useState, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

export default function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((s) => s.register);
  const isLoading = useAuthStore((s) => s.isLoading);

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const canSubmit = email && password.length >= 8;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await register(email, password, displayName || undefined);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message
        || "Could not create account. Please try again.";
      setError(msg);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <Link to="/" style={styles.logoLink}>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="url(#reg-g)" />
            <circle cx="16" cy="16" r="6" fill="white" fillOpacity="0.95" />
            <circle cx="16" cy="16" r="3" fill="url(#reg-g)" />
            <defs>
              <linearGradient id="reg-g" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6366F1" />
                <stop offset="1" stopColor="#14B8A6" />
              </linearGradient>
            </defs>
          </svg>
          <span style={styles.logoText}>docubase</span>
        </Link>

        <h1 style={styles.heading}>Create your account</h1>
        <p style={styles.subheading}>Free to start. No credit card required.</p>

        <form onSubmit={handleSubmit} style={styles.form} noValidate>
          {error && <div style={styles.errorBox}>{error}</div>}

          <div style={styles.field}>
            <label style={styles.label} htmlFor="display-name">Name <span style={styles.optional}>(optional)</span></label>
            <input
              id="display-name"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              style={styles.input}
              placeholder="Jane Smith"
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label} htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              placeholder="you@example.com"
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label} htmlFor="password">
              Password <span style={styles.optional}>(min 8 characters)</span>
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !canSubmit}
            style={{
              ...styles.button,
              opacity: isLoading || !canSubmit ? 0.6 : 1,
              cursor: isLoading || !canSubmit ? "not-allowed" : "pointer",
            }}
          >
            {isLoading ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p style={styles.terms}>
          By creating an account you agree to our{" "}
          <Link to="/terms" style={styles.link}>Terms</Link> and{" "}
          <Link to="/privacy" style={styles.link}>Privacy Policy</Link>.
        </p>

        <p style={styles.footerText}>
          Already have an account?{" "}
          <Link to="/login" style={styles.link}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "var(--color-bg-primary)",
    padding: "24px 16px",
  },
  card: {
    width: "100%",
    maxWidth: "400px",
    background: "var(--color-surface-1)",
    border: "1px solid var(--color-border)",
    borderRadius: "16px",
    padding: "40px 36px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  logoLink: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    textDecoration: "none",
    marginBottom: "16px",
    width: "fit-content",
  },
  logoText: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: "18px",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
  },
  heading: {
    fontFamily: "var(--font-display)",
    fontSize: "24px",
    fontWeight: 700,
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
    margin: 0,
  },
  subheading: {
    fontSize: "15px",
    color: "var(--color-text-secondary)",
    margin: "4px 0 24px",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "20px",
  },
  errorBox: {
    background: "rgba(239, 68, 68, 0.08)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    borderRadius: "8px",
    padding: "12px 14px",
    fontSize: "14px",
    color: "#EF4444",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  label: {
    fontSize: "14px",
    fontWeight: 500,
    color: "var(--color-text-primary)",
  },
  optional: {
    fontWeight: 400,
    color: "var(--color-text-tertiary)",
  },
  input: {
    width: "100%",
    padding: "10px 14px",
    fontSize: "15px",
    color: "var(--color-text-primary)",
    background: "var(--color-bg-primary)",
    border: "1px solid var(--color-border)",
    borderRadius: "8px",
    outline: "none",
    boxSizing: "border-box",
    transition: "border-color 0.15s",
  },
  button: {
    width: "100%",
    padding: "12px",
    fontSize: "15px",
    fontWeight: 600,
    color: "#fff",
    background: "var(--color-iris)",
    border: "none",
    borderRadius: "8px",
    marginTop: "4px",
    transition: "opacity 0.15s",
  },
  terms: {
    fontSize: "12px",
    color: "var(--color-text-tertiary)",
    textAlign: "center",
    marginTop: "12px",
    lineHeight: 1.6,
  },
  footerText: {
    fontSize: "14px",
    color: "var(--color-text-secondary)",
    textAlign: "center",
    marginTop: "8px",
  },
  link: {
    color: "var(--color-iris)",
    textDecoration: "none",
    fontWeight: 500,
  },
};
