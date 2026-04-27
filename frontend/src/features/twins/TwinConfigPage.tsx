/**
 * TwinConfigPage — owner controls for a twin.
 *
 * Sections:
 *  1. Identity      — display name, accent color
 *  2. Context       — custom system context for this twin
 *  3. Content Policy — code snippets opt-in
 *  4. Visibility    — public / private toggle
 *  5. Danger zone   — deactivate / delete twin
 *
 * Uses useTwin + useUpdateTwin + useUpdateTwinConfig mutations.
 * All changes are saved explicitly (not auto-saved) to keep the UX clear.
 */

import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useIsMobile } from "@/hooks/useIsMobile";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppShell from "@/components/AppShell";
import {
  useTwin,
  useUpdateTwin,
  useUpdateTwinConfig,
  useDeleteTwin,
  useMemoryBrief,
  useTriggerMemoryGeneration,
} from "@/hooks/useTwins";
import {
  useTwinShareSurfaces,
  useCreateTwinSharePage,
  useRevokeShareSurface,
} from "@/hooks/useSharing";

const ACCENT_PRESETS = [
  "#6366F1", // iris (default)
  "#14B8A6", // teal
  "#F59E0B", // amber
  "#F43F5E", // rose
  "#8B5CF6", // violet
  "#06B6D4", // cyan
  "#10B981", // emerald
  "#64748B", // slate
];

