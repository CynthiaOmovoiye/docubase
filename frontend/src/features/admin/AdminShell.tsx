import { Suspense, useState } from "react";
import type { CSSProperties } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useIsMobile } from "@/hooks/useIsMobile";
import { useAuthStore } from "@/store/authStore";
import PageLoader from "@/components/PageLoader";

export default function AdminShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const isMobile = useIsMobile();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

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

  const sidebarContent = (
    <>
      <Link to="/admin/dashboard" style={shell.logoRow} onClick={closeDrawer}>
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <rect width="32" height="32" rx="10" fill="url(#adm-brand)" />
          <circle cx="16" cy="16" r="6.5" fill="white" fillOpacity="0.96" />
          <circle cx="16" cy="16" r="3.25" fill="url(#adm-brand)" />
          <defs>
            <linearGradient id="adm-brand" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
              <stop stopColor="#6366F1" />
              <stop offset="1" stopColor="#14B8A6" />
            </linearGradient>
          </defs>
        </svg>
        <div style={shell.logoCopy}>
          <span style={shell.logoText}>docbase</span>
          <span style={shell.logoSub}>Platform admin</span>
        </div>
      </Link>

      <div style={shell.navArea}>
        <div style={shell.navLabel}>Navigation</div>

        <NavLink
          to="/admin/dashboard"
          end
          onClick={closeDrawer}
          style={({ isActive }) => ({
            ...shell.navItem,
            ...(isActive ? shell.navItemActive : {}),
          })}
        >
          Dashboard
        </NavLink>

        <div style={shell.groupLabel}>Users</div>
        <NavLink
          to="/admin/users/admins"
          onClick={closeDrawer}
          style={({ isActive }) => ({
            ...shell.navSubItem,
            ...(isActive ? shell.navItemActive : {}),
          })}
        >
          Admin users
        </NavLink>
        <NavLink
          to="/admin/users/signups"
          onClick={closeDrawer}
          style={({ isActive }) => ({
            ...shell.navSubItem,
            ...(isActive ? shell.navItemActive : {}),
          })}
        >
          Signups
        </NavLink>

        <div style={{ ...shell.groupLabel, marginTop: 14 }}>Maintenance</div>
        <NavLink
          to="/admin/maintenance/ingestion"
          onClick={closeDrawer}
          style={({ isActive }) => ({
            ...shell.navSubItem,
            ...(isActive ? shell.navItemActive : {}),
          })}
        >
          Ingestion jobs
        </NavLink>
        <NavLink
          to="/admin/maintenance/rag"
          onClick={closeDrawer}
          style={({ isActive }) => ({
            ...shell.navSubItem,
            ...(isActive ? shell.navItemActive : {}),
          })}
        >
          RAG &amp; memory
        </NavLink>
      </div>

      <div style={shell.sidebarBottom}>
        <button type="button" style={shell.userRow} onClick={() => setUserMenuOpen((v) => !v)}>
          <div style={shell.avatar}>{initials}</div>
          <div style={shell.userMeta}>
            <span style={shell.userName}>{user?.display_name || user?.email?.split("@")[0]}</span>
            <span style={shell.userEmail}>{user?.email}</span>
          </div>
          <span style={shell.chevron}>⌄</span>
        </button>
        {userMenuOpen && (
          <div style={shell.userMenu}>
            <button type="button" style={shell.userMenuItem} onClick={handleLogout}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </>
  );

  return (
    <div style={shell.root}>
      {isMobile && (
        <button type="button" style={shell.hamburger} onClick={() => setDrawerOpen(true)} aria-label="Open navigation">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      )}
      {isMobile && drawerOpen && (
        <div style={shell.backdrop} onClick={closeDrawer} aria-hidden="true" />
      )}
      <aside
        style={{
          ...shell.sidebar,
          ...(isMobile
            ? {
                position: "fixed",
                top: 0,
                left: 0,
                height: "100dvh",
                zIndex: 300,
                transform: drawerOpen ? "translateX(0)" : "translateX(-100%)",
                transition: "transform 0.24s cubic-bezier(0.4,0,0.2,1)",
                boxShadow: drawerOpen ? "4px 0 32px rgba(15,23,42,0.18)" : "none",
              }
            : {}),
        }}
      >
        {isMobile && (
          <button type="button" style={shell.drawerClose} onClick={closeDrawer} aria-label="Close navigation">
            ✕
          </button>
        )}
        {sidebarContent}
      </aside>
      <main style={{ ...shell.main, paddingTop: isMobile ? 56 : 0 }}>
        <Suspense fallback={<PageLoader />}>
          <Outlet key={location.pathname} />
        </Suspense>
      </main>
    </div>
  );
}

const shell: Record<string, CSSProperties> = {
  root: {
    display: "flex",
    minHeight: "100vh",
    background:
      "radial-gradient(circle at top left, rgba(15,118,110,0.08), transparent 24%), var(--color-bg)",
  },
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
    cursor: "pointer",
    color: "var(--color-text-secondary)",
  },
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
  logoCopy: { display: "flex", flexDirection: "column" },
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
    gap: 4,
    overflowY: "auto",
  },
  navLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-text-tertiary)",
    padding: "0 4px",
    marginBottom: 6,
  },
  groupLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-text-tertiary)",
    padding: "12px 4px 6px",
  },
  navItem: {
    display: "block",
    padding: "12px 14px",
    borderRadius: 14,
    textDecoration: "none",
    color: "var(--color-text-secondary)",
    fontSize: 14,
    fontWeight: 600,
    // border: "1px solid transparent",
  },
  navSubItem: {
    display: "block",
    padding: "10px 14px 10px 22px",
    marginLeft: 4,
    borderRadius: 12,
    textDecoration: "none",
    color: "var(--color-text-secondary)",
    fontSize: 13,
    fontWeight: 600,
    // border: "1px solid transparent",
  },
  navItemActive: {
    background: "rgba(15,118,110,0.08)",
    color: "var(--color-teal-dim)",
    borderColor: "rgba(15,118,110,0.12)",
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
  chevron: { color: "var(--color-text-tertiary)", flexShrink: 0 },
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
    overflow: "auto",
  },
};
