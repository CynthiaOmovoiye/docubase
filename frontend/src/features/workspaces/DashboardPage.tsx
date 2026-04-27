import { Link } from "react-router-dom";

import AppShell from "@/components/AppShell";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useWorkspaceShareSurfacesForWorkspaces } from "@/hooks/useSharing";
import { useTwinsForWorkspaces } from "@/hooks/useTwins";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { useAuthStore } from "@/store/authStore";
import type { Twin } from "@/types";

export default function DashboardPage() {
  const isMobile = useIsMobile();
  const user = useAuthStore((s) => s.user);
  const { data: workspaces = [], isLoading: workspacesLoading } = useWorkspaces();
  const workspaceTwinGroups = useTwinsForWorkspaces(workspaces);
  const workspaceShareGroups = useWorkspaceShareSurfacesForWorkspaces(workspaces);

  const twins = workspaceTwinGroups.flatMap((group) => group.twins);
  const publicTwins = twins.filter((twin) => twin.config?.is_public);
  const publicWorkspacePages = workspaceShareGroups
    .flatMap((group) => group.surfaces)
    .filter((surface) => surface.surface_type === "workspace_page");

  const isLoading =
    workspacesLoading
    || workspaceTwinGroups.some((group) => group.isLoading)
    || workspaceShareGroups.some((group) => group.isLoading);

  const workspaceRows = workspaces.map((workspace, index) => ({
    workspace,
    twinCount: workspaceTwinGroups[index]?.twins.length ?? 0,
  }));

  const recentTwins = twins.slice(0, 6);
  const greeting = user?.display_name
    ? `Welcome back, ${user.display_name.split(" ")[0]}`
    : "Welcome back";

  if (isLoading) {
    return (
      <AppShell>
        <div style={{ ...s.center, paddingTop: isMobile ? 80 : 48 }}>Loading dashboard…</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
        <section style={s.hero}>
          <div>
            <p style={s.eyebrow}>Dashboard</p>
            <h1 style={s.title}>{greeting}</h1>
            <p style={s.subtitle}>
              Workspaces are your top-level containers. Twins live inside them, and workspace
              chat routes each question to the most relevant twin in that workspace.
            </p>
          </div>
          <div style={s.heroActions}>
            <Link to="/workspaces" style={s.primaryLink}>
              Manage workspaces
            </Link>
            <Link to="/twins" style={s.secondaryLink}>
              Manage twins
            </Link>
          </div>
        </section>

        <section style={s.statsGrid}>
          <StatCard
            label="Workspaces"
            value={String(workspaces.length)}
            note="Separate knowledge boundaries for teams, clients, or projects."
          />
          <StatCard
            label="Twins"
            value={String(twins.length)}
            note="Project-specific conversational agents attached to a workspace."
          />
          <StatCard
            label="Public twins"
            value={String(publicTwins.length)}
            note="Twins currently marked public in their owner configuration."
          />
          <StatCard
            label="Public workspace pages"
            value={String(publicWorkspacePages.length)}
            note="Shared workspace-wide chat surfaces exposed through `/w/:slug`."
          />
        </section>

        {workspaces.length === 0 ? (
          <section style={s.emptyState}>
            <h2 style={s.emptyTitle}>Create your first workspace</h2>
            <p style={s.emptyBody}>
              Once a workspace exists, you can add twins inside it and use workspace chat
              to route questions across those twins automatically.
            </p>
            <Link to="/workspaces" style={s.primaryLink}>
              Go to workspaces
            </Link>
          </section>
        ) : (
          <section style={s.contentGrid}>
            <section style={s.panel}>
              <div style={s.panelHeader}>
                <div>
                  <p style={s.panelEyebrow}>Workspaces</p>
                  <h2 style={s.panelTitle}>Open any workspace chat</h2>
                </div>
                <Link to="/workspaces" style={s.inlineLink}>
                  View all
                </Link>
              </div>
              <p style={s.panelBody}>
                Clicking a workspace opens its routed chat. Use the workspaces page to create
                or delete workspaces.
              </p>

              <div style={s.list}>
                {workspaceRows.map(({ workspace, twinCount }) => (
                  <div
                    key={workspace.id}
                    style={{ ...s.listRow, alignItems: isMobile ? "flex-start" : "center" }}
                  >
                    <div style={s.avatar}>{workspace.name.charAt(0).toUpperCase()}</div>
                    <div style={{ ...s.listMeta, flexBasis: isMobile ? "calc(100% - 50px)" : undefined }}>
                      <div style={s.listTitle}>{workspace.name}</div>
                      <div style={s.listBody}>
                        {workspace.description || "Workspace-wide chat and grouped twins."}
                      </div>
                    </div>
                    <div style={s.rowTags}>
                      <span style={s.tag}>{twinCount} twin{twinCount === 1 ? "" : "s"}</span>
                    </div>
                    <Link to={`/workspace/${workspace.id}/chat`} style={s.rowLink}>
                      Open chat
                    </Link>
                  </div>
                ))}
              </div>
            </section>

            <section style={s.panel}>
              <div style={s.panelHeader}>
                <div>
                  <p style={s.panelEyebrow}>Twins</p>
                  <h2 style={s.panelTitle}>Twin directory snapshot</h2>
                </div>
                <Link to="/twins" style={s.inlineLink}>
                  View all
                </Link>
              </div>
              <p style={s.panelBody}>
                Use the twins page to create, review, or delete twins inside each workspace.
              </p>

              {recentTwins.length === 0 ? (
                <div style={s.emptyPanel}>
                  <div style={s.emptyPanelTitle}>No twins yet</div>
                  <div style={s.emptyPanelBody}>
                    Create your first twin from the twins page after setting up a workspace.
                  </div>
                  <Link to="/twins" style={s.secondaryLink}>
                    Go to twins
                  </Link>
                </div>
              ) : (
                <div style={s.list}>
                  {recentTwins.map((twin) => (
                    <TwinRow key={twin.id} twin={twin} workspaceName={findWorkspaceName(workspaceRows, twin)} />
                  ))}
                </div>
              )}
            </section>
          </section>
        )}
      </div>
    </AppShell>
  );
}

function findWorkspaceName(
  rows: Array<{ workspace: { id: string; name: string } }>,
  twin: Twin,
) {
  return rows.find((row) => row.workspace.id === twin.workspace_id)?.workspace.name ?? "Workspace";
}

function TwinRow({
  twin,
  workspaceName,
}: {
  twin: Twin;
  workspaceName: string;
}) {
  const isMobile = useIsMobile();
  return (
    <div style={{ ...s.listRow, alignItems: isMobile ? "flex-start" : "center" }}>
      <div style={s.avatar}>{(twin.config?.display_name || twin.name).charAt(0).toUpperCase()}</div>
      <div style={{ ...s.listMeta, flexBasis: isMobile ? "calc(100% - 50px)" : undefined }}>
        <div style={s.listTitle}>{twin.config?.display_name || twin.name}</div>
        <div style={s.listBody}>
          {twin.description || `${workspaceName} twin`}
        </div>
      </div>
      <div style={s.rowTags}>
        <span style={s.tag}>{workspaceName}</span>
        <span style={twin.config?.is_public ? s.tagPublic : s.tagMuted}>
          {twin.config?.is_public ? "Public" : "Private"}
        </span>
      </div>
      <Link to={`/twin/${twin.id}`} style={s.rowLink}>
        Open twin
      </Link>
    </div>
  );
}

function StatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div style={s.statCard}>
      <div style={s.statLabel}>{label}</div>
      <div style={s.statValue}>{value}</div>
      <div style={s.statNote}>{note}</div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 1240,
    margin: "0 auto",
    padding: "34px 32px 40px",
    display: "flex",
    flexDirection: "column",
    gap: 22,
  },
  center: {
    padding: "48px 32px",
    color: "var(--color-text-secondary)",
  },
  hero: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 18,
    flexWrap: "wrap",
    padding: "30px",
    borderRadius: 24,
    background:
      "linear-gradient(135deg, rgba(15,118,110,0.12), rgba(15,23,42,0.05) 60%, rgba(255,255,255,0.92))",
    border: "1px solid rgba(15,118,110,0.12)",
  },
  eyebrow: {
    margin: 0,
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-teal)",
  },
  title: {
    margin: "10px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 34,
    letterSpacing: "-0.03em",
    color: "var(--color-text-primary)",
  },
  subtitle: {
    margin: "12px 0 0",
    maxWidth: 760,
    fontSize: 15,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  heroActions: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  primaryLink: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "11px 18px",
    borderRadius: 12,
    background: "var(--color-teal)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    textDecoration: "none",
  },
  secondaryLink: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "11px 18px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    background: "rgba(255,255,255,0.84)",
    color: "var(--color-text-primary)",
    fontSize: 14,
    fontWeight: 600,
    textDecoration: "none",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 14,
  },
  statCard: {
    padding: "18px 20px",
    borderRadius: 18,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    boxShadow: "var(--shadow-sm)",
  },
  statLabel: {
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-text-tertiary)",
  },
  statValue: {
    marginTop: 10,
    fontFamily: "var(--font-display)",
    fontSize: 30,
    letterSpacing: "-0.03em",
    color: "var(--color-text-primary)",
  },
  statNote: {
    marginTop: 8,
    fontSize: 13,
    lineHeight: 1.5,
    color: "var(--color-text-secondary)",
  },
  contentGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
    gap: 18,
  },
  panel: {
    padding: "22px",
    borderRadius: 20,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    boxShadow: "var(--shadow-sm)",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
  },
  panelEyebrow: {
    margin: 0,
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-teal)",
  },
  panelTitle: {
    margin: "6px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 22,
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  panelBody: {
    margin: 0,
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  inlineLink: {
    color: "var(--color-teal)",
    fontSize: 13,
    fontWeight: 700,
    textDecoration: "none",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  listRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    flexWrap: "wrap",
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: 13,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, rgba(15,118,110,0.16), rgba(15,23,42,0.12))",
    color: "var(--color-text-primary)",
    fontWeight: 700,
    flexShrink: 0,
  },
  listMeta: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  listTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  listBody: {
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--color-text-secondary)",
  },
  rowTags: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  tag: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    color: "var(--color-text-secondary)",
  },
  tagMuted: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "rgba(148,163,184,0.12)",
    color: "var(--color-text-secondary)",
    border: "1px solid rgba(148,163,184,0.18)",
  },
  tagPublic: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "rgba(15,118,110,0.12)",
    color: "var(--color-teal)",
    border: "1px solid rgba(15,118,110,0.14)",
  },
  rowLink: {
    color: "var(--color-teal)",
    textDecoration: "none",
    fontSize: 13,
    fontWeight: 700,
    flexShrink: 0,
  },
  emptyState: {
    padding: "26px 24px",
    borderRadius: 20,
    border: "1px dashed rgba(15,118,110,0.24)",
    background: "rgba(15,118,110,0.04)",
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: 12,
  },
  emptyTitle: {
    margin: 0,
    fontSize: 22,
    fontFamily: "var(--font-display)",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
  },
  emptyBody: {
    margin: 0,
    maxWidth: 700,
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  emptyPanel: {
    padding: "16px",
    borderRadius: 16,
    border: "1px dashed rgba(15,118,110,0.18)",
    background: "rgba(15,118,110,0.04)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    alignItems: "flex-start",
  },
  emptyPanelTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  emptyPanelBody: {
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
};
