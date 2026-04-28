/**
 * Application router.
 *
 * Marketing (public), Auth, Owner console, Platform admin (`/admin/*`), Public shares.
 */

import { createBrowserRouter, Navigate, Outlet } from "react-router-dom";
import type { ReactNode } from "react";
import { lazy, Suspense } from "react";
import RequireAuth from "@/features/auth/RequireAuth";
import RequireNonSuperuserOwner from "@/features/auth/RequireNonSuperuserOwner";
import RequireSuperuser from "@/features/auth/RequireSuperuser";
import SuperuserDashboardRedirect from "@/features/auth/SuperuserDashboardRedirect";
import { NotFoundPage, RouteErrorPage } from "@/app/errorPages";
import PageLoader from "@/components/PageLoader";

// ─── Marketing ────────────────────────────────────────────────────────────────
const LandingPage = lazy(() => import("@/features/marketing/pages/LandingPage"));
const PricingPage = lazy(() => import("@/features/marketing/pages/PricingPage"));
const AboutPage = lazy(() => import("@/features/marketing/pages/AboutPage"));
const ContactPage = lazy(() => import("@/features/marketing/pages/ContactPage"));
const SecurityPage = lazy(() => import("@/features/marketing/pages/SecurityPage"));
const PrivacyPage = lazy(() => import("@/features/marketing/pages/PrivacyPage"));
const TermsPage = lazy(() => import("@/features/marketing/pages/TermsPage"));

// ─── Auth ─────────────────────────────────────────────────────────────────────
const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const RegisterPage = lazy(() => import("@/features/auth/RegisterPage"));

// ─── App (authenticated) ──────────────────────────────────────────────────────
const DashboardPage = lazy(() => import("@/features/workspaces/DashboardPage"));
const WorkspacesPage = lazy(() => import("@/features/workspaces/WorkspacesPage"));
const WorkspaceChatPage = lazy(() => import("@/features/workspaces/WorkspaceChatPage"));
const TwinsPage = lazy(() => import("@/features/twins/TwinsPage"));
const TwinDetailPage = lazy(() => import("@/features/twins/TwinDetailPage"));
const TwinConfigPage = lazy(() => import("@/features/twins/TwinConfigPage"));
const SourcesPage = lazy(() => import("@/features/sources/SourcesPage"));
const ConnectAccountsPage = lazy(() => import("@/features/integrations/ConnectAccountsPage"));

// ─── Platform admin (nested under `/admin`) ────────────────────────────────────
const AdminShell = lazy(() => import("@/features/admin/AdminShell"));
const AdminDashboardPage = lazy(() => import("@/features/admin/AdminDashboardPage"));
const AdminUsersAdminsPage = lazy(() => import("@/features/admin/AdminUsersAdminsPage"));
const AdminUsersSignupsPage = lazy(() => import("@/features/admin/AdminUsersSignupsPage"));
const AdminMaintenanceIngestionPage = lazy(() => import("@/features/admin/AdminMaintenanceIngestionPage"));
const AdminMaintenanceRagPage = lazy(() => import("@/features/admin/AdminMaintenanceRagPage"));

// ─── Public share surfaces ────────────────────────────────────────────────────
const PublicTwinPage = lazy(() => import("@/features/sharing/PublicTwinPage"));
const PublicWorkspacePage = lazy(() => import("@/features/sharing/PublicWorkspacePage"));

function protectOwner(element: ReactNode) {
  return (
    <RequireAuth>
      <RequireNonSuperuserOwner>
        <Suspense fallback={null}>{element}</Suspense>
      </RequireNonSuperuserOwner>
    </RequireAuth>
  );
}

function protectDashboard(element: ReactNode) {
  return (
    <RequireAuth>
      <SuperuserDashboardRedirect>
        <Suspense fallback={null}>{element}</Suspense>
      </SuperuserDashboardRedirect>
    </RequireAuth>
  );
}

function protectAdminLayout() {
  return (
    <RequireAuth>
      <RequireSuperuser>
        <Suspense fallback={<PageLoader />}>
          <AdminShell />
        </Suspense>
      </RequireSuperuser>
    </RequireAuth>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Outlet />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "pricing", element: <PricingPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "contact", element: <ContactPage /> },
      { path: "security", element: <SecurityPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "terms", element: <TermsPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      { path: "dashboard", element: protectDashboard(<DashboardPage />) },
      { path: "workspaces", element: protectOwner(<WorkspacesPage />) },
      { path: "twins", element: protectOwner(<TwinsPage />) },
      { path: "workspace/:workspaceId/chat", element: protectOwner(<WorkspaceChatPage />) },
      { path: "twin/:twinId", element: protectOwner(<TwinDetailPage />) },
      { path: "twin/:twinId/sources", element: protectOwner(<SourcesPage />) },
      { path: "twin/:twinId/config", element: protectOwner(<TwinConfigPage />) },
      { path: "integrations", element: protectOwner(<ConnectAccountsPage />) },
      {
        path: "admin",
        element: protectAdminLayout(),
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          { path: "dashboard", element: <AdminDashboardPage /> },
          { path: "users/admins", element: <AdminUsersAdminsPage /> },
          { path: "users/signups", element: <AdminUsersSignupsPage /> },
          { path: "maintenance/ingestion", element: <AdminMaintenanceIngestionPage /> },
          { path: "maintenance/rag", element: <AdminMaintenanceRagPage /> },
        ],
      },
      { path: "t/:slug", element: <PublicTwinPage /> },
      { path: "w/:slug", element: <PublicWorkspacePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
