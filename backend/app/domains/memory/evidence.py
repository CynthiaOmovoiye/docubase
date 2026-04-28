from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.twin import Twin


@dataclass(slots=True)
class MemoryEvidenceBundle:
    doctwin_id: str
    workspace_id: str
    structure_overview: list[dict] = field(default_factory=list)


async def load_doctwin_memory_evidence(
    doctwin_id: str,
    db: AsyncSession,
    *,
    structure_overview: list[dict] | None = None,
) -> MemoryEvidenceBundle:
    doctwin_uuid = uuid.UUID(doctwin_id)
    twin = (
        await db.execute(
            select(Twin.id, Twin.workspace_id).where(Twin.id == doctwin_uuid)
        )
    ).one()

    return MemoryEvidenceBundle(
        doctwin_id=doctwin_id,
        workspace_id=str(twin.workspace_id),
        structure_overview=list(structure_overview or []),
    )


def _memory_ref(doctwin_id: str) -> str:
    return f"__memory__/{doctwin_id}"



def build_workspace_synthesis_content(
    *,
    workspace_name: str,
    project_rows: list[dict],
) -> tuple[str, dict]:
    techs = sorted(
        {
            tech
            for row in project_rows
            for tech in (row.get("languages") or [])
            if tech
        }
    )
    lines = [
        f"## Workspace synthesis for {workspace_name}",
        "",
        f"- Projects covered: {len(project_rows)}",
    ]
    if techs:
        lines.append("- Languages observed: " + ", ".join(f"`{tech}`" for tech in techs[:8]))
    lines.append("")

    project_metadata: list[dict] = []
    for row in project_rows:
        name = row["name"]
        lines.append(f"### {name}")
        lines.append(
            "- Evidence counts: "
            f"{row['files_indexed']} files, {row['symbols_indexed']} symbols, "
            f"{row['relationships_indexed']} relationships"
        )
        if row.get("artifact_labels"):
            lines.append("- Memory artifacts: " + ", ".join(f"`{label}`" for label in row["artifact_labels"]))
        if row.get("brief_excerpt"):
            lines.append(f"- Brief signal: {row['brief_excerpt']}")
        lines.append("")
        project_metadata.append(
            {
                "doctwin_id": row["doctwin_id"],
                "name": name,
                "files_indexed": row["files_indexed"],
                "symbols_indexed": row["symbols_indexed"],
                "relationships_indexed": row["relationships_indexed"],
                "artifact_labels": row.get("artifact_labels") or [],
            }
        )

    return "\n".join(lines).strip(), {"projects": project_metadata, "languages": techs}


