/**
 * Application router.
 *
 * Route structure:
 *
 * Marketing (public, no auth):
 * /                      — Landing page
 * /pricing               — Pricing
 * /about                 — About
 * /contact               — Contact
 * /security              — Security model
 * /privacy               — Privacy policy
 * /terms                 — Terms of service
 *
 * Auth:
 * /login                 — Sign in
 * /register              — Create account
 *
 * App (authenticated — wrapped in RequireAuth):
 * /dashboard             — Workspace overview
 * /workspaces            — Workspace list and management
 * /twins                 — Twin list and management
 * /workspace/:workspaceId/chat — Workspace-wide chat with automatic twin routing
 * /twin/:id              — Twin detail + chat
 * /twin/:id/sources      — Source management
 * /twin/:id/config       — Twin config (policy, branding, sharing)
 * /integrations          — Connected accounts (GitHub / GitLab / Google Drive OAuth)
 *
 * Public share surfaces (no auth required):
 * /t/:slug               — Public twin share page
 * /w/:slug               — Public workspace share page
 */

import { createBrowserRouter } from "react-router-dom";
import { lazy, Suspense } from "react";
import RequireAuth from "@/features/auth/RequireAuth";

// ─── Marketing ────────────────────────────────────────────────────────────────
const LandingPage         = lazy(() => import("@/features/marketing/pages/LandingPage"));
const PricingPage         = lazy(() => import("@/features/marketing/pages/PricingPage"));
const AboutPage           = lazy(() => import("@/features/marketing/pages/AboutPage"));
const ContactPage         = lazy(() => import("@/features/marketing/pages/ContactPage"));
const SecurityPage        = lazy(() => import("@/features/marketing/pages/SecurityPage"));
const PrivacyPage         = lazy(() => import("@/features/marketing/pages/PrivacyPage"));
const TermsPage           = lazy(() => import("@/features/marketing/pages/TermsPage"));

// ─── Auth ─────────────────────────────────────────────────────────────────────
const LoginPage           = lazy(() => import("@/features/auth/LoginPage"));
const RegisterPage        = lazy(() => import("@/features/auth/RegisterPage"));

// ─── App (authenticated) ──────────────────────────────────────────────────────
const DashboardPage         = lazy(() => import("@/features/workspaces/DashboardPage"));
const WorkspacesPage        = lazy(() => import("@/features/workspaces/WorkspacesPage"));
const WorkspaceChatPage     = lazy(() => import("@/features/workspaces/WorkspaceChatPage"));
const TwinsPage             = lazy(() => import("@/features/twins/TwinsPage"));
const TwinDetailPage        = lazy(() => import("@/features/twins/TwinDetailPage"));
const TwinConfigPage        = lazy(() => import("@/features/twins/TwinConfigPage"));
const SourcesPage           = lazy(() => import("@/features/sources/SourcesPage"));
const ConnectAccountsPage   = lazy(() => import("@/features/integrations/ConnectAccountsPage"));

// ─── Public share surfaces ────────────────────────────────────────────────────
const PublicTwinPage      = lazy(() => import("@/features/sharing/PublicTwinPage"));
const PublicWorkspacePage = lazy(() => import("@/features/sharing/PublicWorkspacePage"));

function protect(element: React.ReactNode) {
  return (
    <RequireAuth>
      <Suspense fallback={null}>{element}</Suspense>
    </RequireAuth>
  );
}

export const router = createBrowserRouter([
  // Marketing
  { path: "/",          element: <LandingPage /> },
  { path: "/pricing",   element: <PricingPage /> },
  { path: "/about",     element: <AboutPage /> },
  { path: "/contact",   element: <ContactPage /> },
  { path: "/security",  element: <SecurityPage /> },
  { path: "/privacy",   element: <PrivacyPage /> },
  { path: "/terms",     element: <TermsPage /> },

  // Auth (public)
  { path: "/login",     element: <LoginPage /> },
  { path: "/register",  element: <RegisterPage /> },

  // Authenticated app routes
  { path: "/dashboard",            element: protect(<DashboardPage />) },
  { path: "/workspaces",           element: protect(<WorkspacesPage />) },
  { path: "/twins",                element: protect(<TwinsPage />) },
  { path: "/workspace/:workspaceId/chat", element: protect(<WorkspaceChatPage />) },
  { path: "/twin/:twinId",         element: protect(<TwinDetailPage />) },
  { path: "/twin/:twinId/sources", element: protect(<SourcesPage />) },
  { path: "/twin/:twinId/config",  element: protect(<TwinConfigPage />) },
  { path: "/integrations",         element: protect(<ConnectAccountsPage />) },

  // Public share surfaces (no auth)
  { path: "/t/:slug",  element: <PublicTwinPage /> },
  { path: "/w/:slug",  element: <PublicWorkspacePage /> },
]);
