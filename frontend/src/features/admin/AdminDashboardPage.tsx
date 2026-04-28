import { useIsMobile } from "@/hooks/useIsMobile";
import { useAdminPlatformStats } from "@/hooks/useAdmin";
import { adminStyles as s } from "@/features/admin/styles";

export default function AdminDashboardPage() {
  const isMobile = useIsMobile();
  const { data: stats, isLoading: statsLoading, error: statsError, refetch } = useAdminPlatformStats();

  return (
    <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
      <section style={s.hero}>
        <div>
          <p style={s.eyebrow}>Platform</p>
          <h1 style={s.title}>Dashboard</h1>
          <p style={s.subtitle}>
            High-level counts across all accounts, workspaces, twins, and indexed sources.
          </p>
        </div>
        <button type="button" style={s.refreshBtn} onClick={() => refetch()}>
          Refresh
        </button>
      </section>

      {statsError && (
        <div style={s.banner}>Could not load stats — check that you are signed in as a superuser.</div>
      )}

      <section style={s.statsGrid}>
        <StatCard
          label="Users"
          value={statsLoading ? "…" : String(stats?.users ?? "—")}
          note="Registered accounts"
        />
        <StatCard
          label="Workspaces"
          value={statsLoading ? "…" : String(stats?.workspaces ?? "—")}
          note="All workspaces"
        />
        <StatCard
          label="Twins"
          value={statsLoading ? "…" : String(stats?.twins ?? "—")}
          note="Knowledge twins"
        />
        <StatCard
          label="Sources"
          value={statsLoading ? "…" : String(stats?.sources_total ?? "—")}
          note="Attached sources (all statuses)"
        />
      </section>

      {stats?.sources_by_status && Object.keys(stats.sources_by_status).length > 0 && (
        <section style={s.panel}>
          <p style={s.panelEyebrow}>Sources by status</p>
          <div style={s.chips}>
            {Object.entries(stats.sources_by_status).map(([status, count]) => (
              <span key={status} style={s.chip}>
                {status}: <strong>{count}</strong>
              </span>
            ))}
          </div>
        </section>
      )}
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
