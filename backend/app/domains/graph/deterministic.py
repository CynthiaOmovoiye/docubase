from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.extractor import (
    ExtractedEntity,
    ExtractedRelationship,
    GraphExtractionResult,
)
from app.domains.knowledge.implementation_facts_access import load_ready_implementation_facts_ordered
from app.models.implementation_index import (
    IndexedFile,
    IndexedFileKind,
    IndexedRelationship,
    IndexedSymbol,
    IndexedSymbolKind,
)


async def build_deterministic_graph(
    twin_id: str,
    db: AsyncSession,
) -> GraphExtractionResult:
    twin_uuid = uuid.UUID(twin_id)
    entities_by_ref: dict[str, ExtractedEntity] = {}
    name_by_ref: dict[str, str] = {}
    relationships: list[ExtractedRelationship] = []
    seen_relationships: set[tuple[str, str, str]] = set()

    fact_rows = await load_ready_implementation_facts_ordered(db, twin_id, limit=400)
    _integrate_implementation_facts_into_graph(
        fact_rows,
        entities_by_ref,
        name_by_ref,
        relationships,
        seen_relationships,
    )

    file_rows = list(
        (await db.execute(select(IndexedFile).where(IndexedFile.twin_id == twin_uuid)))
        .scalars()
        .all()
    )
    symbol_rows = list(
        (await db.execute(select(IndexedSymbol).where(IndexedSymbol.twin_id == twin_uuid)))
        .scalars()
        .all()
    )
    relationship_rows = list(
        (await db.execute(select(IndexedRelationship).where(IndexedRelationship.twin_id == twin_uuid)))
        .scalars()
        .all()
    )

    for file_row in file_rows:
        ref = _file_ref(file_row.path)
        entity = ExtractedEntity(
            name=file_row.path,
            entity_type=_entity_type_for_file(file_row),
            description=_describe_file(file_row),
            source_refs=[file_row.path],
        )
        entities_by_ref[ref] = entity
        name_by_ref[ref] = entity.name

    for symbol_row in symbol_rows:
        ref = _symbol_ref(symbol_row.path, symbol_row.qualified_name)
        entity = ExtractedEntity(
            name=_display_symbol_name(symbol_row),
            entity_type=_entity_type_for_symbol(symbol_row),
            description=_describe_symbol(symbol_row),
            source_refs=[symbol_row.path],
        )
        entities_by_ref[ref] = entity
        name_by_ref[ref] = entity.name

    for relationship in relationship_rows:
        src_name = _ensure_ref_entity(
            relationship.source_ref,
            relationship.source_kind,
            relationship.relationship_metadata,
            entities_by_ref,
            name_by_ref,
        )
        tgt_name = _ensure_ref_entity(
            relationship.target_ref,
            relationship.target_kind,
            relationship.relationship_metadata,
            entities_by_ref,
            name_by_ref,
        )
        if not src_name or not tgt_name:
            continue
        rel_key = (src_name.lower(), tgt_name.lower(), relationship.relationship_type.value)
        if rel_key in seen_relationships:
            continue
        seen_relationships.add(rel_key)
        relationships.append(
            ExtractedRelationship(
                source=src_name,
                target=tgt_name,
                relationship_type=relationship.relationship_type.value,
                description=_describe_relationship(relationship),
            )
        )

    return GraphExtractionResult(
        entities=list(entities_by_ref.values()),
        relationships=relationships,
    )


