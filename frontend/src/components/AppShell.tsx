import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useIsMobile } from "@/hooks/useIsMobile";
import { useAuthStore } from "@/store/authStore";

interface AppShellProps {
  children: React.ReactNode;
}

interface NavEntry {
  label: string;
  to: string;
  icon: React.ReactNode;
  isActive: (pathname: string) => boolean;
}

const NAV_ITEMS: NavEntry[] = [
  {
    label: "Dashboard",
    to: "/dashboard",
    icon: <IconGrid />,
    isActive: (pathname) => pathname === "/dashboard",
  },
  {
    label: "Workspaces",
    to: "/workspaces",
    icon: <IconLayers />,
    isActive: (pathname) => pathname === "/workspaces" || pathname.startsWith("/workspace/"),
  },
  {
    label: "Twins",
    to: "/twins",
    icon: <IconTwin />,
    isActive: (pathname) => pathname === "/twins" || pathname.startsWith("/twin/"),
  },
  {
    label: "Integrations",
    to: "/integrations",
    icon: <IconPlugs />,
    isActive: (pathname) => pathname === "/integrations",
  },
];

export default function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const isMobile = useIsMobile();

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const initials = user?.display_name
    ? user.display_name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? "?";

  function handleLogout() {
    logout();
    navigate("/");
  }

  function closeDrawer() {
    setDrawerOpen(false);
  }

  return (
    <div style={s.root}>
      {/* ── Mobile hamburger button ──────────────────────────────────────── */}
      {isMobile && (
        <button
          style={s.hamburger}
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation"
        >
          <IconMenu />
        </button>
      )}

      {/* ── Mobile backdrop (dismiss drawer by tapping outside) ─────────── */}
      {isMobile && drawerOpen && (
        <div style={s.backdrop} onClick={closeDrawer} aria-hidden="true" />
      )}

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside
        style={{
          ...s.sidebar,
          ...(isMobile ? {
            position: "fixed",
            top: 0,
            left: 0,
            height: "100dvh",
            zIndex: 300,
            transform: drawerOpen ? "translateX(0)" : "translateX(-100%)",
            transition: "transform 0.24s cubic-bezier(0.4,0,0.2,1)",
            boxShadow: drawerOpen ? "4px 0 32px rgba(15,23,42,0.18)" : "none",
          } : {}),
        }}
      >
        {/* Mobile close button (inside drawer) */}
        {isMobile && (
          <button style={s.drawerClose} onClick={closeDrawer} aria-label="Close navigation">
            <IconX />
          </button>
        )}

        <Link to="/dashboard" style={s.logoRow} onClick={closeDrawer}>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="10" fill="url(#shell-brand)" />
            <circle cx="16" cy="16" r="6.5" fill="white" fillOpacity="0.96" />
            <circle cx="16" cy="16" r="3.25" fill="url(#shell-brand)" />
            <defs>
              <linearGradient id="shell-brand" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6366F1" />
                <stop offset="1" stopColor="#14B8A6" />
              </linearGradient>
            </defs>
          </svg>

          <div style={s.logoCopy}>
            <span style={s.logoText}>docbase</span>
            <span style={s.logoSub}>Owner console</span>
          </div>
        </Link>

        <div style={s.navArea}>
          <div style={s.navLabel}>Navigation</div>
          <nav style={s.nav}>
            {NAV_ITEMS.map((item) => {
              const active = item.isActive(location.pathname);
              return (
                <Link
                  key={item.label}
                  to={item.to}
                  onClick={closeDrawer}
                  style={{
                    ...s.navItem,
                    ...(active ? s.navItemActive : {}),
                  }}
                >
                  <span style={s.navIcon}>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div style={s.helperCard}>
            <div style={s.helperEyebrow}>Owner flow</div>
            <div style={s.helperTitle}>Start with workspaces</div>
            <p style={s.helperBody}>
              Create workspaces first, then add twins inside them. Workspace chat routes
              each question to the best twin automatically.
            </p>
          </div>
        </div>

        <div style={s.sidebarBottom}>
          <button style={s.userRow} onClick={() => setUserMenuOpen((v) => !v)}>
            <div style={s.avatar}>{initials}</div>
            <div style={s.userMeta}>
              <span style={s.userName}>{user?.display_name || user?.email?.split("@")[0]}</span>
              <span style={s.userEmail}>{user?.email}</span>
            </div>
            <span style={s.chevron}>⌄</span>
          </button>

          {userMenuOpen && (
            <div style={s.userMenu}>
              <button style={s.userMenuItem} onClick={handleLogout}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      <main style={s.main}>{children}</main>
    </div>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function IconGrid() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </svg>
  );
}

function IconLayers() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 2 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 17 9 5 9-5" />
    </svg>
  );
}

function IconTwin() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 7a4 4 0 1 1 8 0v10a4 4 0 0 1-8 0V7Z" />
      <path d="M8 11h8" />
      <path d="M12 17v4" />
    </svg>
  );
}

function IconPlugs() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22V12" />
      <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
      <rect x="7" y="2" width="10" height="8" rx="2" />
      <path d="M9 2v3" />
      <path d="M15 2v3" />
    </svg>
  );
}

