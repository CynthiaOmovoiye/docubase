import pytest

from app.domains.graph.deterministic import build_deterministic_graph, merge_graph_extractions
from app.domains.graph.extractor import (
    ExtractedEntity,
    ExtractedRelationship,
    GraphExtractionResult,
)


class TestDeterministicGraph:
    @pytest.mark.asyncio
    async def test_build_deterministic_graph_returns_empty_seed(self):
        """Repo-intelligence index seeding was removed; graph pass relies on LLM + chunks."""
        graph = await build_deterministic_graph(
            "00000000-0000-0000-0000-000000000099",
            None,  # type: ignore[arg-type]
        )
        assert graph.entities == []
        assert graph.relationships == []

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