def _integrate_implementation_facts_into_graph(
    fact_rows: list,
    entities_by_ref: dict[str, ExtractedEntity],
    name_by_ref: dict[str, str],
    relationships: list[ExtractedRelationship],
    seen_relationships: set[tuple[str, str, str]],
) -> None:
    """Phase 5 — add file/subject edges from normalized facts before index relationships."""
    for row in fact_rows:
        if not hasattr(row, "path") or not hasattr(row, "fact_type"):
            continue
        path = (row.path or "").strip()
        if not path:
            continue
        ft = row.fact_type.value if hasattr(row.fact_type, "value") else str(row.fact_type)
        pref = _file_ref(path)
        if pref not in entities_by_ref:
            entities_by_ref[pref] = ExtractedEntity(
                name=path,
                entity_type="module",
                description=f"implementation_fact ({ft})",
                source_refs=[path],
            )
            name_by_ref[pref] = path

        subj = (row.subject or "").strip() or "unknown"
        sym_ref = f"symbol:{path}::{subj}"
        if sym_ref not in entities_by_ref:
            display = f"{subj} ({path})"
            entities_by_ref[sym_ref] = ExtractedEntity(
                name=display,
                entity_type="module",
                description=f"implementation_fact subject ({ft})",
                source_refs=[path],
            )
            name_by_ref[sym_ref] = display

        src_name = path
        tgt_name = entities_by_ref[sym_ref].name
        rel_type = _relationship_type_for_implementation_fact(ft)
        key = (src_name.lower(), tgt_name.lower(), rel_type)
        if key not in seen_relationships and src_name.lower() != tgt_name.lower():
            seen_relationships.add(key)
            relationships.append(
                ExtractedRelationship(
                    source=src_name,
                    target=tgt_name,
                    relationship_type=rel_type,
                    description=((row.summary or "")[:220] or ft),
                )
            )

        obj = (row.object_ref or "").strip()
        if obj and _object_ref_looks_like_repo_path(obj) and obj != path:
            oref = _file_ref(obj)
            if oref not in entities_by_ref:
                entities_by_ref[oref] = ExtractedEntity(
                    name=obj,
                    entity_type="module",
                    description="implementation_fact object_ref",
                    source_refs=[obj],
                )
                name_by_ref[oref] = obj
            rk = (tgt_name.lower(), obj.lower(), "calls")
            if rk not in seen_relationships:
                seen_relationships.add(rk)
                relationships.append(
                    ExtractedRelationship(
                        source=tgt_name,
                        target=obj,
                        relationship_type="calls",
                        description=f"object_ref ({ft})",
                    )
                )


def _relationship_type_for_implementation_fact(ft: str) -> str:
    if ft in {
        "route",
        "route_config",
        "auth_check",
        "validation_constraint",
        "handler",
    }:
        return "implements"
    if ft in {"api_call", "call", "service_edge"}:
        return "calls"
    if ft in {"dependency", "injection_site", "hook_binding"}:
        return "depends_on"
    if ft in {"data_model", "model_edge"}:
        return "produces"
    if ft in {"background_job", "ui_action"}:
        return "uses"
    return "uses"


