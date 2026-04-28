from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    build_evidence_packet,
)
from app.domains.retrieval.planner import build_retrieval_plan


class TestEvidencePacket:
    def test_packet_merges_files_and_spans_from_chunks(self):
        plan = build_retrieval_plan(
            query="How is the onboarding guide structured?",
            intent=QueryIntent.specific,
            expanded_query="Walk through the structure of the onboarding guide.",
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "documentation",
                    "source_ref": "docs/onboarding.md",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.91,
                    "match_reasons": ["vector", "lexical"],
                }
            ],
            file_matches=[
                EvidenceFileRef(
                    path="docs/onboarding.md",
                    doctwin_id="twin-1",
                    source_id="source-1",
                    snapshot_id="snap-1",
                    reasons=["file"],
                )
            ],
            symbol_matches=[],
        )

        assert packet.chunk_ids == ["chunk-1"]
        assert packet.files[0].path == "docs/onboarding.md"
        assert packet.spans[0].start_line == 10
        assert packet.layer_hits["file"] == 1

    def test_packet_does_not_promote_memory_refs_into_file_list(self):
        plan = build_retrieval_plan(
            query="What is this project about?",
            intent=QueryIntent.general,
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "memory_brief",
                    "source_ref": "__memory__/twin-1",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "score": 0.91,
                    "match_reasons": ["vector"],
                },
                {
                    "chunk_id": "chunk-2",
                    "chunk_type": "documentation",
                    "source_ref": "docs/overview.md",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.88,
                    "match_reasons": ["lexical"],
                },
            ],
            file_matches=[],
            symbol_matches=[],
        )

        assert [file_ref.path for file_ref in packet.files] == ["docs/overview.md"]

    def test_packet_promotes_grounded_file_refs_from_memory_provenance(self):
        plan = build_retrieval_plan(
            query="What changed recently in auth?",
            intent=QueryIntent.general,
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "change_entry",
                    "source_ref": "__memory__/twin-1",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "score": 0.55,
                    "match_reasons": ["memory"],
                    "chunk_metadata": {
                        "provenance": [
                            {"path": "changes/auth_april.md"},
                            {"path": "backend/app/api/v1/users.py"},
                        ]
                    },
                }
            ],
            file_matches=[],
            symbol_matches=[],
        )

        assert {file_ref.path for file_ref in packet.files} == {
            "backend/app/api/v1/users.py",
            "changes/auth_april.md",
        }

    def test_packet_promotes_backticked_file_refs_from_memory_content_when_provenance_missing(self):
        plan = build_retrieval_plan(
            query="What looks risky or fragile?",
            intent=QueryIntent.general,
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "risk_note",
                    "source_ref": "__memory__/twin-1",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "score": 0.44,
                    "match_reasons": ["memory"],
                    "content": (
                        "**Potential hotspot**\n"
                        "`backend/app/api/v1/users.py` is handling logout invalidation."
                    ),
                    "chunk_metadata": {},
                }
            ],
            file_matches=[],
            symbol_matches=[],
        )

        assert [file_ref.path for file_ref in packet.files] == ["backend/app/api/v1/users.py"]

    def test_packet_includes_graph_edges(self):
        plan = build_retrieval_plan(
            query="What is in the authentication flow?",
            intent=QueryIntent.general,
        )
        edges = [{"source": "app/routes.py", "relationship": "contains", "target": "login"}]

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[],
            graph_edges=edges,
        )

        assert len(packet.graph_edges) == 1
        assert packet.graph_edges[0]["source"] == "app/routes.py"
