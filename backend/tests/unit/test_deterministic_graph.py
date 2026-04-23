import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domains.graph.deterministic import build_deterministic_graph, merge_graph_extractions
from app.models.implementation_fact import ImplementationFactType
from app.domains.graph.extractor import ExtractedEntity, ExtractedRelationship, GraphExtractionResult
from app.models.implementation_index import (
    IndexedFileKind,
    IndexedRelationshipType,
    IndexedSymbolKind,
)


def _scalar_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    result.scalars = MagicMock(return_value=scalars)
    return result


class TestDeterministicGraph:
    @pytest.mark.asyncio
    async def test_builds_entities_and_relationships_from_index_rows(self):
        twin_id = "00000000-0000-0000-0000-000000000099"
        file_row = SimpleNamespace(
            path="app/api/auth.py",
            file_kind=IndexedFileKind.code,
            framework_role="api_routes",
            language="python",
        )
        symbol_row = SimpleNamespace(
            path="app/api/auth.py",
            qualified_name="login_user",
            symbol_kind=IndexedSymbolKind.async_function,
            signature="async def login_user(payload: LoginRequest) -> dict:",
        )
        relationship_row = SimpleNamespace(
            source_ref="file:app/api/auth.py",
            source_kind="file",
            target_ref="symbol:app/api/auth.py::login_user",
            target_kind="symbol",
            relationship_type=IndexedRelationshipType.contains,
            relationship_metadata={"symbol_kind": "async_function"},
        )

        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result([]),  # implementation facts (Phase 5)
                _scalar_result([file_row]),
                _scalar_result([symbol_row]),
                _scalar_result([relationship_row]),
            ]
        )

        graph = await build_deterministic_graph(twin_id, db)

        assert any(entity.name == "app/api/auth.py" for entity in graph.entities)
        assert any("login_user" in entity.name for entity in graph.entities)
        assert any(
            relationship.source == "app/api/auth.py"
            and "login_user" in relationship.target
            and relationship.relationship_type == "contains"
            for relationship in graph.relationships
        )

    def test_merge_keeps_deterministic_entities_and_adds_unique_llm_entities(self):
        deterministic = GraphExtractionResult(
            entities=[
                ExtractedEntity(
                    name="app/api/auth.py",
                    entity_type="module",
                    description="python code file",
                    source_refs=["app/api/auth.py"],
                )
            ],
            relationships=[],
        )
        llm = GraphExtractionResult(
            entities=[
                ExtractedEntity(
                    name="FastAPI",
                    entity_type="technology",
                    description="framework",
                    source_refs=["app/api/auth.py"],
                )
            ],
            relationships=[
                ExtractedRelationship(
                    source="app/api/auth.py",
                    target="FastAPI",
                    relationship_type="uses",
                    description="imports FastAPI",
                )
            ],
        )

        merged = merge_graph_extractions(deterministic, llm)

        assert {entity.name for entity in merged.entities} == {"app/api/auth.py", "FastAPI"}
        assert merged.relationships[0].relationship_type == "uses"

    @pytest.mark.asyncio
    async def test_integrates_implementation_facts_before_index_rows(self):
        twin_id = "00000000-0000-0000-0000-000000000099"
        fact_row = SimpleNamespace(
            id=uuid.uuid4(),
            path="app/services/auth.py",
            subject="verify_token",
            predicate="uses",
            object_ref="",
            summary="checks JWT",
            fact_type=ImplementationFactType.auth_check,
        )
        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar_result([fact_row]),
                _scalar_result([]),
                _scalar_result([]),
                _scalar_result([]),
            ]
        )

        graph = await build_deterministic_graph(twin_id, db)

        assert any(e.name == "app/services/auth.py" for e in graph.entities)
        assert any("verify_token" in e.name for e in graph.entities)
        assert any(
            r.source == "app/services/auth.py"
            and "verify_token" in r.target
            and r.relationship_type == "implements"
            for r in graph.relationships
        )
