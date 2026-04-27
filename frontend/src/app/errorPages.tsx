import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";

/**
 * Centered, product-styled view for 404s and route-level errors.
 */
function ErrorPageView({ title, description }: { title: string; description: string }) {
  const btnBase: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "10px 20px",
    borderRadius: "var(--radius-sm)",
    fontSize: "14px",
    fontWeight: 600,
    fontFamily: "var(--font-body)",
    textDecoration: "none",
    transition: "background var(--duration-base), color var(--duration-base), border-color var(--duration-base)",
  };
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-6)",
        background: "var(--color-bg)",
        color: "var(--color-text-primary)",
        fontFamily: "var(--font-body)",
      }}
    >
      <main style={{ textAlign: "center", maxWidth: "480px" }}>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(24px, 4vw, 32px)",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "var(--color-text-primary)",
            marginBottom: "var(--space-3)",
            lineHeight: 1.2,
          }}
        >
          {title}
        </h1>
        <p
          style={{
            color: "var(--color-text-secondary)",
            marginBottom: "var(--space-8)",
            lineHeight: 1.6,
            fontSize: "16px",
          }}
        >
          {description}
        </p>
        <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", justifyContent: "center" }}>
          <Link
            to="/"
            style={{
              ...btnBase,
              background: "var(--color-iris)",
              color: "#fff",
              border: "none",
            }}
          >
            Back to home
          </Link>
          <Link
            to="/login"
            style={{
              ...btnBase,
              background: "var(--color-surface)",
              color: "var(--color-text-primary)",
              border: "1px solid var(--color-border)",
            }}
          >
            Sign in
          </Link>
        </div>
      </main>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <ErrorPageView
      title="Page not found"
      description="We could not find a page at this address. Check the URL or return to the home page."
    />
  );
}

/**
 * Renders for thrown route errors (loaders, actions, or missing matches that surface as errors)
 * and replaces React Router’s default error UI.
 */
export function RouteErrorPage() {
  const error = useRouteError();
  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      return (
        <ErrorPageView
          title="Page not found"
          description="We could not find a page at this address. It may have moved or the link is outdated."
        />
      );
    }
    return (
      <ErrorPageView
        title="Something went wrong"
        description={error.statusText || "The request could not be completed. Try again or go back to the home page."}
      />
    );
  }
  if (error instanceof Error) {
    return (
      <ErrorPageView
        title="Something went wrong"
        description={
          import.meta.env.DEV
            ? error.message
            : "An unexpected error occurred. Try again in a moment, or return to the home page."
        }
      />
    );
  }
  return (
    <ErrorPageView
      title="Something went wrong"
      description="An unexpected error occurred. Try again in a moment, or return to the home page."
    />
  );
}
