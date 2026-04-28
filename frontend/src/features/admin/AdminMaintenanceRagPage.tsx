import { useState } from "react";

import { useIsMobile } from "@/hooks/useIsMobile";
import { useAdminRebuildTwinMemory, useAdminTwinRagDiagnostics } from "@/hooks/useAdmin";
import { adminStyles as s } from "@/features/admin/styles";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default function AdminMaintenanceRagPage() {
  const isMobile = useIsMobile();
  const diagMutation = useAdminTwinRagDiagnostics();
  const rebuildMutation = useAdminRebuildTwinMemory();
  const [twinId, setTwinId] = useState("");
  const [previewQ, setPreviewQ] = useState("");
  const twinValid = UUID_RE.test(twinId.trim());

  return (
    <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
      <section style={s.hero}>
        <div>
          <p style={s.eyebrow}>Maintenance</p>
          <h1 style={s.title}>RAG diagnostics &amp; memory</h1>
          <p style={s.subtitle}>
            Inspect indexing coverage per twin and enqueue memory brief regeneration when answers drift from sources.
          </p>
        </div>
      </section>

      <section style={s.panel}>
        <p style={s.panelEyebrow}>Twin tools</p>
        <h2 style={s.panelTitle}>Retrieval preview &amp; memory rebuild</h2>
        <p style={s.panelBody}>
          Paste a twin UUID from <code style={s.code}>/twin/:id</code>. Optionally add a preview query to test retrieval hits.
        </p>

        <div style={s.formRow}>
          <label style={s.label} htmlFor="rag-twin-id">
            Twin ID
          </label>
          <input
            id="rag-twin-id"
            style={s.input}
            value={twinId}
            onChange={(e) => setTwinId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            autoComplete="off"
          />
        </div>
        <div style={s.formRow}>
          <label style={s.label} htmlFor="rag-preview-q">
            Preview query (optional)
          </label>
          <input
            id="rag-preview-q"
            style={s.input}
            value={previewQ}
            onChange={(e) => setPreviewQ(e.target.value)}
            placeholder="e.g. What does the README say about authentication?"
            autoComplete="off"
          />
        </div>

        <div style={s.actions}>
          <button
            type="button"
            style={twinValid ? s.primaryBtn : s.primaryBtnDisabled}
            disabled={!twinValid || diagMutation.isPending}
            onClick={() => diagMutation.mutate({ twinId: twinId.trim(), q: previewQ || undefined })}
          >
            {diagMutation.isPending ? "Loading…" : "Load RAG diagnostics"}
          </button>
          <button
            type="button"
            style={twinValid ? s.secondaryBtn : s.secondaryBtnDisabled}
            disabled={!twinValid || rebuildMutation.isPending}
            onClick={() => rebuildMutation.mutate(twinId.trim())}
          >
            {rebuildMutation.isPending ? "Enqueueing…" : "Rebuild memory brief"}
          </button>
        </div>

        {diagMutation.isError && (
          <p style={s.errorText}>{(diagMutation.error as Error)?.message ?? "Diagnostics request failed."}</p>
        )}
        {diagMutation.data && <pre style={s.pre}>{JSON.stringify(diagMutation.data, null, 2)}</pre>}

        {rebuildMutation.isSuccess && rebuildMutation.data && (
          <p style={s.successText}>
            Enqueued: {rebuildMutation.data.action} for twin {rebuildMutation.data.doctwin_id}
          </p>
        )}
        {rebuildMutation.isError && (
          <p style={s.errorText}>{(rebuildMutation.error as Error)?.message ?? "Rebuild request failed."}</p>
        )}
      </section>
    </div>
  );
}
