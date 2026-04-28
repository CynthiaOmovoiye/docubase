import { FormEvent, useState } from "react";

import { useIsMobile } from "@/hooks/useIsMobile";
import {
  useAdminCreateOperator,
  useAdminUpdateUserRole,
  useAdminUsers,
} from "@/hooks/useAdmin";
import { adminStyles as s } from "@/features/admin/styles";
import { axiosDetail, formatJoined } from "@/features/admin/adminUtils";
import { useAuthStore } from "@/store/authStore";

export default function AdminUsersAdminsPage() {
  const isMobile = useIsMobile();
  const currentUserId = useAuthStore((state) => state.user?.id);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const {
    data: usersPayload,
    isLoading,
    refetch,
    error: usersError,
  } = useAdminUsers();
  const updateRole = useAdminUpdateUserRole();
  const createOperator = useAdminCreateOperator();

  const admins = usersPayload?.users.filter((u) => u.is_superuser) ?? [];

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !password) return;
    createOperator.mutate(
      {
        email: trimmedEmail,
        password,
        display_name: displayName.trim() || null,
      },
      {
        onSuccess: () => {
          setEmail("");
          setPassword("");
          setDisplayName("");
        },
      }
    );
  }

  const formValid =
    email.trim().length > 0 && password.length >= 8;

  return (
    <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
      <section style={s.hero}>
        <div>
          <p style={s.eyebrow}>Users</p>
          <h1 style={s.title}>Admin users</h1>
          <p style={s.subtitle}>
            Platform operators — accounts that can access /admin and internal APIs. Creating an
            operator provisions a new login; the email must not already belong to any account.
          </p>
        </div>
        <button type="button" style={s.refreshBtn} onClick={() => refetch()}>
          Refresh list
        </button>
      </section>

      <section style={s.panel}>
        <p style={s.panelEyebrow}>Create operator</p>
        <h2 style={s.panelTitle}>New admin account</h2>
        <p style={s.panelBody}>
          Password must be at least 8 characters and not all digits (same rules as signup).
          If that email already belongs to an account, creation fails — use Remove admin / role
          controls for existing rows, or PATCH admin users with is_superuser.
        </p>
        <form
          onSubmit={handleCreateSubmit}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 14,
            marginTop: 16,
            maxWidth: 440,
          }}
        >
          <div style={{ ...s.formRow, marginTop: 0 }}>
            <label style={s.label} htmlFor="operator-email">
              Email address
            </label>
            <input
              id="operator-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
              placeholder="ops@company.com"
              style={s.inputEmail}
            />
          </div>
          <div style={{ ...s.formRow, marginTop: 0 }}>
            <label style={s.label} htmlFor="operator-password">
              Password
            </label>
            <input
              id="operator-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              placeholder="••••••••"
              style={s.input}
            />
          </div>
          <div style={{ ...s.formRow, marginTop: 0 }}>
            <label style={s.label} htmlFor="operator-name">
              Display name <span style={{ fontWeight: 500, opacity: 0.75 }}>(optional)</span>
            </label>
            <input
              id="operator-name"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(ev) => setDisplayName(ev.target.value)}
              placeholder="Operations"
              style={s.inputEmail}
            />
          </div>
          <div>
            <button
              type="submit"
              disabled={!formValid || createOperator.isPending}
              style={formValid && !createOperator.isPending ? s.primaryBtn : s.primaryBtnDisabled}
            >
              {createOperator.isPending ? "Creating…" : "Create operator"}
            </button>
          </div>
        </form>
        {createOperator.isError && (
          <p style={s.errorText}>{axiosDetail(createOperator.error)}</p>
        )}
        {createOperator.isSuccess && (
          <p style={s.successText}>Operator account created. They can sign in with this email.</p>
        )}
      </section>

      {usersError && <p style={s.errorText}>Could not load users.</p>}

      <section style={s.panel}>
        <div style={s.panelHeaderRow}>
          <div>
            <p style={s.panelEyebrow}>Operators</p>
            <h2 style={s.panelTitle}>Current admins</h2>
          </div>
        </div>

        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Email</th>
                <th style={s.th}>Name</th>
                <th style={s.th}>Joined</th>
                <th style={s.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={4} style={s.tdMuted}>
                    Loading…
                  </td>
                </tr>
              )}
              {!isLoading && admins.length === 0 && (
                <tr>
                  <td colSpan={4} style={s.tdMuted}>
                    No admin users yet.
                  </td>
                </tr>
              )}
              {!isLoading
                && admins.map((u) => {
                  const isSelf = u.id === currentUserId;
                  const demoteBlocked = isSelf;
                  return (
                    <tr key={u.id}>
                      <td style={s.td}>{u.email}</td>
                      <td style={s.td}>{u.display_name ?? "—"}</td>
                      <td style={s.td}>{formatJoined(u.created_at)}</td>
                      <td style={s.td}>
                        <button
                          type="button"
                          disabled={demoteBlocked || updateRole.isPending}
                          title={
                            demoteBlocked ? "You cannot remove your own admin access here." : undefined
                          }
                          style={demoteBlocked ? s.linkBtnDisabled : s.linkBtnDanger}
                          onClick={() => updateRole.mutate({ userId: u.id, is_superuser: false })}
                        >
                          Remove admin
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {updateRole.isError && <p style={s.errorText}>{axiosDetail(updateRole.error)}</p>}
      </section>
    </div>
  );
}
