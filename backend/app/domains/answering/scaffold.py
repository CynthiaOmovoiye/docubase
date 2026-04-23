"""Answer scaffold XML blocks — structured hints layered on the contract."""

from __future__ import annotations

from typing import Any

from app.domains.retrieval.packets import RetrievalEvidencePacket


def build_answer_scaffold(retrieval_packet: RetrievalEvidencePacket | None) -> str:
    if retrieval_packet is None:
        return ""
    p = retrieval_packet
    lines = [
        "<answer_scaffold>",
        f"implementation_facts: {len(p.facts)} row(s)",
        f"flow_outline: {p.flow_outline or '—'}",
    ]
    if p.query_labels:
        lines.append(f"query_labels: {', '.join(p.query_labels)}")
    lines.append("</answer_scaffold>")
    return "\n".join(lines) + "\n"


def build_workspace_answer_scaffold(project_contexts: list[dict[str, Any]]) -> str:
    if not project_contexts:
        return ""
    parts = ["<workspace_answer_scaffold>", "<project_evidence_index>"]
    for project in project_contexts:
        name = str(project.get("name") or "Unnamed project")
        packet: RetrievalEvidencePacket | None = project.get("evidence_packet")
        if packet is None:
            parts.append(f'<project name="{name}">—</project>')
            continue
        row = [f'<project name="{name}">']
        if packet.files:
            for ref in packet.files:
                reason = ", ".join(ref.reasons) if ref.reasons else "file"
                row.append(f"files: {ref.path} [{reason}]")
        if packet.facts:
            row.append(f"facts: {len(packet.facts)}")
        row.append("</project>")
        parts.append("\n".join(row))
    parts.append("</project_evidence_index>")
    parts.append("</workspace_answer_scaffold>")
    return "\n".join(parts) + "\n"
