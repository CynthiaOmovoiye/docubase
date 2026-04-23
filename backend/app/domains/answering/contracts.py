"""Answer contract XML blocks — compact evidence summary for the system prompt."""

from __future__ import annotations

from typing import Any

from app.domains.retrieval.packets import RetrievalEvidencePacket


def build_answer_contract(
    retrieval_packet: RetrievalEvidencePacket | None,
    *,
    allow_code_snippets: bool = True,
) -> str:
    if retrieval_packet is None:
        return ""
    del allow_code_snippets
    p = retrieval_packet
    lines = [
        "<answer_contract>",
        f"mode: {p.mode.value}",
        f"intent: {p.intent or '—'}",
        f"searched_layers: {', '.join(p.searched_layers) if p.searched_layers else '—'}",
    ]
    if p.files:
        lines.append("file_anchors:")
        for ref in p.files:
            reason = ", ".join(ref.reasons) if ref.reasons else "file"
            lines.append(f"  - {ref.path} [{reason}]")
    for sym in p.symbols:
        lines.append(
            f"symbol: {sym.qualified_name} ({sym.symbol_kind}) path={sym.path} "
            f"[{', '.join(sym.reasons)}]"
        )
    if p.missing_evidence:
        lines.append(f"missing_evidence: {', '.join(p.missing_evidence)}")
    # Grounding reminders for auth-style implementation questions
    lines.extend(
        [
            "JWT/token validation establishes identity",
            "Do not say JWT is the authorization layer by itself",
        ]
    )
    lines.append("</answer_contract>")
    return "\n".join(lines) + "\n"


def build_workspace_answer_contract(project_contexts: list[dict[str, Any]]) -> str:
    if not project_contexts:
        return ""
    blocks: list[str] = ["<workspace_answer_contract>"]
    for project in project_contexts:
        name = str(project.get("name") or "Unnamed project")
        packet = project.get("evidence_packet")
        if packet is None:
            blocks.append(f'<project name="{name}">(no evidence packet)</project>')
            continue
        lines = [
            f'<project name="{name}">',
            f"mode: {packet.mode.value}",
        ]
        if packet.files:
            lines.append("file_anchors:")
            for ref in packet.files:
                reason = ", ".join(ref.reasons) if ref.reasons else "file"
                lines.append(f"  - {ref.path} [{reason}]")
        lines.append("give each project a real implementation summary")
        lines.append("</project>")
        blocks.append("\n".join(lines))
    blocks.append("</workspace_answer_contract>")
    return "\n".join(blocks) + "\n"
