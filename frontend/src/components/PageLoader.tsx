/**
 * Full-page loading spinner.
 *
 * Used during:
 *   - Suspense fallback while lazy bundles load
 *   - Auth initialisation (reading sessionStorage + silent token refresh)
 *   - Any other full-screen async gate
 */

export default function PageLoader() {
  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#F5F5F8",
    }}>
      <div style={{
        width: 32,
        height: 32,
        borderRadius: "50%",
        border: "3px solid #EEF2FF",
        borderTopColor: "#6366F1",
        animation: "spin 0.7s linear infinite",
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
