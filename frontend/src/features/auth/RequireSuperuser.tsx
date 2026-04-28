/**
 * Route guard — only users with `is_superuser` may access operator pages.
 */
import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import PageLoader from "@/components/PageLoader";

export default function RequireSuperuser({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const isInitialised = useAuthStore((s) => s.isInitialised);

  if (!isInitialised) return <PageLoader />;
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (!user.is_superuser) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
