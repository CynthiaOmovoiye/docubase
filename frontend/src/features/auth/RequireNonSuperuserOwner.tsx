/**
 * Owner-only routes (workspaces, twins, integrations). Superusers are redirected to `/admin`.
 */
import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

export default function RequireNonSuperuserOwner({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (user?.is_superuser) {
    return <Navigate to="/admin/dashboard" replace />;
  }

  return <>{children}</>;
}
