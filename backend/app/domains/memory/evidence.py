from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.git_index import GitActivity
from app.models.implementation_index import IndexedFile, IndexedRelationship, IndexedSymbol
from app.models.twin import Twin

_AUTH_RE = re.compile(
    r"\b(auth|login|logout|signin|sign_in|signout|sign_out|signup|sign_up|token|jwt|session|oauth|guard|current_user|middleware|clerk)\b",
    re.IGNORECASE,
)
_RISKY_RE = re.compile(r"\b(auth|payment|billing|webhook|queue|worker|migration|db|database)\b", re.IGNORECASE)


@dataclass(slots=True)
class MemoryEvidenceBundle:
    twin_id: str
    workspace_id: str
    indexed_files: list[IndexedFile] = field(default_factory=list)
    indexed_symbols: list[IndexedSymbol] = field(default_factory=list)
    indexed_relationships: list[IndexedRelationship] = field(default_factory=list)
    git_activities: list[GitActivity] = field(default_factory=list)
    structure_overview: list[dict] = field(default_factory=list)


async def load_twin_memory_evidence(
    twin_id: str,
    db: AsyncSession,
    *,
    structure_overview: list[dict] | None = None,
) -> MemoryEvidenceBundle:
    twin_uuid = uuid.UUID(twin_id)
    twin = (
        await db.execute(
            select(Twin.id, Twin.workspace_id).where(Twin.id == twin_uuid)
        )
    ).one()

    indexed_files = list(
        (await db.execute(select(IndexedFile).where(IndexedFile.twin_id == twin_uuid)))
        .scalars()
        .all()
    )
    indexed_symbols = list(
        (await db.execute(select(IndexedSymbol).where(IndexedSymbol.twin_id == twin_uuid)))
        .scalars()
        .all()
    )
    indexed_relationships = list(
        (await db.execute(select(IndexedRelationship).where(IndexedRelationship.twin_id == twin_uuid)))
        .scalars()
        .all()
    )
    git_activities = list(
        (
            await db.execute(
                select(GitActivity)
                .where(GitActivity.twin_id == twin_uuid)
                .order_by(GitActivity.occurred_at.desc().nullslast(), GitActivity.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    return MemoryEvidenceBundle(
        twin_id=twin_id,
        workspace_id=str(twin.workspace_id),
        indexed_files=indexed_files,
        indexed_symbols=indexed_symbols,
        indexed_relationships=indexed_relationships,
        git_activities=git_activities,
        structure_overview=list(structure_overview or []),
    )


def build_feature_summary_chunks(bundle: MemoryEvidenceBundle) -> list[dict]:
    groups: dict[str, dict] = {}
    symbol_count_by_path = _count_by_path(bundle.indexed_symbols)
    relationship_count_by_path = _count_by_path(bundle.indexed_relationships, attr="source_ref")
    symbols_by_path = _symbols_by_path(bundle.indexed_symbols)

    for file_row in bundle.indexed_files:
        key = _feature_group_key(file_row.path, file_row.framework_role)
        group = groups.setdefault(
            key,
            {
                "files": [],
                "roles": set(),
                "symbol_count": 0,
                "relationship_count": 0,
            },
        )
        group["files"].append(file_row)
        if file_row.framework_role:
            group["roles"].add(file_row.framework_role)
        group["symbol_count"] += symbol_count_by_path.get(file_row.path, 0)
        group["relationship_count"] += relationship_count_by_path.get(file_row.path, 0)

    ranked = sorted(
        groups.items(),
        key=lambda item: (
            item[1]["symbol_count"] + item[1]["relationship_count"] + len(item[1]["files"]),
            len(item[1]["files"]),
        ),
        reverse=True,
    )
    chunks: list[dict] = []
    for label, group in ranked[:4]:
        files = sorted(group["files"], key=lambda row: row.path)[:6]
        sample_files = [file_row.path for file_row in files]
        sample_symbols = []
        for file_path in sample_files:
            sample_symbols.extend(symbols_by_path.get(file_path, [])[:2])
        sample_symbols = sample_symbols[:6]
        content_lines = [
            f"**{_format_feature_label(label)}**",
            f"Grounded files: {', '.join(f'`{path}`' for path in sample_files)}",
            (
                f"Signals: {len(group['files'])} indexed files, "
                f"{group['symbol_count']} indexed symbols, "
                f"{group['relationship_count']} relationship edges."
            ),
        ]
        if group["roles"]:
            content_lines.append(
                "Framework roles: " + ", ".join(f"`{role}`" for role in sorted(group["roles"]))
            )
        if sample_symbols:
            content_lines.append(
                "Representative symbols: "
                + ", ".join(f"`{symbol}`" for symbol in sample_symbols)
            )
        chunks.append(
            {
                "chunk_type": "feature_summary",
                "content": "\n".join(content_lines),
                "source_ref": _memory_ref(bundle.twin_id),
                "chunk_metadata": {
                    "extraction": "feature_summary",
                    "label": label,
                    "provenance": _build_provenance_for_paths(bundle, sample_files, sample_symbols),
                },
            }
        )
    return chunks


def build_auth_flow_chunks(bundle: MemoryEvidenceBundle) -> list[dict]:
    relationship_paths, relationship_symbol_names = _extract_index_refs_from_relationships(
        [
            rel
            for rel in bundle.indexed_relationships
            if _AUTH_RE.search(rel.source_ref) or _AUTH_RE.search(rel.target_ref)
        ]
    )
    symbol_count_by_path = _count_by_path(bundle.indexed_symbols)
    relationship_count_by_path = _count_by_path(bundle.indexed_relationships, attr="source_ref")
    auth_files = sorted(
        bundle.indexed_files,
        key=lambda file_row: (
            4 if _AUTH_RE.search(file_row.path) else 0,
            3 if file_row.path in relationship_paths else 0,
            symbol_count_by_path.get(file_row.path, 0),
            relationship_count_by_path.get(file_row.path, 0),
        ),
        reverse=True,
    )
    auth_files = [
        file_row
        for file_row in auth_files
        if _AUTH_RE.search(file_row.path)
        or file_row.path in relationship_paths
        or symbol_count_by_path.get(file_row.path, 0) > 0 and "auth" in file_row.path.lower()
    ]
    auth_symbols = [
        symbol
        for symbol in bundle.indexed_symbols
        if _AUTH_RE.search(symbol.symbol_name) or _AUTH_RE.search(symbol.qualified_name) or _AUTH_RE.search(symbol.path)
    ]
    auth_relationships = [
        rel
        for rel in bundle.indexed_relationships
        if _AUTH_RE.search(rel.source_ref) or _AUTH_RE.search(rel.target_ref)
    ]
    file_paths = list(dict.fromkeys(file_row.path for file_row in auth_files))[:8]
    symbol_names = list(
        dict.fromkeys(symbol.qualified_name or symbol.symbol_name for symbol in auth_symbols)
    )[:8]
    for path in relationship_paths:
        if path not in file_paths:
            file_paths.append(path)
    file_paths = file_paths[:8]
    for symbol_name in relationship_symbol_names:
        if symbol_name not in symbol_names:
            symbol_names.append(symbol_name)
    symbol_names = symbol_names[:8]
    relationship_lines = [
        f"`{rel.source_ref}` -[{rel.relationship_type.value}]-> `{rel.target_ref}`"
        for rel in auth_relationships[:6]
    ]
    if not (file_paths or symbol_names or relationship_lines):
        return []

    content_lines = ["**Authentication / authorization flow**"]
    if file_paths:
        content_lines.append("Grounded files: " + ", ".join(f"`{path}`" for path in file_paths))
    if symbol_names:
        content_lines.append("Grounded symbols: " + ", ".join(f"`{name}`" for name in symbol_names))
    if relationship_lines:
        content_lines.append("Observed relationships: " + ", ".join(relationship_lines))
    content_lines.append(
        "This artifact only captures auth-related signals that were explicitly present in the deterministic indexes."
    )
    return [
        {
            "chunk_type": "auth_flow",
            "content": "\n".join(content_lines),
            "source_ref": _memory_ref(bundle.twin_id),
            "chunk_metadata": {
                "extraction": "auth_flow",
                "provenance": _build_provenance_for_paths(bundle, file_paths, symbol_names),
            },
        }
    ]


def build_onboarding_map_chunks(bundle: MemoryEvidenceBundle) -> list[dict]:
    symbol_count_by_path = _count_by_path(bundle.indexed_symbols)
    relationship_count_by_path = _count_by_path(bundle.indexed_relationships, attr="source_ref")
    ranked_files = sorted(
        bundle.indexed_files,
        key=lambda file_row: (
            6 if file_row.framework_role == "dependency_manifest" else 0,
            5 if file_row.framework_role == "api_routes" else 0,
            4 if file_row.framework_role == "data_models" else 0,
            3 if file_row.framework_role == "config" else 0,
            2 if file_row.framework_role == "tests" else 0,
            3 if _AUTH_RE.search(file_row.path) else 0,
            relationship_count_by_path.get(file_row.path, 0),
            symbol_count_by_path.get(file_row.path, 0),
        ),
        reverse=True,
    )

    ordered_paths: list[str] = []
    for file_row in ranked_files:
        if file_row.path not in ordered_paths:
            ordered_paths.append(file_row.path)
        if len(ordered_paths) >= 6:
            break

    if not ordered_paths:
        ordered_paths = [entry["file_paths"][0] for entry in bundle.structure_overview[:4] if entry.get("file_paths")]

    if not ordered_paths:
        return []

    steps = [
        f"{index}. `{path}`"
        for index, path in enumerate(ordered_paths[:6], start=1)
    ]
    content_lines = [
        "**Onboarding map**",
        "Suggested reading order:",
        *steps,
    ]
    roles = [
        f"`{file_row.path}` ({file_row.framework_role})"
        for file_row in bundle.indexed_files
        if file_row.path in ordered_paths[:6] and file_row.framework_role
    ]
    if roles:
        content_lines.append("Role hints: " + ", ".join(roles))
    return [
        {
            "chunk_type": "onboarding_map",
            "content": "\n".join(content_lines),
            "source_ref": _memory_ref(bundle.twin_id),
            "chunk_metadata": {
                "extraction": "onboarding_map",
                "provenance": _build_provenance_for_paths(bundle, ordered_paths[:6], []),
            },
        }
    ]


def build_risk_summary_chunks(bundle: MemoryEvidenceBundle) -> list[dict]:
    symbol_count_by_path = _count_by_path(bundle.indexed_symbols)
    relationship_count_by_path = _count_by_path(bundle.indexed_relationships, attr="source_ref")
    ranked_files = sorted(
        bundle.indexed_files,
        key=lambda row: (
            symbol_count_by_path.get(row.path, 0)
            + relationship_count_by_path.get(row.path, 0)
            + (8 if _RISKY_RE.search(row.path) else 0)
        ),
        reverse=True,
    )

    chunks: list[dict] = []
    for file_row in ranked_files[:3]:
        symbol_count = symbol_count_by_path.get(file_row.path, 0)
        relationship_count = relationship_count_by_path.get(file_row.path, 0)
        if symbol_count == 0 and relationship_count == 0 and not _RISKY_RE.search(file_row.path):
            continue
        severity = "high" if symbol_count + relationship_count >= 12 else "medium"
        content_lines = [
            f"**Potential hotspot: {file_row.path}** ({severity.upper()})",
            (
                f"This file has {symbol_count} indexed symbols and {relationship_count} "
                "relationship edges in the deterministic implementation index."
            ),
        ]
        if file_row.framework_role:
            content_lines.append(f"Role hint: `{file_row.framework_role}`.")
        chunks.append(
            {
                "chunk_type": "risk_note",
                "content": "\n".join(content_lines),
                "source_ref": _memory_ref(bundle.twin_id),
                "chunk_metadata": {
                    "extraction": "risk_summary",
                    "severity": severity,
                    "affected_paths": [file_row.path],
                    "provenance": _build_provenance_for_paths(bundle, [file_row.path], []),
                },
            }
        )
    return chunks


def build_change_summary_chunks(bundle: MemoryEvidenceBundle) -> list[dict]:
    if not bundle.git_activities:
        return []

    by_week: dict[str, dict] = {}
    for activity in bundle.git_activities:
        week_label = _week_label(activity.occurred_at)
        bucket = by_week.setdefault(
            week_label,
            {
                "titles": [],
                "paths": [],
                "count": 0,
                "activity_keys": [],
            },
        )
        bucket["count"] += 1
        bucket["activity_keys"].append(activity.activity_key)
        if activity.title:
            bucket["titles"].append(activity.title)
        for path in activity.path_refs[:8]:
            if path not in bucket["paths"]:
                bucket["paths"].append(path)

    chunks: list[dict] = []
    for week_label, bucket in list(by_week.items())[:4]:
        titles = bucket["titles"][:4]
        paths = bucket["paths"][:8]
        lines = [
            f"**{week_label}** ({bucket['count']} activit{'y' if bucket['count'] == 1 else 'ies'})",
        ]
        if titles:
            lines.append("Recent activity: " + "; ".join(titles))
        if paths:
            lines.append("Touched paths: " + ", ".join(f"`{path}`" for path in paths))
        chunks.append(
            {
                "chunk_type": "change_entry",
                "content": "\n".join(lines),
                "source_ref": _memory_ref(bundle.twin_id),
                "chunk_metadata": {
                    "extraction": "change_summary",
                    "period": week_label,
                    "activity_count": bucket["count"],
                    "activity_keys": bucket["activity_keys"][:12],
                    "provenance": _build_provenance_for_paths(bundle, paths, []),
                },
            }
        )
    return chunks


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
            f"- Evidence counts: {row['files_indexed']} files, {row['symbols_indexed']} symbols, {row['relationships_indexed']} relationships"
        )
        if row.get("artifact_labels"):
            lines.append("- Memory artifacts: " + ", ".join(f"`{label}`" for label in row["artifact_labels"]))
        if row.get("brief_excerpt"):
            lines.append(f"- Brief signal: {row['brief_excerpt']}")
        lines.append("")
        project_metadata.append(
            {
                "twin_id": row["twin_id"],
                "name": name,
                "files_indexed": row["files_indexed"],
                "symbols_indexed": row["symbols_indexed"],
                "relationships_indexed": row["relationships_indexed"],
                "artifact_labels": row.get("artifact_labels") or [],
            }
        )

    return "\n".join(lines).strip(), {"projects": project_metadata, "languages": techs}


def _memory_ref(twin_id: str) -> str:
    return f"__memory__/{twin_id}"


def _feature_group_key(path: str, framework_role: str | None) -> str:
    if framework_role and framework_role not in {"library_module"}:
        return framework_role
    parts = PurePosixPath(path).parts
    if len(parts) > 1:
        return parts[0]
    return "_root"


def _format_feature_label(label: str) -> str:
    if label == "_root":
        return "Root-level components"
    return label.replace("_", " ").title()


def _count_by_path(rows: list, *, attr: str = "path") -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        raw_value = str(getattr(row, attr))
        if attr != "path":
            kind, path, _symbol_name = _parse_index_ref(raw_value)
            if kind == "file" and path:
                counts[path] += 1
                continue
            if kind == "symbol" and path:
                counts[path] += 1
                continue
        counts[raw_value] += 1
    return counts


def _symbols_by_path(symbols: list[IndexedSymbol]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols:
        grouped[symbol.path].append(symbol.qualified_name or symbol.symbol_name)
    return grouped


def _build_provenance_for_paths(
    bundle: MemoryEvidenceBundle,
    paths: list[str],
    symbol_names: list[str],
) -> list[dict]:
    path_lookup = {file_row.path: file_row for file_row in bundle.indexed_files}
    symbol_lookup = {
        (symbol.qualified_name or symbol.symbol_name): symbol
        for symbol in bundle.indexed_symbols
    }
    provenance: list[dict] = []
    for path in paths:
        file_row = path_lookup.get(path)
        if file_row is None:
            continue
        provenance.append(
            {
                "kind": "file",
                "path": file_row.path,
                "source_id": str(file_row.source_id),
                "snapshot_id": file_row.snapshot_id,
            }
        )
    for symbol_name in symbol_names:
        symbol_row = symbol_lookup.get(symbol_name)
        if symbol_row is None:
            continue
        provenance.append(
            {
                "kind": "symbol",
                "path": symbol_row.path,
                "symbol_name": symbol_row.symbol_name,
                "qualified_name": symbol_row.qualified_name,
                "start_line": symbol_row.start_line,
                "end_line": symbol_row.end_line,
                "source_id": str(symbol_row.source_id),
                "snapshot_id": symbol_row.snapshot_id,
            }
        )
    return provenance


def _extract_index_refs_from_relationships(
    relationships: list[IndexedRelationship],
) -> tuple[list[str], list[str]]:
    file_paths: list[str] = []
    symbol_names: list[str] = []
    for relationship in relationships:
        for ref in (relationship.source_ref, relationship.target_ref):
            kind, path, symbol_name = _parse_index_ref(ref)
            if kind == "file" and path and path not in file_paths:
                file_paths.append(path)
            elif kind == "symbol" and symbol_name and symbol_name not in symbol_names:
                symbol_names.append(symbol_name)
    return file_paths, symbol_names


def _parse_index_ref(raw_ref: str) -> tuple[str | None, str | None, str | None]:
    if raw_ref.startswith("file:"):
        return "file", raw_ref.removeprefix("file:"), None
    if raw_ref.startswith("symbol:"):
        payload = raw_ref.removeprefix("symbol:")
        if "::" in payload:
            path, symbol_name = payload.split("::", 1)
            return "symbol", path, symbol_name
    return None, None, None


def _week_label(raw_value: str | None) -> str:
    if not raw_value:
        return "Undated activity"
    normalized = raw_value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return str(raw_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    day = dt.astimezone(UTC).date()
    return f"Week of {day.strftime('%B')} {day.day}, {day.year}"