def _object_ref_looks_like_repo_path(value: str) -> bool:
    v = value.strip()
    if not v or v.startswith("http://") or v.startswith("https://"):
        return False
    return "/" in v and any(v.endswith(ext) for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"))


def merge_graph_extractions(
    deterministic: GraphExtractionResult,
    llm_enriched: GraphExtractionResult,
) -> GraphExtractionResult:
    entities: dict[str, ExtractedEntity] = {}
    for entity in deterministic.entities + llm_enriched.entities:
        key = entity.name.lower()
        if key not in entities:
            entities[key] = entity
            continue
        merged_refs = sorted(set((entities[key].source_refs or []) + (entity.source_refs or [])))
        description = entities[key].description or entity.description
        entities[key] = entities[key].model_copy(
            update={
                "description": description,
                "source_refs": merged_refs,
            }
        )

    entity_names = set(entities.keys())
    relationships: list[ExtractedRelationship] = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for relationship in deterministic.relationships + llm_enriched.relationships:
        rel_key = (
            relationship.source.lower(),
            relationship.target.lower(),
            relationship.relationship_type,
        )
        if rel_key in seen_relationships:
            continue
        if (
            relationship.source.lower() not in entity_names
            or relationship.target.lower() not in entity_names
        ):
            continue
        seen_relationships.add(rel_key)
        relationships.append(relationship)

    return GraphExtractionResult(
        entities=list(entities.values()),
        relationships=relationships,
    )


def _entity_type_for_file(file_row: IndexedFile) -> str:
    if file_row.file_kind == IndexedFileKind.dependency_manifest:
        return "technology"
    if file_row.file_kind == IndexedFileKind.documentation:
        return "concept"
    return "module"


def _entity_type_for_symbol(symbol_row: IndexedSymbol) -> str:
    if symbol_row.symbol_kind == IndexedSymbolKind.data_model:
        return "data_model"
    return "module"


def _display_symbol_name(symbol_row: IndexedSymbol) -> str:
    return f"{symbol_row.qualified_name} ({symbol_row.path})"


def _describe_file(file_row: IndexedFile) -> str:
    role = f" role={file_row.framework_role}" if file_row.framework_role else ""
    language = file_row.language or "unknown"
    return f"{language} {file_row.file_kind.value} file{role}"


def _describe_symbol(symbol_row: IndexedSymbol) -> str:
    signature = f": {symbol_row.signature}" if symbol_row.signature else ""
    return f"{symbol_row.symbol_kind.value} defined in {symbol_row.path}{signature}"


def _describe_relationship(relationship: IndexedRelationship) -> str:
    metadata = relationship.relationship_metadata or {}
    if relationship.relationship_type.value == "depends_on":
        import_name = metadata.get("import_name") or metadata.get("import_from")
        if import_name:
            return f"imports {import_name}"
    if relationship.relationship_type.value == "uses":
        annotation_name = metadata.get("annotation_name")
        if annotation_name:
            return f"uses {annotation_name} in a type annotation"
    if relationship.relationship_type.value == "extends":
        base_name = metadata.get("base_name")
        if base_name:
            return f"extends {base_name}"
    if relationship.relationship_type.value == "contains":
        symbol_kind = metadata.get("symbol_kind")
        if symbol_kind:
            return f"contains {symbol_kind}"
    if relationship.relationship_type.value == "produces":
        return "produces a data model artifact"
    return relationship.relationship_type.value.replace("_", " ")


def _ensure_ref_entity(
    ref: str,
    ref_kind: str,
    metadata: dict,
    entities_by_ref: dict[str, ExtractedEntity],
    name_by_ref: dict[str, str],
) -> str | None:
    if ref in name_by_ref:
        return name_by_ref[ref]

    entity = _build_external_entity(ref, ref_kind, metadata)
    if entity is None:
        return None
    entities_by_ref[ref] = entity
    name_by_ref[ref] = entity.name
    return entity.name


def _build_external_entity(
    ref: str,
    ref_kind: str,
    metadata: dict,
) -> ExtractedEntity | None:
    if ref.startswith("module:"):
        module_name = ref.removeprefix("module:")
        return ExtractedEntity(
            name=module_name,
            entity_type="technology" if not module_name.startswith(".") else "module",
            description="imported module or package",
            source_refs=[],
        )
    if ref.startswith("symbol_external:"):
        symbol_name = ref.removeprefix("symbol_external:")
        return ExtractedEntity(
            name=symbol_name,
            entity_type="concept" if ref_kind == "type" else "module",
            description="referenced external symbol",
            source_refs=[],
        )
    if ref.startswith("file:"):
        path = ref.removeprefix("file:")
        return ExtractedEntity(
            name=path,
            entity_type="module",
            description="indexed file reference",
            source_refs=[path],
        )
    if ref.startswith("symbol:"):
        _, rest = ref.split(":", 1)
        path, qualified_name = rest.split("::", 1)
        return ExtractedEntity(
            name=f"{qualified_name} ({path})",
            entity_type="module",
            description="indexed symbol reference",
            source_refs=[path],
        )
    return None


def _file_ref(path: str) -> str:
    return f"file:{path}"


def _symbol_ref(path: str, qualified_name: str) -> str:
    return f"symbol:{path}::{qualified_name}"
