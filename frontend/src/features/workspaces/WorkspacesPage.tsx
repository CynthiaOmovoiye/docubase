import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import AppShell from "@/components/AppShell";
import {
  useCreateWorkspaceSharePage,
  useRevokeShareSurface,
  useWorkspaceShareSurfaces,
  useWorkspaceShareSurfacesForWorkspaces,
} from "@/hooks/useSharing";
import { useTwinsForWorkspaces } from "@/hooks/useTwins";
import {
  useCreateWorkspace,
  useDeleteWorkspace,
  useWorkspaces,
} from "@/hooks/useWorkspaces";

export default function WorkspacesPage() {
  const navigate = useNavigate();
  const { data: workspaces = [], isLoading: workspacesLoading } = useWorkspaces();
  const workspaceTwinGroups = useTwinsForWorkspaces(workspaces);
  const workspaceShareGroups = useWorkspaceShareSurfacesForWorkspaces(workspaces);
  const createWorkspace = useCreateWorkspace();
  const deleteWorkspace = useDeleteWorkspace();

  const [showCreate, setShowCreate] = useState(false);
  const [shareWorkspace, setShareWorkspace] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      workspaces.map((workspace, index) => ({
        workspace,
        twinCount: workspaceTwinGroups[index]?.twins.length ?? 0,
        publicPageCount:
          workspaceShareGroups[index]?.surfaces.filter(
            (surface) => surface.surface_type === "workspace_page",
          ).length ?? 0,
      })),
    [workspaces, workspaceTwinGroups, workspaceShareGroups],
  );

  const isLoading =
    workspacesLoading
    || workspaceTwinGroups.some((group) => group.isLoading)
    || workspaceShareGroups.some((group) => group.isLoading);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      const workspace = await createWorkspace.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setShowCreate(false);
      setName("");
      setDescription("");
      navigate(`/workspace/${workspace.id}/chat`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message
        || "Could not create workspace. Try again.";
      setError(msg);
    }
  }

  async function handleDelete(workspaceId: string, workspaceName: string) {
    if (!window.confirm(`Delete workspace "${workspaceName}"? This removes all twins inside it.`)) {
      return;
    }
    await deleteWorkspace.mutateAsync(workspaceId);
  }

  return (
    <AppShell>
      <div style={s.page}>
        <div style={s.header}>
          <div>
            <p style={s.eyebrow}>Workspaces</p>
            <h1 style={s.title}>Manage your workspaces</h1>
            <p style={s.subtitle}>
              Create, open, and remove workspaces here. The Public link button on each row
              creates a shareable URL for workspace-wide routed chat (like a twin share link,
              but for the whole workspace).
            </p>
          </div>
          <button style={s.primaryBtn} onClick={() => setShowCreate(true)}>
            + New workspace
          </button>
        </div>

        {isLoading && <div style={s.center}>Loading workspaces…</div>}

        {!isLoading && rows.length === 0 && (
          <div style={s.empty}>
            <h2 style={s.emptyTitle}>No workspaces yet</h2>
            <p style={s.emptyBody}>
              Create your first workspace to start organizing twins and routed chats.
            </p>
            <button style={s.primaryBtn} onClick={() => setShowCreate(true)}>
              Create workspace
            </button>
          </div>
        )}

        {!isLoading && rows.length > 0 && (
          <div style={s.list}>
            {rows.map(({ workspace, twinCount, publicPageCount }) => (
              <div
                key={workspace.id}
                style={s.row}
                onClick={() => navigate(`/workspace/${workspace.id}/chat`)}
              >
                <div style={s.rowAvatar}>{workspace.name.charAt(0).toUpperCase()}</div>
                <div style={s.rowMeta}>
                  <div style={s.rowTop}>
                    <h2 style={s.rowTitle}>{workspace.name}</h2>
                    <div style={s.chips}>
                      <span style={s.chip}>{twinCount} twin{twinCount === 1 ? "" : "s"}</span>
                      <span style={s.chip}>
                        {publicPageCount} public page{publicPageCount === 1 ? "" : "s"}
                      </span>
                    </div>
                  </div>
                  <p style={s.rowDescription}>
                    {workspace.description || "Workspace-wide routed chat and grouped twins."}
                  </p>
                  <p style={s.rowSlug}>/{workspace.slug}</p>
                </div>
                <div style={s.rowActions}>
                  <button
                    style={s.secondaryBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/workspace/${workspace.id}/chat`);
                    }}
                  >
                    Open chat
                  </button>
                  <button
                    style={s.secondaryBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/twins?workspace=${workspace.id}`);
                    }}
                  >
                    View twins
                  </button>
                  <button
                    style={s.secondaryBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      setShareWorkspace({ id: workspace.id, name: workspace.name });
                    }}
                  >
                    Public link
                  </button>
                  <button
                    style={s.deleteBtn}
                    disabled={deleteWorkspace.isPending}
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDelete(workspace.id, workspace.name);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {shareWorkspace && (
        <Modal onClose={() => setShareWorkspace(null)}>
          <h2 style={s.modalTitle}>Public link — {shareWorkspace.name}</h2>
          <p style={s.modalSubtitle}>
            Visitors can chat on this workspace&apos;s routed surface without signing in. They
            cannot change workspace or twin settings.
          </p>
          <WorkspaceShareLinksPanel workspaceId={shareWorkspace.id} />
        </Modal>
      )}

      {showCreate && (
        <Modal onClose={() => { setShowCreate(false); setError(null); }}>
          <h2 style={s.modalTitle}>Create workspace</h2>
          <p style={s.modalSubtitle}>
            Workspaces group twins and provide a workspace-level routed chat surface.
          </p>
          <form onSubmit={handleCreate} style={s.form}>
            {error && <div style={s.errorBox}>{error}</div>}
            <div style={s.field}>
              <label style={s.label} htmlFor="workspace-name">Name</label>
              <input
                id="workspace-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={s.input}
                maxLength={120}
                autoFocus
                required
              />
            </div>
            <div style={s.field}>
              <label style={s.label} htmlFor="workspace-description">Description</label>
              <textarea
                id="workspace-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                style={s.textarea}
                maxLength={500}
              />
            </div>
            <div style={s.modalActions}>
              <button
                type="button"
                style={s.secondaryBtn}
                onClick={() => { setShowCreate(false); setError(null); }}
              >
                Cancel
              </button>
              <button type="submit" style={s.primaryBtn} disabled={createWorkspace.isPending}>
                {createWorkspace.isPending ? "Creating…" : "Create workspace"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </AppShell>
  );
}

function WorkspaceShareLinksPanel({ workspaceId }: { workspaceId: string }) {
  const { data: surfaces = [], isLoading } = useWorkspaceShareSurfaces(workspaceId);
  const createPage = useCreateWorkspaceSharePage();
  const revoke = useRevokeShareSurface();
  const [copied, setCopied] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const pageLinks = surfaces.filter((surface) => surface.surface_type === "workspace_page");

  function copyUrl(url: string, id: string) {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  return (
    <div style={sh.panel}>
      <div style={sh.header}>
        <span style={sh.panelTitle}>Share URL</span>
        {pageLinks.length === 0 && (
          <button
            type="button"
            style={sh.generateBtn}
            disabled={createPage.isPending || isLoading}
            onClick={() => createPage.mutate(workspaceId)}
          >
            {createPage.isPending ? "Generating…" : "Generate link"}
          </button>
        )}
      </div>

      {createPage.isError && (
        <p style={sh.error}>Failed to generate link. It may already exist.</p>
      )}

      {isLoading && <p style={sh.hint}>Loading…</p>}

      {!isLoading && pageLinks.length === 0 && (
        <p style={sh.hint}>
          No public link yet. Generate one to share workspace-wide routed chat.
        </p>
      )}

      {pageLinks.map((surface) => (
        <div key={surface.id} style={sh.linkRow}>
          <span style={sh.url}>{surface.public_url}</span>
          <div style={sh.actions}>
            <button
              type="button"
              style={sh.copyBtn}
              onClick={() => copyUrl(surface.public_url, surface.id)}
            >
              {copied === surface.id ? "✓ Copied" : "Copy"}
            </button>
            <button
              type="button"
              style={sh.revokeBtn}
              disabled={revoking === surface.id}
              onClick={() => {
                setRevoking(surface.id);
                revoke.mutate(
                  { surfaceId: surface.id, workspaceId },
                  { onSettled: () => setRevoking(null) },
                );
              }}
            >
              {revoking === surface.id ? "Revoking…" : "Revoke"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

const sh: Record<string, React.CSSProperties> = {
  panel: {
    marginTop: 4,
    border: "1px solid var(--color-border)",
    borderRadius: 12,
    padding: "14px 16px",
    background: "var(--color-bg)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
    gap: 12,
    flexWrap: "wrap",
  },
  panelTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  generateBtn: {
    fontSize: 12,
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid var(--color-iris)",
    background: "var(--color-iris)",
    color: "#fff",
    cursor: "pointer",
  },
  hint: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    margin: 0,
    lineHeight: 1.5,
  },
  error: {
    fontSize: 13,
    color: "var(--color-rose)",
    margin: "0 0 8px",
  },
  linkRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "10px 0 0",
    marginTop: 8,
    borderTop: "1px solid var(--color-border)",
    flexWrap: "wrap",
  },
  url: {
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    color: "var(--color-text-primary)",
    wordBreak: "break-all",
    flex: 1,
    minWidth: 0,
  },
  actions: {
    display: "flex",
    gap: 8,
    flexShrink: 0,
  },
  copyBtn: {
    fontSize: 12,
    padding: "5px 12px",
    borderRadius: 8,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
  },
  revokeBtn: {
    fontSize: 12,
    padding: "5px 12px",
    borderRadius: 8,
    border: "1px solid rgba(239,68,68,0.35)",
    background: "transparent",
    color: "var(--color-rose)",
    cursor: "pointer",
  },
};

function Modal({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div style={s.overlay} onClick={onClose}>
      <div style={s.modal} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 1100,
    margin: "0 auto",
    padding: "36px 32px 42px",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-start",
    flexWrap: "wrap",
    marginBottom: 24,
  },
  eyebrow: {
    margin: 0,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--color-iris)",
  },
  title: {
    margin: "10px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 30,
    letterSpacing: "-0.03em",
    color: "var(--color-text-primary)",
  },
  subtitle: {
    margin: "10px 0 0",
    maxWidth: 700,
    fontSize: 15,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  row: {
    display: "flex",
    gap: 16,
    alignItems: "flex-start",
    padding: "18px 18px 18px 16px",
    borderRadius: 18,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    cursor: "pointer",
    boxShadow: "var(--shadow-sm)",
  },
  rowAvatar: {
    width: 42,
    height: 42,
    borderRadius: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, rgba(99,102,241,0.14), rgba(20,184,166,0.18))",
    color: "var(--color-text-primary)",
    fontWeight: 700,
    flexShrink: 0,
  },
  rowMeta: {
    flex: 1,
    minWidth: 0,
  },
  rowTop: {
    display: "flex",
    // justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start",
    flexWrap: "wrap",
  },
  rowTitle: {
    margin: 0,
    fontSize: 18,
    fontFamily: "var(--font-display)",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
  },
  chips: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  chip: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "var(--color-bg)",
    color: "var(--color-text-secondary)",
    border: "1px solid var(--color-border)",
  },
  rowDescription: {
    margin: "8px 0 0",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  rowSlug: {
    margin: "8px 0 0",
    fontSize: 12,
    color: "var(--color-text-tertiary)",
    fontFamily: "var(--font-mono)",
  },
  rowActions: {
    display: "flex",
    gap: 8,
    flexShrink: 0,
    alignItems: "center",
  },
  primaryBtn: {
    padding: "10px 16px",
    borderRadius: 10,
    border: "none",
    background: "var(--color-iris)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    cursor: "pointer",
  },
  secondaryBtn: {
    padding: "10px 14px",
    borderRadius: 10,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-primary)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  deleteBtn: {
    padding: "10px 14px",
    borderRadius: 10,
    border: "1px solid rgba(239,68,68,0.2)",
    background: "rgba(239,68,68,0.08)",
    color: "var(--color-rose)",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
  },
  center: {
    padding: "48px 0",
    color: "var(--color-text-secondary)",
  },
  empty: {
    padding: "56px 24px",
    borderRadius: 20,
    textAlign: "center",
    border: "1px dashed rgba(99,102,241,0.2)",
    background: "rgba(99,102,241,0.05)",
  },
  emptyTitle: {
    margin: 0,
    fontFamily: "var(--font-display)",
    fontSize: 24,
    color: "var(--color-text-primary)",
  },
  emptyBody: {
    margin: "10px auto 0",
    maxWidth: 420,
    color: "var(--color-text-secondary)",
    lineHeight: 1.7,
  },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.36)",
    backdropFilter: "blur(6px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    zIndex: 120,
  },
  modal: {
    width: "100%",
    maxWidth: 500,
    background: "var(--color-surface)",
    borderRadius: 20,
    padding: "30px 28px",
    boxShadow: "var(--shadow-lg)",
    border: "1px solid var(--color-border)",
  },
  modalTitle: {
    margin: 0,
    fontFamily: "var(--font-display)",
    fontSize: 22,
    color: "var(--color-text-primary)",
  },
  modalSubtitle: {
    margin: "8px 0 20px",
    color: "var(--color-text-secondary)",
    lineHeight: 1.6,
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  label: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  input: {
    width: "100%",
    padding: "11px 14px",
    fontSize: 14,
    color: "var(--color-text-primary)",
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 10,
    boxSizing: "border-box",
  },
  textarea: {
    width: "100%",
    minHeight: 90,
    padding: "11px 14px",
    fontSize: 14,
    color: "var(--color-text-primary)",
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 10,
    boxSizing: "border-box",
    resize: "vertical",
  },
  modalActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
  },
  errorBox: {
    background: "rgba(239,68,68,0.08)",
    border: "1px solid rgba(239,68,68,0.3)",
    borderRadius: 10,
    padding: "10px 14px",
    fontSize: 13,
    color: "#EF4444",
  },
};
