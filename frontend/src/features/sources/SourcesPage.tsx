/**
 * SourcesPage — manage knowledge sources attached to a twin.
 *
 * Google Drive OAuth: connect at /integrations, then pick files or folders here.
 * Markdown and manual sources use the paste flow; PDF uses upload.
 */

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { useTwin } from "@/hooks/useTwins";
import {
  useSources,
  useAttachSource,
  useBackfillLegacySources,
  useDetachSource,
  useTriggerSync,
  useUploadPdfSource,
} from "@/hooks/useSources";
import {
  useConnectedAccount,
  useAccountDriveFiles,
} from "@/hooks/useIntegrations";
import type { DriveFileItem, Source, SourceType } from "@/types";

// ─── Source type catalog ──────────────────────────────────────────────────────

type SourceFlow = "oauth_drive" | "text" | "pdf";

interface SourceTypeDef {
  value: SourceType;
  label: string;
  description: string;
  flow: SourceFlow;
  provider?: "google_drive";
  icon: React.ReactNode;
}

const SOURCE_TYPES: SourceTypeDef[] = [
  {
    value: "google_drive",
    label: "Google Drive",
    description: "Attach files or a folder from your Google Drive.",
    flow: "oauth_drive",
    provider: "google_drive",
    icon: <IconDrive />,
  },
  {
    value: "markdown",
    label: "Markdown",
    description: "Paste or upload Markdown documentation.",
    flow: "text",
    icon: <IconMarkdown />,
  },
  {
    value: "manual",
    label: "Manual Notes",
    description: "Add plain-text context — project descriptions, team notes, etc.",
    flow: "text",
    icon: <IconPencil />,
  },
  {
    value: "pdf",
    label: "PDF Document",
    description: "Upload a PDF resume, spec, or portfolio document.",
    flow: "pdf",
    icon: <IconPDF />,
  },
];

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  ready:        { label: "Ready",       color: "var(--color-teal)" },
  ingesting:    { label: "Ingesting…",  color: "var(--color-iris)" },
  processing:   { label: "Processing…", color: "var(--color-iris)" },
  pending:      { label: "Pending",     color: "var(--color-amber)" },
  failed:       { label: "Failed",      color: "var(--color-rose)" },
  needs_resync: { label: "Needs sync",  color: "var(--color-amber)" },
};

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SourcesPage() {
  const { twinId } = useParams<{ twinId: string }>();
  const { data: twin, isLoading: twinLoading } = useTwin(twinId ?? "");
  const { data: sources = [], isLoading: sourcesLoading } = useSources(twinId ?? "");
  const attachSource = useAttachSource();
  const backfillLegacySources = useBackfillLegacySources();
  const detachSource = useDetachSource();
  const triggerSync = useTriggerSync();
  const uploadPdfSource = useUploadPdfSource();

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [addingSource, setAddingSource] = useState(false);
  const [selectedType, setSelectedType] = useState<SourceTypeDef | null>(null);
  const [formName, setFormName] = useState("");
  const [formText, setFormText] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);

  const [pickedDriveFile, setPickedDriveFile] = useState<DriveFileItem | null>(null);
  const [pickedDriveAccountId, setPickedDriveAccountId] = useState<string>("");

  function resetModal() {
    setAddingSource(false);
    setSelectedType(null);
    setFormName("");
    setFormText("");
    setFormError(null);
    setPdfFile(null);
    setPickedDriveFile(null);
    setPickedDriveAccountId("");
  }

  async function handleSubmit() {
    if (!selectedType || !formName.trim()) {
      setFormError("Please give this source a name.");
      return;
    }
    setFormError(null);

    let connection_config: Record<string, string> = {};
    let connected_account_id: string | undefined;

    const flow = selectedType.flow;

    if (flow === "oauth_drive") {
      if (!pickedDriveFile) { setFormError("Select a file or folder first."); return; }
      if (!pickedDriveAccountId) { setFormError("Account ID missing — please reconnect Google Drive."); return; }
      // Folders get listed recursively; individual files are fetched directly.
      const isFolder = pickedDriveFile.mime_type === "application/vnd.google-apps.folder";
      connection_config = isFolder
        ? { folder_id: pickedDriveFile.id }
        : { file_id: pickedDriveFile.id };
      connected_account_id = pickedDriveAccountId;
    } else if (flow === "text") {
      if (!formText.trim()) { setFormError("Content cannot be empty."); return; }
      connection_config = { content: formText.trim(), title: formName.trim() };
    } else if (flow === "pdf") {
      if (!pdfFile) { setFormError("Please select a PDF file."); return; }
      if (!pdfFile.name.toLowerCase().endsWith(".pdf")) {
        setFormError("Only PDF files are accepted.");
        return;
      }
      const MAX_PDF = 20 * 1024 * 1024;
      if (pdfFile.size > MAX_PDF) {
        setFormError("PDF exceeds the 20 MB limit.");
        return;
      }
      try {
        await uploadPdfSource.mutateAsync({
          twinId: twinId!,
          name: formName.trim(),
          file: pdfFile,
        });
        resetModal();
      } catch (err: unknown) {
        const detail =
          (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
        setFormError(typeof detail === "string" ? detail : "Failed to upload PDF.");
      }
      return;
    }

    try {
      await attachSource.mutateAsync({
        twinId: twinId!,
        name: formName.trim(),
        source_type: selectedType.value,
        connection_config,
        connected_account_id,
      });
      resetModal();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setFormError(typeof detail === "string" ? detail : "Failed to add source.");
    }
  }

  function handleRemoveSource(sourceId: string) {
    if (!confirm("Remove this source? Ingested knowledge will no longer be available to this twin."))
      return;
    setDeletingId(sourceId);
    detachSource.mutate(
      { sourceId, twinId: twinId! },
      { onSettled: () => setDeletingId(null) },
    );
  }

  const legacySources = sources.filter((source) => source.index_mode === "legacy");
  const staleSources = sources.filter((source) => source.index_health?.freshness?.is_stale);
  const strictSources = sources.filter((source) => source.index_mode === "strict");
  const parserCoverageValues = sources
    .map((source) => source.index_health?.implementation_index?.parser_coverage_percent)
    .filter((value): value is number => typeof value === "number");
  const averageParserCoverage = parserCoverageValues.length
    ? Math.round(
        parserCoverageValues.reduce((sum, value) => sum + value, 0) / parserCoverageValues.length
      )
    : null;

  if (twinLoading || sourcesLoading || !twin) {
    return (
      <AppShell>
        <div style={s.loadingWrap}><div style={s.spinner} /></div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={s.page}>
        {/* Header */}
        <div style={s.header}>
          <div style={s.headerLeft}>
            <Link to={`/twin/${twin.id}`} style={s.backLink}><IconArrowLeft /> {twin.config?.display_name || twin.name}</Link>
            <h1 style={s.pageTitle}>Sources</h1>
            <p style={s.pageSubtitle}>
              Manage the knowledge sources this twin draws from. All sources sync automatically.
            </p>
          </div>
          <div style={s.headerActions}>
            {legacySources.length > 0 && (
              <button
                style={s.secondaryBtn}
                onClick={() => backfillLegacySources.mutate({ twinId: twinId! })}
                disabled={backfillLegacySources.isPending}
              >
                {backfillLegacySources.isPending ? "Upgrading…" : `Upgrade legacy indexes (${legacySources.length})`}
              </button>
            )}
            <button style={s.primaryBtn} onClick={() => setAddingSource(true)}>+ Add source</button>
          </div>
        </div>

        {/* Policy banner */}
        <div style={s.policyBanner}>
          <IconShield />
          <span>
            All ingested content passes through the safety policy. Secrets and credentials are always blocked.
            Code snippets are opt-in per twin.
          </span>
        </div>

        {legacySources.length > 0 && (
          <div style={s.legacyBanner}>
            <IconAlert />
            <span>
              {legacySources.length} source{legacySources.length === 1 ? "" : "s"} still use the legacy evidence contract.
              Upgrade them to enable stricter snapshot-backed answers.
            </span>
          </div>
        )}

        {sources.length > 0 && (
          <div style={s.summaryGrid}>
            <SummaryCard
              label="Trust mode"
              value={`${strictSources.length}/${sources.length}`}
              detail={`${legacySources.length} legacy source${legacySources.length === 1 ? "" : "s"}`}
              tone={legacySources.length > 0 ? "amber" : "teal"}
            />
            <SummaryCard
              label="Freshness"
              value={staleSources.length > 0 ? `${staleSources.length} stale` : "All fresh"}
              detail={`${sources.length - staleSources.length} source${sources.length - staleSources.length === 1 ? "" : "s"} within budget`}
              tone={staleSources.length > 0 ? "rose" : "teal"}
            />
            <SummaryCard
              label="Parser coverage"
              value={averageParserCoverage !== null ? `${averageParserCoverage}%` : "N/A"}
              detail={
                parserCoverageValues.length > 0
                  ? `${parserCoverageValues.length} source${parserCoverageValues.length === 1 ? "" : "s"} with parser stats`
                  : "No parser stats on sources yet"
              }
              tone="iris"
            />
          </div>
        )}

        {/* Sources list */}
        <div style={s.content}>
          {sources.length === 0 ? (
            <EmptyState onAdd={() => setAddingSource(true)} />
          ) : (
            <div style={s.sourceGrid}>
              {sources.map((src) => (
                <SourceCard
                  key={src.id}
                  source={src}
                  isDeleting={deletingId === src.id}
                  onRemove={() => handleRemoveSource(src.id)}
                  onResync={() => triggerSync.mutate({ sourceId: src.id, twinId: twinId! })}
                />
              ))}
            </div>
          )}
        </div>

        {/* Modal */}
        {addingSource && (
          <Modal onClose={resetModal}>
            <h2 style={s.modalTitle}>Add a source</h2>

            {!selectedType ? (
              <TypePicker onPick={(t) => { setSelectedType(t); setFormError(null); }} />
            ) : (
              <SourceForm
                typeDef={selectedType}
                formName={formName}
                formText={formText}
                formError={formError}
                pdfFile={pdfFile}
                pickedDriveFile={pickedDriveFile}
                onNameChange={setFormName}
                onTextChange={setFormText}
                onPdfFileChange={setPdfFile}
                onPickDriveFile={(f, accountId) => { setPickedDriveFile(f); setPickedDriveAccountId(accountId); }}
                onBack={() => {
                  setSelectedType(null); setFormError(null);
                  setPdfFile(null);
                  setPickedDriveFile(null); setPickedDriveAccountId("");
                }}
                onSubmit={handleSubmit}
                onCancel={resetModal}
                isSubmitting={attachSource.isPending || uploadPdfSource.isPending}
              />
            )}
          </Modal>
        )}
      </div>
    </AppShell>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: "teal" | "amber" | "rose" | "iris";
}) {
  const colorMap = {
    teal: "var(--color-teal)",
    amber: "var(--color-amber)",
    rose: "var(--color-rose)",
    iris: "var(--color-iris)",
  } as const;
  const color = colorMap[tone];

  return (
    <div style={s.summaryCard}>
      <span style={s.summaryLabel}>{label}</span>
      <span style={{ ...s.summaryValue, color }}>{value}</span>
      <span style={s.summaryDetail}>{detail}</span>
    </div>
  );
}

// ─── TypePicker ───────────────────────────────────────────────────────────────

function TypePicker({ onPick }: { onPick: (t: SourceTypeDef) => void }) {
  return (
    <div style={s.typeGrid}>
      {SOURCE_TYPES.map((t) => (
        <button key={t.value} style={s.typeCard} onClick={() => onPick(t)}>
          <span style={s.typeIcon}>{t.icon}</span>
          <span style={s.typeLabel}>{t.label}</span>
          <span style={s.typeDesc}>{t.description}</span>
        </button>
      ))}
    </div>
  );
}

// ─── SourceForm ───────────────────────────────────────────────────────────────

function SourceForm({
  typeDef,
  formName,
  formText,
  formError,
  pdfFile,
  pickedDriveFile,
  onNameChange,
  onTextChange,
  onPdfFileChange,
  onPickDriveFile,
  onBack,
  onSubmit,
  onCancel,
  isSubmitting,
}: {
  typeDef: SourceTypeDef;
  formName: string;
  formText: string;
  formError: string | null;
  pdfFile: File | null;
  pickedDriveFile: DriveFileItem | null;
  onNameChange: (v: string) => void;
  onTextChange: (v: string) => void;
  onPdfFileChange: (f: File | null) => void;
  onPickDriveFile: (f: DriveFileItem | null, accountId: string) => void;
  onBack: () => void;
  onSubmit: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  return (
    <div style={s.formBody}>
      <button style={s.typeBackBtn} onClick={onBack}>
        <IconArrowLeft /> {typeDef.label} — change
      </button>

      {/* Name */}
      <div style={s.formGroup}>
        <label style={s.label}>Source name</label>
        <input
          style={s.input}
          type="text"
          placeholder="e.g. Main backend repo"
          value={formName}
          onChange={(e) => onNameChange(e.target.value)}
          autoFocus
        />
      </div>

      {/* Provider-specific content */}
      {typeDef.flow === "oauth_drive" && (
        <DriveSelector
          picked={pickedDriveFile}
          onPick={(f, accountId) => {
            onPickDriveFile(f, accountId);
            if (f && !formName) onNameChange(f.name);
          }}
        />
      )}

      {typeDef.flow === "text" && (
        <div style={s.formGroup}>
          <label style={s.label}>Content</label>
          <textarea
            style={{ ...s.input, minHeight: 130, resize: "vertical" }}
            placeholder={typeDef.value === "markdown" ? "Paste Markdown here…" : "Paste plain-text notes here…"}
            value={formText}
            onChange={(e) => onTextChange(e.target.value)}
          />
        </div>
      )}

      {typeDef.flow === "pdf" && (
        <div style={s.formGroup}>
          <label style={s.label}>PDF file</label>
          {pdfFile ? (
            <div style={s.fileSelected}>
              <span style={s.fileSelectedIcon}><IconPDF /></span>
              <div style={s.fileSelectedMeta}>
                <span style={s.fileSelectedName}>{pdfFile.name}</span>
                <span style={s.fileSelectedSize}>
                  {(pdfFile.size / 1024 / 1024).toFixed(2)} MB
                </span>
              </div>
              <button
                style={s.pickedClear}
                type="button"
                onClick={() => onPdfFileChange(null)}
                title="Remove file"
              >
                ✕
              </button>
            </div>
          ) : (
            <label style={s.filePickerLabel}>
              <input
                type="file"
                accept=".pdf,application/pdf"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  onPdfFileChange(f);
                  // Auto-fill name from filename if name is blank
                  if (f && !formName) {
                    onNameChange(f.name.replace(/\.pdf$/i, ""));
                  }
                }}
              />
              <span style={s.filePickerIcon}><IconPDF /></span>
              <span style={s.filePickerText}>Click to choose a PDF</span>
              <span style={s.fileInputHint}>Max 20 MB · PDF only</span>
            </label>
          )}
        </div>
      )}

      {formError && <p style={s.formError}>{formError}</p>}

      <div style={s.formActions}>
        <button style={s.cancelBtn} onClick={onCancel}>Cancel</button>
        <button
          style={{ ...s.primaryBtn, opacity: isSubmitting ? 0.7 : 1 }}
          onClick={onSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? "Adding…" : "Add source"}
        </button>
      </div>
    </div>
  );
}