export default function TwinConfigPage() {
  const isMobile = useIsMobile();
  const { twinId } = useParams<{ twinId: string }>();
  const navigate = useNavigate();

  const { data: twin, isLoading } = useTwin(twinId ?? "");
  const updateTwin = useUpdateTwin();
  const updateConfig = useUpdateTwinConfig();
  const deleteTwin = useDeleteTwin();

  // Identity fields
  const [displayName, setDisplayName] = useState("");
  const [accentColor, setAccentColor] = useState("#6366F1");
  const [customHex, setCustomHex] = useState("");

  // Context
  const [customContext, setCustomContext] = useState("");

  // Policy
  // const [allowCodeSnippets, setAllowCodeSnippets] = useState(false);

  // Visibility
  const [isPublic, setIsPublic] = useState(false);

  // Saved / error state
  const [saving, setSaving] = useState(false);
  const [savedSection, setSavedSection] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Populate from loaded twin
  useEffect(() => {
    if (twin?.config) {
      setDisplayName(twin.config.display_name ?? twin.name ?? "");
      setAccentColor(twin.config.accent_color ?? "#6366F1");
      setCustomContext(twin.config.custom_context ?? "");
      // setAllowCodeSnippets(twin.config.allow_code_snippets ?? false);
      setIsPublic(twin.config.is_public ?? false);
    } else if (twin) {
      setDisplayName(twin.name);
    }
  }, [twin]);

  function markSaved(section: string) {
    setSavedSection(section);
    setTimeout(() => setSavedSection(null), 2500);
  }

  async function saveIdentity() {
    if (!twinId) return;
    const errs: Record<string, string> = {};

    if (!displayName.trim()) {
      errs.displayName = "Display name is required.";
    }

    const hexToValidate = customHex || accentColor;
    if (!/^#[0-9a-fA-F]{6}$/.test(hexToValidate)) {
      errs.accentColor = "Invalid hex color. Use format #RRGGBB.";
    }

    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }

    setErrors({});
    setSaving(true);
    try {
      await updateConfig.mutateAsync({
        twinId,
        display_name: displayName.trim(),
        accent_color: customHex || accentColor,
      });
      markSaved("identity");
    } catch {
      setErrors({ identity: "Failed to save. Please try again." });
    } finally {
      setSaving(false);
    }
  }

  async function saveContext() {
    if (!twinId) return;
    setSaving(true);
    try {
      await updateConfig.mutateAsync({
        twinId,
        custom_context: customContext.trim() || undefined,
      });
      markSaved("context");
    } catch {
      setErrors({ context: "Failed to save. Please try again." });
    } finally {
      setSaving(false);
    }
  }

  // async function savePolicy() {
  //   if (!twinId) return;
  //   setSaving(true);
  //   try {
  //     await updateConfig.mutateAsync({ twinId, allow_code_snippets: allowCodeSnippets });
  //     markSaved("policy");
  //   } catch {
  //     setErrors({ policy: "Failed to save. Please try again." });
  //   } finally {
  //     setSaving(false);
  //   }
  // }

  async function saveVisibility() {
    if (!twinId) return;
    setSaving(true);
    try {
      await updateConfig.mutateAsync({ twinId, is_public: isPublic });
      markSaved("visibility");
    } catch {
      setErrors({ visibility: "Failed to save. Please try again." });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!twin) return;
    const confirmed = window.confirm(
      `Delete "${twin.config?.display_name || twin.name}"? This cannot be undone. All sources and chat history will be permanently removed.`
    );
    if (!confirmed) return;

    try {
      await deleteTwin.mutateAsync({ twinId: twin.id, workspaceId: twin.workspace_id });
      navigate("/dashboard");
    } catch {
      setErrors({ danger: "Delete failed. Please try again." });
    }
  }

  async function handleDeactivate() {
    if (!twin) return;
    const isActive = twin.is_active;
    const action = isActive ? "deactivate" : "reactivate";
    if (!window.confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} this twin?`)) return;

    try {
      await updateTwin.mutateAsync({ twinId: twin.id, is_active: !isActive });
      markSaved("danger");
    } catch {
      setErrors({ danger: "Failed. Please try again." });
    }
  }

  if (isLoading || !twin) {
    return (
      <AppShell>
        <div style={s.loadingWrap}>
          <div style={s.spinner} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={{ ...s.page, padding: isMobile ? "68px 16px 48px" : s.page.padding }}>
        {/* ── Page header ───────────────────────────────────────────────── */}
        <div style={s.header}>
          <Link to={`/twin/${twin.id}`} style={s.backLink}>
            <IconArrowLeft />
            {twin.config?.display_name || twin.name}
          </Link>
          <h1 style={s.pageTitle}>Twin settings</h1>
          <p style={s.pageSubtitle}>
            Configure how this twin presents itself and what it's allowed to share.
          </p>
        </div>

        {/* ── Section: Identity ─────────────────────────────────────────── */}
        <Section title="Identity" saved={savedSection === "identity"}>
          <p style={s.sectionNote}>
            The display name and color are visible to anyone who interacts with this twin.
          </p>

          <div style={s.formGroup}>
            <label style={s.label}>Display name</label>
            <input
              style={{ ...s.input, ...(errors.displayName ? s.inputError : {}) }}
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g. Backend Bot"
              maxLength={80}
            />
            {errors.displayName && <p style={s.errorText}>{errors.displayName}</p>}
          </div>

          <div style={s.formGroup}>
            <label style={s.label}>Accent color</label>
            <div style={s.colorRow}>
              {ACCENT_PRESETS.map((hex) => (
                <button
                  key={hex}
                  style={{
                    ...s.colorSwatch,
                    background: hex,
                    outline: accentColor === hex && !customHex ? `3px solid ${hex}` : "none",
                    outlineOffset: 2,
                  }}
                  onClick={() => { setAccentColor(hex); setCustomHex(""); }}
                  title={hex}
                />
              ))}
              <input
                style={{ ...s.input, width: 120, fontFamily: "var(--font-mono)", fontSize: 13 }}
                type="text"
                placeholder="#RRGGBB"
                value={customHex}
                maxLength={7}
                onChange={(e) => {
                  const v = e.target.value;
                  setCustomHex(v);
                  if (/^#[0-9a-fA-F]{6}$/.test(v)) setAccentColor(v);
                }}
              />
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: customHex || accentColor,
                  border: "1px solid var(--color-border)",
                  flexShrink: 0,
                }}
              />
            </div>
            {errors.accentColor && <p style={s.errorText}>{errors.accentColor}</p>}
          </div>

          {errors.identity && <p style={s.errorText}>{errors.identity}</p>}
          <SaveButton onClick={saveIdentity} saving={saving} />
        </Section>

        {/* ── Section: Context ──────────────────────────────────────────── */}
        <Section title="Custom context" saved={savedSection === "context"}>
          <p style={s.sectionNote}>
            Provide background about this twin that shapes how it introduces itself and frames its answers. This is injected as system context — do not include sensitive information.
          </p>

          <div style={s.formGroup}>
            <label style={s.label}>System context</label>
            <textarea
              style={{ ...s.input, minHeight: 120, resize: "vertical" }}
              value={customContext}
              onChange={(e) => setCustomContext(e.target.value)}
              placeholder="e.g. This twin represents the docbase backend API. It can explain architectural decisions, API contracts, and dependency choices based on the connected repository."
              maxLength={2000}
            />
            <span style={s.charCount}>{customContext.length} / 2000</span>
          </div>

          {errors.context && <p style={s.errorText}>{errors.context}</p>}
          <SaveButton onClick={saveContext} saving={saving} />
        </Section>

        {/* ── Section: Content Policy ───────────────────────────────────── */}
        <Section title="Content policy" saved={savedSection === "policy"}>
          <p style={s.sectionNote}>
            These settings control what information the twin is allowed to include in answers. The always-blocked tier (secrets, credentials, private keys) cannot be changed.
          </p>

          <div style={s.policyTierTable}>
            <PolicyRow
              label="secrets, credentials"
              tier="Always blocked"
              tierColor="var(--color-rose)"
              locked
            />
            <PolicyRow
              label="Structure, docs, summaries, architecture"
              tier="Always available"
              tierColor="var(--color-teal)"
              locked
            />
            {/* <PolicyRow
              label="Code snippets (scoped sections, not full files)"
              tier={allowCodeSnippets ? "Enabled" : "Disabled"}
              tierColor={allowCodeSnippets ? "var(--color-iris)" : "var(--color-text-tertiary)"}
              toggle={
                <Toggle
                  on={allowCodeSnippets}
                  onChange={(v) => setAllowCodeSnippets(v)}
                />
              }
            /> */}
          </div>

          {errors.policy && <p style={s.errorText}>{errors.policy}</p>}
          {/* <SaveButton onClick={savePolicy} saving={saving} /> */}
        </Section>

        {/* ── Section: Visibility ───────────────────────────────────────── */}
        <Section title="Visibility" saved={savedSection === "visibility"}>
          <p style={s.sectionNote}>
            Public twins can be accessed via a shareable link. The content policy still applies — the twin will never expose blocked content regardless of visibility.
          </p>

          <div style={s.visibilityRow}>
            <div style={s.visibilityText}>
              <span style={s.visibilityLabel}>{isPublic ? "Public" : "Private"}</span>
              <span style={s.visibilityDesc}>
                {isPublic
                  ? "Anyone with the share link can chat with this twin."
                  : "Only you can access this twin. Share links are disabled."}
              </span>
            </div>
            <Toggle on={isPublic} onChange={setIsPublic} />
          </div>

          {errors.visibility && <p style={s.errorText}>{errors.visibility}</p>}
          <SaveButton onClick={saveVisibility} saving={saving} />

          {isPublic && <ShareLinksPanel twinId={twinId ?? ""} />}
        </Section>

        {/* ── Section: Knowledge Brief ───────────────────────────────── */}
        <KnowledgeBriefSection twinId={twinId ?? ""} />

        {/* ── Section: Danger zone ──────────────────────────────────────── */}
        <Section title="Danger zone" danger>
          <div style={s.dangerRow}>
            <div style={s.dangerRowText}>
              <span style={s.dangerRowLabel}>
                {twin.is_active ? "Deactivate twin" : "Reactivate twin"}
              </span>
              <span style={s.dangerRowDesc}>
                {twin.is_active
                  ? "Deactivating stops the twin from answering questions. Sources are preserved."
                  : "Reactivating makes the twin available again."}
              </span>
            </div>
            <button style={s.warningBtn} onClick={handleDeactivate}>
              {twin.is_active ? "Deactivate" : "Reactivate"}
            </button>
          </div>

          <div style={{ ...s.dangerRow, borderTop: "1px solid var(--color-border)", paddingTop: 16, marginTop: 8 }}>
            <div style={s.dangerRowText}>
              <span style={s.dangerRowLabel}>Delete twin</span>
              <span style={s.dangerRowDesc}>
                Permanently deletes this twin, all its sources, and all chat history. This cannot be undone.
              </span>
            </div>
            <button style={s.deleteBtn} onClick={handleDelete}>
              Delete twin
            </button>
          </div>

          {errors.danger && <p style={s.errorText}>{errors.danger}</p>}
        </Section>
      </div>
    </AppShell>
  );
}

// ─── Share Links panel ────────────────────────────────────────────────────────

function ShareLinksPanel({ twinId }: { twinId: string }) {
  const { data: surfaces = [], isLoading } = useTwinShareSurfaces(twinId);
  const createPage = useCreateTwinSharePage();
  const revoke = useRevokeShareSurface();
  const [copied, setCopied] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const pageLinks = surfaces.filter((s) => s.surface_type === "doctwin_page");

  function copyUrl(url: string, id: string) {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  return (
    <div style={sl.panel}>
      <div style={sl.header}>
        <span style={sl.panelTitle}>Share links</span>
        {pageLinks.length === 0 && (
          <button
            style={sl.generateBtn}
            disabled={createPage.isPending || isLoading}
            onClick={() => createPage.mutate(twinId)}
          >
            {createPage.isPending ? "Generating…" : "Generate link"}
          </button>
        )}
      </div>

      {createPage.isError && (
        <p style={sl.error}>Failed to generate link. It may already exist.</p>
      )}

      {isLoading && <p style={sl.hint}>Loading…</p>}

      {!isLoading && pageLinks.length === 0 && (
        <p style={sl.hint}>No share links yet. Generate one to make this twin publicly accessible.</p>
      )}

      {pageLinks.map((surface) => (
        <div key={surface.id} style={sl.linkRow}>
          <span style={sl.url}>{surface.public_url}</span>
          <div style={sl.actions}>
            <button
              style={sl.copyBtn}
              onClick={() => copyUrl(surface.public_url, surface.id)}
            >
              {copied === surface.id ? "✓ Copied" : "Copy"}
            </button>
            <button
              style={sl.revokeBtn}
              disabled={revoking === surface.id}
              onClick={() => {
                setRevoking(surface.id);
                revoke.mutate(
                  { surfaceId: surface.id, twinId },
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

const sl: Record<string, React.CSSProperties> = {
  panel: {
    marginTop: 16,
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    padding: "14px 16px",
    background: "var(--color-surface)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
  },
  panelTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  generateBtn: {
    fontSize: 12,
    padding: "5px 12px",
    borderRadius: 6,
    border: "1px solid var(--color-iris)",
    background: "var(--color-iris)",
    color: "#fff",
    cursor: "pointer",
  },
  hint: {
    fontSize: 12,
    color: "var(--color-text-secondary)",
    margin: 0,
  },
  error: {
    fontSize: 12,
    color: "var(--color-rose)",
    margin: "0 0 8px",
  },
  linkRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "8px 0",
    borderTop: "1px solid var(--color-border)",
  },
  url: {
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    color: "var(--color-text-primary)",
    wordBreak: "break-all",
    flex: 1,
  },
  actions: {
    display: "flex",
    gap: 6,
    flexShrink: 0,
  },
  copyBtn: {
    fontSize: 11,
    padding: "4px 10px",
    borderRadius: 5,
    border: "1px solid var(--color-border)",
    background: "none",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
  },
  revokeBtn: {
    fontSize: 11,
    padding: "4px 10px",
    borderRadius: 5,
    border: "1px solid var(--color-rose, #F43F5E)",
    background: "none",
    color: "var(--color-rose, #F43F5E)",
    cursor: "pointer",
  },
};

// ─── Knowledge Brief section ───────────────────────────────────────────────

function KnowledgeBriefSection({ twinId }: { twinId: string }) {
  const { data: brief, isLoading } = useMemoryBrief(twinId);
  const trigger = useTriggerMemoryGeneration();
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<string, string> = {
    ready: "var(--color-teal)",
    generating: "var(--color-iris)",
    pending: "var(--color-amber)",
    failed: "var(--color-rose)",
  };

  const statusLabel: Record<string, string> = {
    ready: "Ready",
    generating: "Generating…",
    pending: "Pending",
    failed: "Failed",
  };

  return (
    <Section title="Knowledge Brief">
      <p style={s.sectionNote}>
        The knowledge brief summarises document topics, coverage, and
        onboarding guidance from your sources. The generated brief is shown in the
        chat empty state and injected into every conversation as persistent context.
      </p>

      {isLoading ? (
        <div style={s.memLoadingRow}>
          <div style={s.spinnerXS} />
          <span style={{ fontSize: 13, color: "var(--color-text-tertiary)" }}>
            Loading…
          </span>
        </div>
      ) : (
        <div style={s.memStatusRow}>
          {/* Status badge */}
          <span
            style={{
              ...s.memStatusBadge,
              color: statusColors[brief?.status ?? ""] ?? "var(--color-text-tertiary)",
              background: (statusColors[brief?.status ?? ""] ?? "transparent") + "18",
            }}
          >
            {brief?.status === "generating" && (
              <span style={s.spinnerXS} />
            )}
            {statusLabel[brief?.status ?? ""] ?? "Not generated"}
          </span>

          {/* Timestamp */}
          {brief?.generated_at && (
            <span style={s.memTimestamp}>
              Last generated {new Date(brief.generated_at).toLocaleDateString()}
            </span>
          )}

          {/* Action button */}
          <button
            style={s.memRegenerateBtn}
            onClick={() => trigger.mutate(twinId)}
            disabled={trigger.isPending || brief?.status === "generating"}
          >
            {trigger.isPending
              ? "Queued…"
              : brief?.status === "ready"
              ? "Regenerate"
              : "Generate Knowledge Brief"}
          </button>
        </div>
      )}

      {/* Expandable brief preview */}
      {brief?.brief && (
        <div style={s.memPreviewWrap}>
          <button
            style={s.memExpandBtn}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Hide preview" : "Show preview"}
          </button>
          {expanded && (
            <div style={s.memPreviewContent}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {brief.brief}
              </ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Section({
  title,
  children,
  saved,
  danger,
}: {
  title: string;
  children: React.ReactNode;
  saved?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      style={{
        ...s.section,
        ...(danger
          ? { borderColor: "rgba(244,63,94,0.25)", background: "rgba(244,63,94,0.03)" }
          : {}),
      }}
    >
      <div style={s.sectionHeader}>
        <h2 style={{ ...s.sectionTitle, color: danger ? "var(--color-rose)" : "var(--color-text-primary)" }}>
          {title}
        </h2>
        {saved && (
          <span style={s.savedBadge}>
            <IconCheck /> Saved
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

function PolicyRow({
  label,
  tier,
  tierColor,
  locked,
  toggle,
}: {
  label: string;
  tier: string;
  tierColor: string;
  locked?: boolean;
  toggle?: React.ReactNode;
}) {
  return (
    <div style={s.policyRow}>
      <span style={s.policyLabel}>{label}</span>
      <div style={s.policyRight}>
        <span style={{ ...s.policyTier, color: tierColor }}>{tier}</span>
        {locked && <span style={s.lockIcon}><IconLock /></span>}
        {toggle}
      </div>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      style={{
        ...s.toggle,
        background: on ? "var(--color-iris)" : "var(--color-border)",
      }}
      onClick={() => onChange(!on)}
    >
      <span
        style={{
          ...s.toggleThumb,
          transform: on ? "translateX(2px)" : "translateX(-18px)",
        }}
      />
    </button>
  );
}

function SaveButton({ onClick, saving }: { onClick: () => void; saving: boolean }) {
  return (
    <button
      style={{ ...s.saveBtn, opacity: saving ? 0.7 : 1 }}
      onClick={onClick}
      disabled={saving}
    >
      {saving ? "Saving…" : "Save changes"}
    </button>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function IconArrowLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function IconLock() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  page: {
    maxWidth: 660,
    margin: "0 auto",
    padding: "40px 32px 80px",
    fontFamily: "var(--font-body)",
    display: "flex",
    flexDirection: "column",
    gap: 24,
  },

  // Header
  header: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    marginBottom: 8,
  },
  backLink: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    fontSize: 13,
    color: "var(--color-text-secondary)",
    textDecoration: "none",
    marginBottom: 6,
  },
  pageTitle: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: 22,
    color: "var(--color-text-primary)",
    margin: 0,
  },
  pageSubtitle: {
    fontSize: 14,
    color: "var(--color-text-secondary)",
    margin: 0,
    lineHeight: 1.5,
  },

  // Sections
  section: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 12,
    padding: "22px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  sectionTitle: {
    fontFamily: "var(--font-display)",
    fontWeight: 700,
    fontSize: 15,
    margin: 0,
  },
  sectionNote: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    lineHeight: 1.6,
    margin: 0,
  },
  savedBadge: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    fontSize: 12,
    color: "var(--color-teal)",
    fontWeight: 600,
  },

  // Form elements
  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  input: {
    padding: "9px 12px",
    borderRadius: 8,
    border: "1px solid var(--color-border)",
    background: "var(--color-bg)",
    color: "var(--color-text-primary)",
    fontFamily: "var(--font-body)",
    fontSize: 14,
    outline: "none",
    width: "100%",
    boxSizing: "border-box" as const,
  },
  inputError: {
    borderColor: "var(--color-rose)",
  },
  charCount: {
    fontSize: 11,
    color: "var(--color-text-tertiary)",
    textAlign: "right" as const,
  },
  errorText: {
    fontSize: 12,
    color: "var(--color-rose)",
    margin: 0,
  },
  saveBtn: {
    alignSelf: "flex-end",
    padding: "8px 18px",
    background: "var(--color-iris)",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontFamily: "var(--font-body)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },

  // Color picker
  colorRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap" as const,
  },
  colorSwatch: {
    width: 28,
    height: 28,
    borderRadius: 6,
    border: "none",
    cursor: "pointer",
    flexShrink: 0,
  },

  // Policy table
  policyTierTable: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    overflow: "hidden",
  },
  policyRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "12px 14px",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-surface)",
  },
  policyLabel: {
    fontSize: 13,
    color: "var(--color-text-primary)",
    flex: 1,
  },
  policyRight: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
  },
  policyTier: {
    fontSize: 12,
    fontWeight: 600,
  },
  lockIcon: {
    color: "var(--color-text-tertiary)",
    display: "flex",
    alignItems: "center",
  },

  // Toggle
  toggle: {
    width: 40,
    height: 22,
    borderRadius: 11,
    border: "none",
    cursor: "pointer",
    position: "relative" as const,
    transition: "background 0.15s",
    flexShrink: 0,
  },
  toggleThumb: {
    position: "absolute" as const,
    top: 3,
    width: 16,
    height: 16,
    borderRadius: "50%",
    background: "#fff",
    transition: "transform 0.15s",
    boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
  },

  // Visibility
  visibilityRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
  },
  visibilityText: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    flex: 1,
  },
  visibilityLabel: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  visibilityDesc: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    lineHeight: 1.4,
  },
  shareHint: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 12,
    color: "var(--color-text-secondary)",
    background: "var(--color-bg)",
    padding: "8px 12px",
    borderRadius: 6,
  },

  // Danger zone
  dangerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
  },
  dangerRowText: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    flex: 1,
  },
  dangerRowLabel: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--color-text-primary)",
  },
  dangerRowDesc: {
    fontSize: 13,
    color: "var(--color-text-secondary)",
    lineHeight: 1.4,
  },
  warningBtn: {
    padding: "8px 16px",
    background: "transparent",
    border: "1px solid var(--color-amber)",
    color: "var(--color-amber)",
    borderRadius: 8,
    fontFamily: "var(--font-body)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
  deleteBtn: {
    padding: "8px 16px",
    background: "transparent",
    border: "1px solid var(--color-rose)",
    color: "var(--color-rose)",
    borderRadius: 8,
    fontFamily: "var(--font-body)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },

  // Knowledge Brief section
  memLoadingRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  memStatusRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap" as const,
  },
  memStatusBadge: {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    fontSize: 12,
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: 20,
  },
  memTimestamp: {
    fontSize: 12,
    color: "var(--color-text-tertiary)",
    flex: 1,
  },
  memRegenerateBtn: {
    padding: "6px 14px",
    background: "var(--color-iris)",
    border: "none",
    borderRadius: 7,
    color: "#fff",
    fontFamily: "var(--font-body)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
  memPreviewWrap: {
    marginTop: 12,
    borderTop: "1px solid var(--color-border)",
    paddingTop: 12,
  },
  memExpandBtn: {
    background: "none",
    border: "1px solid var(--color-border)",
    borderRadius: 6,
    padding: "4px 12px",
    fontSize: 12,
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    fontFamily: "inherit",
    marginBottom: 10,
  },
  memPreviewContent: {
    fontSize: 13,
    lineHeight: 1.65,
    color: "var(--color-text-primary)",
    background: "var(--color-bg)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    padding: "16px 20px",
    maxHeight: 400,
    overflowY: "auto" as const,
  },
  spinnerXS: {
    display: "inline-block",
    width: 12,
    height: 12,
    borderRadius: "50%",
    border: "2px solid var(--color-border)",
    borderTopColor: "var(--color-iris)",
    animation: "spin 0.7s linear infinite",
    flexShrink: 0,
  },

  // Loading
  loadingWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
  },
  spinner: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    border: "3px solid var(--color-border)",
    borderTopColor: "var(--color-iris)",
    animation: "spin 0.7s linear infinite",
  },
};