function IconMenu() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function IconX() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    minHeight: "100vh",
    background:
      "radial-gradient(circle at top left, rgba(15,118,110,0.08), transparent 24%), var(--color-bg)",
  },
  // ── Mobile controls ──────────────────────────────────────────────────
  hamburger: {
    position: "fixed",
    top: 12,
    left: 12,
    zIndex: 400,
    width: 40,
    height: 40,
    borderRadius: 10,
    border: "1px solid var(--color-border)",
    background: "rgba(255,255,255,0.96)",
    backdropFilter: "blur(8px)",
    boxShadow: "0 1px 8px rgba(15,23,42,0.12)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    color: "var(--color-text-primary)",
  },
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.42)",
    zIndex: 299,
    backdropFilter: "blur(2px)",
  },
  drawerClose: {
    position: "absolute",
    top: 14,
    right: 14,
    width: 32,
    height: 32,
    borderRadius: 8,
    border: "1px solid var(--color-border)",
    background: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    color: "var(--color-text-secondary)",
  },
  // ── Sidebar ──────────────────────────────────────────────────────────
  sidebar: {
    width: 272,
    minWidth: 272,
    borderRight: "1px solid var(--color-border)",
    background: "rgba(255,255,255,0.94)",
    backdropFilter: "blur(18px)",
    display: "flex",
    flexDirection: "column",
    position: "sticky",
    top: 0,
    height: "100vh",
  },
  logoRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "22px 18px 18px",
    borderBottom: "1px solid var(--color-border)",
    textDecoration: "none",
  },
  logoCopy: {
    display: "flex",
    flexDirection: "column",
  },
  logoText: {
    fontFamily: "var(--font-display)",
    fontSize: 18,
    fontWeight: 700,
    color: "var(--color-text-primary)",
    letterSpacing: "-0.03em",
  },
  logoSub: {
    marginTop: 2,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--color-text-tertiary)",
  },
  navArea: {
    flex: 1,
    padding: "18px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    overflowY: "auto",
  },
  navLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-text-tertiary)",
    padding: "0 4px",
  },
  nav: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "12px 14px",
    borderRadius: 14,
    textDecoration: "none",
    color: "var(--color-text-secondary)",
    fontSize: 14,
    fontWeight: 600,
    transition: "background 0.15s ease, color 0.15s ease, border-color 0.15s ease",
    border: "1px solid transparent",
  },
  navItemActive: {
    background: "rgba(15,118,110,0.08)",
    color: "var(--color-teal-dim)",
    borderColor: "rgba(15,118,110,0.12)",
  },
  navIcon: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  helperCard: {
    marginTop: 10,
    padding: "16px 16px 18px",
    borderRadius: 18,
    background: "linear-gradient(180deg, rgba(15,118,110,0.08), rgba(15,23,42,0.04))",
    border: "1px solid rgba(15,118,110,0.12)",
  },
  helperEyebrow: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-teal-dim)",
  },
  helperTitle: {
    marginTop: 8,
    fontSize: 16,
    fontWeight: 700,
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
  },
  helperBody: {
    margin: "8px 0 0",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  sidebarBottom: {
    padding: "14px",
    borderTop: "1px solid var(--color-border)",
    position: "relative",
  },
  userRow: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 12px",
    borderRadius: 14,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    cursor: "pointer",
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 12,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, rgba(15,118,110,0.14), rgba(15,23,42,0.16))",
    color: "var(--color-text-primary)",
    fontWeight: 700,
    flexShrink: 0,
  },
  userMeta: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 2,
    flex: 1,
    textAlign: "left",
  },
  userName: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--color-text-primary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  userEmail: {
    fontSize: 12,
    color: "var(--color-text-tertiary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  chevron: {
    color: "var(--color-text-tertiary)",
    flexShrink: 0,
  },
  userMenu: {
    position: "absolute",
    left: 14,
    right: 14,
    bottom: 74,
    padding: 8,
    borderRadius: 14,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    boxShadow: "var(--shadow-md)",
  },
  userMenuItem: {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 10,
    border: "none",
    background: "transparent",
    color: "var(--color-text-primary)",
    fontSize: 14,
    fontWeight: 600,
    textAlign: "left",
    cursor: "pointer",
  },
  main: {
    flex: 1,
    minWidth: 0,
  },
};