// ─── DriveSelector ────────────────────────────────────────────────────────────

const GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder";

function DriveSelector({
  picked,
  onPick,
}: {
  picked: DriveFileItem | null;
  onPick: (f: DriveFileItem | null, accountId: string) => void;
}) {
  const { account, isLoading: accountLoading } = useConnectedAccount("google_drive");

  // Breadcrumb stack: each entry is { id, name }. Empty = root.
  const [breadcrumbs, setBreadcrumbs] = useState<{ id: string; name: string }[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const currentFolderId = breadcrumbs.length > 0 ? breadcrumbs[breadcrumbs.length - 1].id : undefined;

  const { data: files = [], isLoading: filesLoading } = useAccountDriveFiles(
    account?.id,
    currentFolderId,
  );

  if (accountLoading) {
    return <div style={s.browserPlaceholder}><div style={s.spinnerSm} /></div>;
  }

  if (!account) {
    return (
      <div style={s.connectPrompt}>
        <div style={s.connectPromptIcon}><IconDrive /></div>
        <div>
          <div style={s.connectPromptTitle}>Connect Google Drive first</div>
          <p style={s.connectPromptBody}>
            Authorize docbase to read from your Drive. Only files you explicitly
            attach are ingested — no broad access.
          </p>
          <Link to="/integrations" style={{ ...s.primaryBtn, textDecoration: "none" }}>
            Connect Google Drive →
          </Link>
        </div>
      </div>
    );
  }

  if (picked) {
    return (
      <div style={s.formGroup}>
        <label style={s.label}>Selected</label>
        <div style={s.pickedItem}>
          <span style={s.pickedItemName}>
            {picked.mime_type === GDRIVE_FOLDER_MIME ? "📁 " : "📄 "}
            {picked.name}
          </span>
          <button style={s.pickedClear} onClick={() => onPick(null, "")}>✕</button>
        </div>
      </div>
    );
  }

  function enterFolder(folder: DriveFileItem) {
    setBreadcrumbs((prev) => [...prev, { id: folder.id, name: folder.name }]);
    setSearchQuery("");
  }

  function navigateTo(index: number) {
    // -1 = root, 0..n = breadcrumb index
    setBreadcrumbs((prev) => index < 0 ? [] : prev.slice(0, index + 1));
    setSearchQuery("");
  }

  const visibleFiles = searchQuery.trim()
    ? files.filter((f) => f.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : files;

  return (
    <div style={s.formGroup}>
      <label style={s.label}>
        File or Folder
        <span style={s.accountTag}> · {account.provider_username ?? "connected"}</span>
      </label>

      {/* Search */}
      <input
        style={{ ...s.input, marginBottom: 6 }}
        type="text"
        placeholder="Search files…"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
      />

      {/* Breadcrumb trail */}
      <div style={s.driveBreadcrumbs}>
        <button style={s.driveCrumb} onClick={() => navigateTo(-1)}>My Drive</button>
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={s.driveCrumbSep}>›</span>
            <button style={s.driveCrumb} onClick={() => navigateTo(i)}>{crumb.name}</button>
          </span>
        ))}
      </div>

      <div style={s.browser}>
        {filesLoading ? (
          <div style={s.browserCenter}><div style={s.spinnerSm} /></div>
        ) : visibleFiles.length === 0 ? (
          <div style={s.browserCenter}>
            {searchQuery.trim() ? `No files matching "${searchQuery}"` : "This folder is empty."}
          </div>
        ) : (
          visibleFiles.map((f) => {
            const isFolder = f.mime_type === GDRIVE_FOLDER_MIME;
            return (
              <div key={f.id} style={s.driveRow}>
                <button
                  style={{ ...s.browserItem, flex: 1, borderBottom: "none" }}
                  onClick={() => {
                    if (isFolder) {
                      enterFolder(f);
                    } else {
                      onPick(f, account.id);
                    }
                  }}
                >
                  <div style={s.browserItemMain}>
                    <span style={{ marginRight: 6, opacity: 0.7 }}>{isFolder ? "📁" : "📄"}</span>
                    <span style={s.browserItemName}>{f.name}</span>
                  </div>
                  <span style={s.browserItemDesc}>{_driveMimeLabel(f.mime_type)}</span>
                </button>
                {/* Folders get a "Select folder" button so the user can attach the folder itself */}
                {isFolder && (
                  <button
                    style={s.driveSelectFolderBtn}
                    title="Attach this folder (ingests all files inside)"
                    onClick={() => onPick(f, account.id)}
                  >
                    Select
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ─── SourceCard ───────────────────────────────────────────────────────────────

function SourceCard({
  source,
  isDeleting,
  onRemove,
  onResync,
}: {
  source: Source;
  isDeleting: boolean;
  onRemove: () => void;
  onResync: () => void;
}) {
  const status = STATUS_CONFIG[source.status] ?? { label: source.status, color: "var(--color-text-tertiary)" };
  const typeDef = SOURCE_TYPES.find((t) => t.value === source.source_type);
  const indexModeColor =
    source.index_mode === "strict" ? "var(--color-teal)" : "var(--color-amber)";
  const snapshotLabel = source.snapshot_id
    ? source.snapshot_id.startsWith("hash:")
      ? source.snapshot_id.slice(5, 17)
      : source.snapshot_id.slice(0, 12)
    : null;
  const legacyReason = source.index_health?.legacy_reasons?.[0] ?? null;
  const freshness = source.index_health?.freshness;
  const parserCoverage = source.index_health?.implementation_index?.parser_coverage_percent;
  const parserSupported = source.index_health?.implementation_index?.parser_supported_files ?? 0;
  const codeFiles = source.index_health?.implementation_index?.code_files_indexed ?? 0;
  const implementationFiles = source.index_health?.implementation_index?.files_indexed ?? 0;
  const implementationSymbols = source.index_health?.implementation_index?.symbols_indexed ?? 0;
  const implementationRelationships = source.index_health?.implementation_index?.relationships_indexed ?? 0;
  const freshnessColor = freshness?.is_stale ? "var(--color-rose)" : "var(--color-teal)";
  const freshnessLabel = freshness?.label ?? "Unknown";

  return (
    <div style={{ ...s.sourceCard, ...(isDeleting ? { opacity: 0.5, pointerEvents: "none" } : {}) }}>
      <div style={s.sourceCardTop}>
        <div style={s.sourceCardIcon}>{typeDef?.icon ?? <IconGlobe />}</div>
        <div style={s.sourceCardMeta}>
          <span style={s.sourceCardName}>{source.name}</span>
          <span style={s.sourceCardType}>{typeDef?.label ?? source.source_type}</span>
        </div>
        {isDeleting ? (
          <div style={{ ...s.statusBadge, color: "var(--color-rose)", background: "var(--color-rose)18" }}>
            <span style={s.spinnerSm} />
            Removing…
          </div>
        ) : (
          <div style={{ ...s.statusBadge, color: status.color, background: `${status.color}18` }}>
            <span style={{ ...s.statusDot, background: status.color }} />
            {status.label}
          </div>
        )}
      </div>

      {source.last_error && !isDeleting && (
        <div style={s.errorNote}><IconAlert /> {source.last_error}</div>
      )}

      {!isDeleting && (
        <div style={s.healthPanel}>
          <div style={s.healthRow}>
            <span style={s.healthLabel}>Evidence mode</span>
            <span style={{ ...s.modeBadge, color: indexModeColor, background: `${indexModeColor}18` }}>
              {source.index_mode === "strict" ? "Strict evidence" : "Legacy index"}
            </span>
          </div>
          {snapshotLabel && (
            <div style={s.healthRow}>
              <span style={s.healthLabel}>Snapshot</span>
              <code style={s.inlineCode}>{snapshotLabel}</code>
            </div>
          )}
          <div style={s.healthRow}>
            <span style={s.healthLabel}>Freshness</span>
            <span style={{ ...s.modeBadge, color: freshnessColor, background: `${freshnessColor}18` }}>
              {freshnessLabel}
            </span>
          </div>
          {freshness?.last_indexed_at && (
            <div style={s.healthRow}>
              <span style={s.healthLabel}>Last indexed</span>
              <span style={s.healthValue}>{formatFreshnessAge(freshness.age_minutes)}</span>
            </div>
          )}
          <div style={s.healthRow}>
            <span style={s.healthLabel}>Coverage</span>
            <span style={s.healthValue}>
              {source.index_health?.contract?.strict_chunk_ready ?? 0}/
              {source.index_health?.contract?.strict_chunk_total ?? 0} strict-ready chunks
            </span>
          </div>
          <div style={s.healthRow}>
            <span style={s.healthLabel}>Parser coverage</span>
            <span style={s.healthValue}>
              {parserCoverage !== undefined ? `${parserCoverage}%` : "N/A"}
              {codeFiles > 0 ? ` (${parserSupported}/${codeFiles} code files)` : ""}
            </span>
          </div>
          <div style={s.healthRow}>
            <span style={s.healthLabel}>Implementation</span>
            <span style={s.healthValue}>
              {implementationFiles} files • {implementationSymbols} symbols • {implementationRelationships} edges
            </span>
          </div>
          {legacyReason && (
            <div style={s.healthNote}>
              {legacyReason}
            </div>
          )}
          {freshness?.reason && !legacyReason && (
            <div style={s.healthNote}>
              {freshness.reason}
            </div>
          )}
        </div>
      )}

      <div style={s.sourceCardActions}>
        {!["ingesting", "processing"].includes(source.status) && !isDeleting && (
          <button style={s.ghostBtn} onClick={onResync}><IconRefresh /> Re-sync</button>
        )}
        <button
          style={{ ...s.ghostBtn, color: "var(--color-rose)" }}
          disabled={isDeleting}
          onClick={onRemove}
        >
          <IconTrash /> {isDeleting ? "Removing…" : "Remove"}
        </button>
      </div>
    </div>
  );
}

// ─── EmptyState / Modal ───────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div style={s.emptyState}>
      <div style={s.emptyOrb}><IconDatabase /></div>
      <h2 style={s.emptyTitle}>No sources yet</h2>
      <p style={s.emptyBody}>
        Connect a repository, Drive folder, or paste text content. Your twin
        will answer questions from what you connect here — nothing else.
      </p>
      <button style={s.primaryBtn} onClick={onAdd}>Add first source</button>
    </div>
  );
}

function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={s.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={s.modal}>
        <button style={s.modalClose} onClick={onClose}>×</button>
        {children}
      </div>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Hoisted to module level — object is created once, not on every call.
const DRIVE_MIME_LABELS: Record<string, string> = {
  "application/vnd.google-apps.document": "Google Doc",
  "application/vnd.google-apps.spreadsheet": "Google Sheet",
  "application/vnd.google-apps.presentation": "Google Slides",
  "text/plain": "Plain text",
  "text/markdown": "Markdown",
  "application/pdf": "PDF",
};

function _driveMimeLabel(mime: string): string {
  return DRIVE_MIME_LABELS[mime] ?? mime.split("/")[1] ?? mime;
}

function formatFreshnessAge(ageMinutes?: number | null): string {
  if (ageMinutes == null) return "Unknown";
  if (ageMinutes < 60) return `${ageMinutes} min ago`;
  const hours = Math.floor(ageMinutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function IconDrive() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M7.71 3.5L1.15 15l3.43 5.96L10.14 9.5 7.71 3.5zm8.58 0L13.86 9.5l5.56 11.46 3.43-5.96L16.29 3.5zm-8.58 0h8.58L12 9.5l-3.87-6zM1.15 15l3.43 5.96h14.84L22.85 15H1.15z" />
    </svg>
  );
}

function IconGlobe() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function IconMarkdown() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

function IconPDF() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <path d="M9 15v-4" /><path d="M12 15v-6" /><path d="M15 15v-2" />
    </svg>
  );
}

function IconPencil() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function IconArrowLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  );
}

function IconDatabase() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function IconRefresh() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  );
}

function IconTrash() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function IconAlert() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  page: { maxWidth: 820, margin: "0 auto", padding: "40px 32px", fontFamily: "var(--font-body)" },
  header: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 24 },
  headerLeft: { display: "flex", flexDirection: "column", gap: 4 },
  headerActions: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" as const, justifyContent: "flex-end" },
  backLink: { display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--color-text-secondary)", textDecoration: "none", marginBottom: 6 },
  pageTitle: { fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 22, color: "var(--color-text-primary)", margin: 0 },
  pageSubtitle: { fontSize: 14, color: "var(--color-text-secondary)", margin: 0, lineHeight: 1.5, maxWidth: 480 },
  policyBanner: { display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 14px", background: "var(--color-iris-muted)", borderRadius: 8, fontSize: 13, color: "var(--color-iris)", marginBottom: 28, lineHeight: 1.5 },
  legacyBanner: { display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 14px", background: "rgba(245, 158, 11, 0.10)", border: "1px solid rgba(245, 158, 11, 0.24)", borderRadius: 8, fontSize: 13, color: "var(--color-amber)", margin: "-10px 0 24px", lineHeight: 1.5 },
  summaryGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, margin: "-8px 0 24px" },
  summaryCard: { display: "flex", flexDirection: "column", gap: 6, padding: "14px 16px", borderRadius: 12, border: "1px solid var(--color-border)", background: "var(--color-surface)", boxShadow: "0 8px 24px rgba(20,32,57,0.04)" },
  summaryLabel: { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--color-text-tertiary)" },
  summaryValue: { fontFamily: "var(--font-display)", fontSize: 24, fontWeight: 700 },
  summaryDetail: { fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.45 },
  content: { minHeight: 200 },
  sourceGrid: { display: "flex", flexDirection: "column", gap: 12 },
  sourceCard: { background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10 },
  sourceCardTop: { display: "flex", alignItems: "center", gap: 12 },
  sourceCardIcon: { width: 36, height: 36, borderRadius: 8, background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-secondary)", flexShrink: 0 },
  sourceCardMeta: { flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 },
  sourceCardName: { fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)" },
  sourceCardType: { fontSize: 12, color: "var(--color-text-tertiary)" },
  statusBadge: { display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, padding: "3px 8px", borderRadius: 6 },
  statusDot: { width: 6, height: 6, borderRadius: "50%", display: "inline-block" },
  errorNote: { display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-rose)", background: "rgba(244,63,94,0.06)", padding: "6px 10px", borderRadius: 6 },
  modeBadge: { display: "inline-flex", alignItems: "center", borderRadius: 999, padding: "4px 8px", fontSize: 11, fontWeight: 700, letterSpacing: "0.02em" },
  healthPanel: { display: "grid", gap: 8, padding: "10px 12px", borderRadius: 10, border: "1px solid rgba(20,32,57,0.08)", background: "rgba(248,249,244,0.8)" },
  healthRow: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 },
  healthLabel: { fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--color-text-tertiary)" },
  healthValue: { fontSize: 13, color: "var(--color-text-secondary)" },
  healthNote: { fontSize: 12, lineHeight: 1.45, color: "var(--color-text-secondary)" },
  inlineCode: { fontFamily: "var(--font-mono)", fontSize: 12, padding: "2px 6px", borderRadius: 8, background: "rgba(20,32,57,0.06)", color: "var(--color-text-secondary)" },
  sourceCardActions: { display: "flex", gap: 8 },
  ghostBtn: { display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--color-text-secondary)", background: "transparent", border: "1px solid var(--color-border)", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontFamily: "var(--font-body)" },
  emptyState: { display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" as const, padding: "60px 0", gap: 12 },
  emptyOrb: { width: 56, height: 56, borderRadius: 16, background: "var(--color-iris-muted)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-iris)", marginBottom: 4 },
  emptyTitle: { fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, color: "var(--color-text-primary)", margin: 0 },
  emptyBody: { fontSize: 14, color: "var(--color-text-secondary)", lineHeight: 1.6, maxWidth: 400, margin: 0 },
  primaryBtn: { padding: "9px 18px", background: "var(--color-iris)", color: "#fff", border: "none", borderRadius: 8, fontFamily: "var(--font-body)", fontSize: 14, fontWeight: 600, cursor: "pointer", flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 6 },
  secondaryBtn: { padding: "9px 14px", background: "transparent", color: "var(--color-text-secondary)", border: "1px solid var(--color-border)", borderRadius: 8, fontFamily: "var(--font-body)", fontSize: 13, fontWeight: 600, cursor: "pointer", flexShrink: 0 },
  cancelBtn: { padding: "9px 18px", background: "transparent", color: "var(--color-text-secondary)", border: "1px solid var(--color-border)", borderRadius: 8, fontFamily: "var(--font-body)", fontSize: 14, cursor: "pointer" },
  overlay: { position: "fixed" as const, inset: 0, background: "rgba(0,0,0,0.4)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 24 },
  modal: { background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 16, padding: "28px 28px 24px", width: "100%", maxWidth: 560, position: "relative" as const, boxShadow: "var(--shadow-lg)", maxHeight: "90vh", overflowY: "auto" },
  modalTitle: { fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 17, color: "var(--color-text-primary)", margin: "0 0 20px" },
  modalClose: { position: "absolute" as const, top: 16, right: 16, width: 28, height: 28, borderRadius: 6, border: "none", background: "var(--color-bg)", color: "var(--color-text-secondary)", fontSize: 16, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--font-body)" },
  typeGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 },
  typeCard: { display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 4, padding: "14px", border: "1px solid var(--color-border)", borderRadius: 10, background: "var(--color-bg)", cursor: "pointer", textAlign: "left" as const, transition: "border-color 0.1s", fontFamily: "var(--font-body)" },
  typeIcon: { color: "var(--color-iris)", marginBottom: 2 },
  typeLabel: { fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" },
  typeDesc: { fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.4 },
  formBody: { display: "flex", flexDirection: "column", gap: 16 },
  typeBackBtn: { display: "inline-flex", alignItems: "center", gap: 5, background: "transparent", border: "none", color: "var(--color-iris)", fontSize: 13, cursor: "pointer", padding: 0, fontFamily: "var(--font-body)", marginBottom: 4 },
  formGroup: { display: "flex", flexDirection: "column", gap: 6 },
  label: { fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" },
  accountTag: { fontSize: 12, fontWeight: 400, color: "var(--color-text-tertiary)" },
  fieldHint: { fontSize: 12, color: "var(--color-text-tertiary)", lineHeight: 1.5 },
  input: { padding: "9px 12px", borderRadius: 8, border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text-primary)", fontFamily: "var(--font-body)", fontSize: 14, outline: "none", width: "100%", boxSizing: "border-box" as const },
  fileDropZone: { border: "2px dashed var(--color-border)", borderRadius: 10, padding: "28px 20px", display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: "var(--color-text-secondary)" },
  filePickerLabel: { display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 6, border: "2px dashed var(--color-border)", borderRadius: 10, padding: "28px 20px", cursor: "pointer", transition: "border-color 0.15s, background 0.15s", background: "transparent" },
  filePickerIcon: { color: "var(--color-iris)", marginBottom: 2 },
  filePickerText: { fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)" },
  fileInputHint: { fontSize: 12, color: "var(--color-text-tertiary)" },
  fileSelected: { display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", border: "1px solid var(--color-iris)", borderRadius: 8, background: "var(--color-iris-muted)" },
  fileSelectedIcon: { color: "var(--color-iris)", flexShrink: 0 },
  fileSelectedMeta: { flex: 1, display: "flex", flexDirection: "column" as const, gap: 1, minWidth: 0 },
  fileSelectedName: { fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const },
  fileSelectedSize: { fontSize: 11, color: "var(--color-text-tertiary)" },
  formError: { fontSize: 13, color: "var(--color-rose)", margin: 0 },
  formActions: { display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 },

  // Browser
  browser: { border: "1px solid var(--color-border)", borderRadius: 10, maxHeight: 240, overflowY: "auto" as const, background: "var(--color-bg)" },
  browserCenter: { display: "flex", alignItems: "center", justifyContent: "center", padding: "24px 0", fontSize: 13, color: "var(--color-text-secondary)" },
  browserPlaceholder: { display: "flex", alignItems: "center", justifyContent: "center", minHeight: 80 },
  browserItem: { display: "flex", flexDirection: "column", gap: 2, width: "100%", padding: "10px 14px", background: "transparent", border: "none", borderBottom: "1px solid var(--color-border)", cursor: "pointer", textAlign: "left" as const, fontFamily: "var(--font-body)", transition: "background 0.1s" },
  browserItemMain: { display: "flex", alignItems: "center", gap: 8 },
  browserItemName: { fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" },
  browserItemDesc: { fontSize: 12, color: "var(--color-text-tertiary)", whiteSpace: "nowrap" as const, overflow: "hidden", textOverflow: "ellipsis" },
  privateBadge: { fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 4, background: "var(--color-iris-muted)", color: "var(--color-iris)" },

  // Connect prompt
  connectPrompt: { display: "flex", gap: 16, padding: "16px", border: "1px solid var(--color-border)", borderRadius: 12, background: "var(--color-bg)", alignItems: "flex-start" },
  connectPromptIcon: { width: 36, height: 36, borderRadius: 8, background: "var(--color-surface)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, color: "var(--color-text-secondary)" },
  connectPromptTitle: { fontSize: 14, fontWeight: 700, color: "var(--color-text-primary)", marginBottom: 6 },
  connectPromptBody: { fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.55, margin: "0 0 12px" },

  // Picked item
  pickedItem: { display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", border: "1px solid var(--color-teal)", borderRadius: 8, background: "rgba(20,184,166,0.06)" },
  pickedItemName: { flex: 1, fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" },
  pickedItemMeta: { fontSize: 12, color: "var(--color-text-tertiary)" },
  pickedClear: { background: "transparent", border: "none", cursor: "pointer", fontSize: 13, color: "var(--color-text-tertiary)", padding: "0 2px" },

  // Drive breadcrumb + row
  driveBreadcrumbs: { display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" as const, padding: "4px 0", marginBottom: 4 },
  driveCrumb: { background: "transparent", border: "none", cursor: "pointer", fontSize: 12, color: "var(--color-iris)", padding: "2px 4px", borderRadius: 4, fontFamily: "var(--font-body)", textDecoration: "underline" },
  driveCrumbSep: { fontSize: 12, color: "var(--color-text-tertiary)", userSelect: "none" as const },
  driveRow: { display: "flex", alignItems: "stretch", borderBottom: "1px solid var(--color-border)" },
  driveSelectFolderBtn: { flexShrink: 0, alignSelf: "center", margin: "6px 10px 6px 0", padding: "4px 10px", background: "var(--color-iris-muted)", color: "var(--color-iris)", border: "1px solid var(--color-iris)", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "var(--font-body)", whiteSpace: "nowrap" as const },

  // Loading
  loadingWrap: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" },
  spinner: { width: 28, height: 28, borderRadius: "50%", border: "3px solid var(--color-border)", borderTopColor: "var(--color-iris)", animation: "spin 0.7s linear infinite" },
  spinnerSm: { width: 18, height: 18, borderRadius: "50%", border: "2px solid var(--color-border)", borderTopColor: "var(--color-iris)", animation: "spin 0.7s linear infinite" },
};
