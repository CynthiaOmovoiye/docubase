/**
 * Regular `/dashboard` — superusers land on `/admin` instead.
 */
import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

export default function SuperuserDashboardRedirect({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (user?.is_superuser) {
    return <Navigate to="/admin/dashboard" replace />;
  }

  return <>{children}</>;
}
