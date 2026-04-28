import { useIsMobile } from "@/hooks/useIsMobile";
import { useAdminIngestionLogs } from "@/hooks/useAdmin";
import { adminStyles as s } from "@/features/admin/styles";

export default function AdminMaintenanceIngestionPage() {
  const isMobile = useIsMobile();
  const { data: logs } = useAdminIngestionLogs();

  return (
    <div style={{ ...s.page, padding: isMobile ? "68px 16px 32px" : "34px 32px 40px" }}>
      <section style={s.hero}>
        <div>
          <p style={s.eyebrow}>Maintenance</p>
          <h1 style={s.title}>Ingestion jobs</h1>
          <p style={s.subtitle}>
            Visibility into ingestion will expand once job history is persisted. Until then, check worker logs on the host.
          </p>
        </div>
      </section>

      <section style={s.panel}>
        <div style={s.panelHeader}>
          <p style={s.panelEyebrow}>Ingestion</p>
          <h2 style={s.panelTitle}>Job history</h2>
        </div>
        <p style={s.panelBody}>{logs?.note ?? "Loading…"}</p>
        {logs?.items && logs.items.length > 0 && (
          <pre style={s.pre}>{JSON.stringify(logs.items, null, 2)}</pre>
        )}
      </section>
    </div>
  );
}
