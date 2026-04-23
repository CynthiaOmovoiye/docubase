/**
 * Route guard — redirects to /login if the user is not authenticated.
 * Preserves the intended destination so login can redirect back.
 *
 * Auth initialisation (sessionStorage restore + silent refresh) is handled
 * by AppInitializer in main.tsx, which blocks rendering until isInitialised=true.
 * The guard below is therefore a safety net — in normal operation isInitialised
 * is already true when RequireAuth is evaluated.
 */
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import PageLoader from "@/components/PageLoader";

export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const isInitialised = useAuthStore((s) => s.isInitialised);
  const location = useLocation();

  // AppInitializer should have resolved this before we render, but guard anyway.
  if (!isInitialised) return <PageLoader />;

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <>{children}</>;
}
