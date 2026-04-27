import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import AppShell from "@/components/AppShell";
import { useIsMobile } from "@/hooks/useIsMobile";
import {
  useCreateTwin,
  useDeleteTwin,
  useTwinsForWorkspaces,
} from "@/hooks/useTwins";
import { useWorkspaces } from "@/hooks/useWorkspaces";

export default function TwinsPage() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: workspaces = [], isLoading: workspacesLoading } = useWorkspaces();
  const workspaceTwinGroups = useTwinsForWorkspaces(workspaces);
  const createTwin = useCreateTwin();
  const deleteTwin = useDeleteTwin();

  const [showCreate, setShowCreate] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const workspaceFilter = searchParams.get("workspace") ?? "";

  const visibleGroups = useMemo(() => {
    if (!workspaceFilter) return workspaceTwinGroups;
    return workspaceTwinGroups.filter((group) => group.workspace.id === workspaceFilter);
  }, [workspaceFilter, workspaceTwinGroups]);

  const totalTwinCount = workspaceTwinGroups.reduce((sum, group) => sum + group.twins.length, 0);
  const isLoading = workspacesLoading || workspaceTwinGroups.some((group) => group.isLoading);
  const selectedWorkspace = workspaces.find((workspace) => workspace.id === workspaceFilter) ?? null;

  function openCreateModal(workspaceId?: string) {
    setSelectedWorkspaceId(workspaceId || selectedWorkspace?.id || workspaces[0]?.id || "");
    setName("");
    setDescription("");
    setError(null);
    setShowCreate(true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedWorkspaceId || !name.trim()) return;
    setError(null);
    try {
      const twin = await createTwin.mutateAsync({
        workspace_id: selectedWorkspaceId,
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setShowCreate(false);
      navigate(`/twin/${twin.id}`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message
        || "Could not create twin. Try again.";
      setError(msg);
    }
  }

  async function handleDelete(twinId: string, workspaceId: string, twinName: string) {
    if (!window.confirm(`Delete twin "${twinName}"? This also removes its sources and chat history.`)) {
      return;
    }
    await deleteTwin.mutateAsync({ twinId, workspaceId });
  }

  function clearFilter() {
    setSearchParams({});
  }

  return (
    <AppShell>
      <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "36px 32px 42px" }}>
        <div style={s.header}>
          <div>
            <p style={s.eyebrow}>Twins</p>
            <h1 style={s.title}>Manage twins across workspaces</h1>
            <p style={s.subtitle}>
              Create twins inside a workspace, open any twin, or remove twins you no longer need.
            </p>
          </div>

          <div style={s.headerActions}>
            {workspaces.length > 0 && (
              <select
                value={workspaceFilter}
                onChange={(e) => {
                  const value = e.target.value;
                  if (!value) {
                    clearFilter();
                    return;
                  }
                  setSearchParams({ workspace: value });
                }}
                style={s.select}
              >
                <option value="">All workspaces</option>
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            )}
            <button
              style={s.primaryBtn}
              onClick={() => openCreateModal()}
              disabled={workspaces.length === 0}
            >
              + New twin
            </button>
          </div>
        </div>

        {isLoading && <div style={s.center}>Loading twins…</div>}

        {!isLoading && workspaces.length === 0 && (
          <div style={s.empty}>
            <h2 style={s.emptyTitle}>Create a workspace first</h2>
            <p style={s.emptyBody}>
              Twins must belong to a workspace. Start by creating a workspace, then come back
              here to add twins inside it.
            </p>
            <Link to="/workspaces" style={s.primaryLink}>
              Go to workspaces
            </Link>
          </div>
        )}

        {!isLoading && workspaces.length > 0 && totalTwinCount === 0 && (
          <div style={s.empty}>
            <h2 style={s.emptyTitle}>No twins yet</h2>
            <p style={s.emptyBody}>
              Create your first twin and attach sources to give it grounded knowledge.
            </p>
            <button style={s.primaryBtn} onClick={() => openCreateModal()}>
              Create twin
            </button>
          </div>
        )}

        {!isLoading && workspaces.length > 0 && totalTwinCount > 0 && visibleGroups.length === 0 && (
          <div style={s.empty}>
            <h2 style={s.emptyTitle}>Workspace filter is empty</h2>
            <p style={s.emptyBody}>
              There are no twins in the selected workspace yet. You can create one now or clear
              the filter to see all twins.
            </p>
            <div style={s.emptyActions}>
              <button style={s.primaryBtn} onClick={() => openCreateModal(workspaceFilter)}>
                Create twin here
              </button>
              <button style={s.secondaryBtn} onClick={clearFilter}>
                Clear filter
              </button>
            </div>
          </div>
        )}

        {!isLoading && visibleGroups.length > 0 && (
          <div style={s.groupList}>
            {visibleGroups.map((group) => (
              <section key={group.workspace.id} style={s.groupCard}>
                <div style={s.groupHeader}>
                  <div>
                    <p style={s.groupEyebrow}>Workspace</p>
                    <h2 style={s.groupTitle}>{group.workspace.name}</h2>
                    <p style={s.groupSubtitle}>
                      {group.workspace.description || "Twins grouped under this workspace."}
                    </p>
                  </div>

                  <div style={s.groupActions}>
                    <Link to={`/workspace/${group.workspace.id}/chat`} style={s.inlineLink}>
                      Open chat
                    </Link>
                    <button
                      style={s.secondaryBtn}
                      onClick={() => openCreateModal(group.workspace.id)}
                    >
                      Add twin
                    </button>
                  </div>
                </div>

                {group.twins.length === 0 ? (
                  <div style={s.groupEmpty}>
                    <p style={s.groupEmptyText}>No twins in this workspace yet.</p>
                    <button style={s.secondaryBtn} onClick={() => openCreateModal(group.workspace.id)}>
                      Create first twin
                    </button>
                  </div>
                ) : (
                  <div style={s.rows}>
                    {group.twins.map((twin) => (
                      <div
                        key={twin.id}
                        style={s.row}
                        onClick={() => navigate(`/twin/${twin.id}`)}
                      >
                        <div style={s.rowAvatar}>
                          {(twin.config?.display_name || twin.name).charAt(0).toUpperCase()}
                        </div>

                        <div style={s.rowMeta}>
                          <div style={s.rowTop}>
                            <h3 style={s.rowTitle}>{twin.config?.display_name || twin.name}</h3>
                            <div style={s.rowChips}>
                              <span style={s.chip}>{twin.slug}</span>
                              <span style={twin.config?.is_public ? s.publicChip : s.privateChip}>
                                {twin.config?.is_public ? "Public" : "Private"}
                              </span>
                            </div>
                          </div>

                          <p style={s.rowDescription}>
                            {twin.description || "No description yet."}
                          </p>
                        </div>

                        <div style={{
                          ...s.rowActions,
                          width: isMobile ? "100%" : undefined,
                          marginLeft: isMobile ? 0 : "auto",
                        }}>
                          <button
                            style={s.inlineAction}
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/twin/${twin.id}`);
                            }}
                          >
                            Open
                          </button>
                          <button
                            style={s.deleteBtn}
                            disabled={deleteTwin.isPending}
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleDelete(
                                twin.id,
                                twin.workspace_id,
                                twin.config?.display_name || twin.name,
                              );
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal onClose={() => { setShowCreate(false); setError(null); }}>
          <h2 style={s.modalTitle}>Create twin</h2>
          <p style={s.modalSubtitle}>
            Twins are the conversational surfaces inside each workspace.
          </p>
          <form onSubmit={handleCreate} style={s.form}>
            {error && <div style={s.errorBox}>{error}</div>}

            <div style={s.field}>
              <label htmlFor="twin-workspace" style={s.label}>Workspace</label>
              <select
                id="twin-workspace"
                value={selectedWorkspaceId}
                onChange={(e) => setSelectedWorkspaceId(e.target.value)}
                style={s.select}
              >
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </div>

            <div style={s.field}>
              <label htmlFor="twin-name" style={s.label}>Name</label>
              <input
                id="twin-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={s.input}
                maxLength={120}
                autoFocus
                required
              />
            </div>

            <div style={s.field}>
              <label htmlFor="twin-description" style={s.label}>Description</label>
              <textarea
                id="twin-description"
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
              <button
                type="submit"
                style={s.primaryBtn}
                disabled={createTwin.isPending || !name.trim() || !selectedWorkspaceId}
              >
                {createTwin.isPending ? "Creating…" : "Create twin"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </AppShell>
  );
}

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
    maxWidth: 1160,
    margin: "0 auto",
    padding: "36px 32px 42px",
    display: "flex",
    flexDirection: "column",
    gap: 18,
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 16,
    flexWrap: "wrap",
  },
  eyebrow: {
    margin: 0,
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--color-teal)",
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
    maxWidth: 720,
    fontSize: 15,
    lineHeight: 1.7,
    color: "var(--color-text-secondary)",
  },
  headerActions: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
    alignItems: "center",
  },
  center: {
    padding: "40px 0",
    color: "var(--color-text-secondary)",
  },
  empty: {
    padding: "26px 24px",
    borderRadius: 20,
    border: "1px dashed rgba(15,118,110,0.22)",
    background: "rgba(15,118,110,0.04)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    alignItems: "flex-start",
  },
  emptyTitle: {
    margin: 0,
    fontFamily: "var(--font-display)",
    fontSize: 22,
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  emptyBody: {
    margin: 0,
    fontSize: 14,
    lineHeight: 1.7,
    maxWidth: 720,
    color: "var(--color-text-secondary)",
  },
  emptyActions: {
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
    border: "none",
    background: "var(--color-teal)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    textDecoration: "none",
  },
  primaryBtn: {
    padding: "11px 18px",
    borderRadius: 12,
    border: "none",
    background: "var(--color-teal)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    cursor: "pointer",
  },
  secondaryBtn: {
    padding: "10px 16px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-primary)",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    textDecoration: "none",
  },
  groupList: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  groupCard: {
    padding: 20,
    borderRadius: 20,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    boxShadow: "var(--shadow-sm)",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  groupHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 16,
    flexWrap: "wrap",
  },
  groupEyebrow: {
    margin: 0,
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    color: "var(--color-teal)",
  },
  groupTitle: {
    margin: "6px 0 0",
    fontFamily: "var(--font-display)",
    fontSize: 24,
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  groupSubtitle: {
    margin: "8px 0 0",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  groupActions: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  inlineLink: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "10px 14px",
    borderRadius: 12,
    background: "rgba(15,118,110,0.08)",
    color: "var(--color-teal)",
    fontSize: 13,
    fontWeight: 700,
    textDecoration: "none",
  },
  groupEmpty: {
    padding: "16px",
    borderRadius: 16,
    border: "1px dashed rgba(15,118,110,0.18)",
    background: "rgba(15,118,110,0.04)",
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    flexWrap: "wrap",
  },
  groupEmptyText: {
    margin: 0,
    fontSize: 14,
    color: "var(--color-text-secondary)",
  },
  rows: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  row: {
    display: "flex",
    gap: 14,
    alignItems: "flex-start",
    padding: "16px",
    borderRadius: 16,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    cursor: "pointer",
    flexWrap: "wrap",
  },
  rowAvatar: {
    width: 42,
    height: 42,
    borderRadius: 14,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, rgba(15,118,110,0.16), rgba(15,23,42,0.12))",
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
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  rowChips: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  chip: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "var(--color-surface)",
    color: "var(--color-text-secondary)",
    border: "1px solid var(--color-border)",
    fontFamily: "var(--font-mono)",
    whiteSpace: "nowrap",
  },
  publicChip: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "rgba(15,118,110,0.12)",
    color: "var(--color-teal)",
    border: "1px solid rgba(15,118,110,0.14)",
    whiteSpace: "nowrap",
  },
  privateChip: {
    padding: "5px 9px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
    background: "rgba(148,163,184,0.12)",
    color: "var(--color-text-secondary)",
    border: "1px solid rgba(148,163,184,0.18)",
    whiteSpace: "nowrap",
  },
  rowDescription: {
    margin: "8px 0 0",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  rowActions: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginLeft: "auto",
  },
  inlineAction: {
    padding: "9px 12px",
    borderRadius: 10,
    border: "1px solid var(--color-border)",
    background: "var(--color-surface)",
    color: "var(--color-text-primary)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  deleteBtn: {
    padding: "9px 12px",
    borderRadius: 10,
    border: "1px solid rgba(239,68,68,0.18)",
    background: "rgba(239,68,68,0.08)",
    color: "var(--color-rose)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.38)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    zIndex: 40,
  },
  modal: {
    width: "min(560px, 100%)",
    background: "var(--color-surface)",
    borderRadius: 22,
    padding: 24,
    boxShadow: "var(--shadow-lg)",
    border: "1px solid var(--color-border)",
  },
  modalTitle: {
    margin: 0,
    fontFamily: "var(--font-display)",
    fontSize: 24,
    letterSpacing: "-0.02em",
    color: "var(--color-text-primary)",
  },
  modalSubtitle: {
    margin: "10px 0 0",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--color-text-secondary)",
  },
  form: {
    marginTop: 18,
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--color-text-primary)",
  },
  input: {
    width: "100%",
    padding: "11px 12px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    fontSize: 14,
    background: "var(--color-bg)",
  },
  textarea: {
    width: "100%",
    minHeight: 112,
    padding: "11px 12px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    fontSize: 14,
    background: "var(--color-bg)",
    resize: "vertical",
    fontFamily: "inherit",
  },
  select: {
    padding: "11px 12px",
    borderRadius: 12,
    border: "1px solid var(--color-border)",
    fontSize: 14,
    background: "var(--color-surface)",
    color: "var(--color-text-primary)",
  },
  errorBox: {
    padding: "10px 12px",
    borderRadius: 12,
    background: "rgba(239,68,68,0.08)",
    border: "1px solid rgba(239,68,68,0.16)",
    color: "var(--color-rose)",
    fontSize: 13,
  },
  modalActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 10,
    flexWrap: "wrap",
    marginTop: 6,
  },
};
