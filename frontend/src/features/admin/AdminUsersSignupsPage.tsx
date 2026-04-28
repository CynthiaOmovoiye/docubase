import { useIsMobile } from "@/hooks/useIsMobile";
import { useAdminConsumerSignups } from "@/hooks/useAdmin";
import { adminStyles as s } from "@/features/admin/styles";
import { formatJoined } from "@/features/admin/adminUtils";

export default function AdminUsersSignupsPage() {
  const isMobile = useIsMobile();
  const { data: usersPayload, isLoading, refetch, error: usersError } = useAdminConsumerSignups();
  const rows = usersPayload?.users ?? [];

  return (
    <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
      <section style={s.hero}>
        <div>
          <p style={s.eyebrow}>Users</p>
          <h1 style={s.title}>Signups</h1>
          <p style={s.subtitle}>
            Consumer accounts only (newest first). Platform operators are listed under Admin users, not
            here.
          </p>
        </div>
        <button type="button" style={s.refreshBtn} onClick={() => refetch()}>
          Refresh list
        </button>
      </section>

      {usersError && <p style={s.errorText}>Could not load users.</p>}

      <section style={s.panel}>
        <div style={s.tableWrap}>
          <table style={{ ...s.table, minWidth: 640 }}>
            <thead>
              <tr>
                <th style={s.th}>Email</th>
                <th style={s.th}>Name</th>
                <th style={s.th}>Verified</th>
                <th style={s.th}>Active</th>
                <th style={s.th}>Joined</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={5} style={s.tdMuted}>
                    Loading…
                  </td>
                </tr>
              )}
              {!isLoading && rows.length === 0 && (
                <tr>
                  <td colSpan={5} style={s.tdMuted}>
                    No signups yet.
                  </td>
                </tr>
              )}
              {!isLoading
                && rows.map((u) => (
                  <tr key={u.id}>
                    <td style={s.td}>{u.email}</td>
                    <td style={s.td}>{u.display_name ?? "—"}</td>
                    <td style={s.td}>{u.is_verified ? "Yes" : "No"}</td>
                    <td style={s.td}>{u.is_active ? "Yes" : "No"}</td>
                    <td style={s.td}>{formatJoined(u.created_at)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
