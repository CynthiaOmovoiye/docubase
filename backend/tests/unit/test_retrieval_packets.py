from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    EvidenceSymbolRef,
    build_evidence_packet,
)
from app.domains.retrieval.planner import build_retrieval_plan


class TestEvidencePacket:
    def test_packet_merges_files_and_spans_from_chunks(self):
        plan = build_retrieval_plan(
            query="How is auth implemented?",
            intent=QueryIntent.architecture,
            expanded_query="Explain the auth implementation and the files involved.",
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "code_snippet",
                    "source_ref": "app/auth.py",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.91,
                    "match_reasons": ["vector", "symbol:login_user"],
                }
            ],
            file_matches=[
                EvidenceFileRef(
                    path="app/auth.py",
                    doctwin_id="twin-1",
                    source_id="source-1",
                    snapshot_id="snap-1",
                    reasons=["file"],
                )
            ],
            symbol_matches=[
                EvidenceSymbolRef(
                    symbol_name="login_user",
                    qualified_name="login_user",
                    symbol_kind="async_function",
                    path="app/auth.py",
                    doctwin_id="twin-1",
                    source_id="source-1",
                    snapshot_id="snap-1",
                    reasons=["symbol"],
                )
            ],
        )

        assert packet.chunk_ids == ["chunk-1"]
        assert packet.files[0].path == "app/auth.py"
        assert "symbol:login_user" in packet.files[0].reasons
        assert packet.spans[0].start_line == 10
        assert packet.layer_hits["file"] == 1
        assert packet.layer_hits["symbol"] == 1

    def test_packet_counts_facts_in_layer_hits_and_flow_outline(self):
        plan = build_retrieval_plan(
            query="How is auth implemented?",
            intent=QueryIntent.architecture,
        )
        facts = [
            {
                "fact_type": "route",
                "path": "app/routes.py",
                "summary": "POST /login",
                "subject": "login",
                "predicate": "defines",
                "object_ref": None,
                "source_id": "s1",
                "fact_id": "f1",
                "score": 1.0,
            },
            {
                "fact_type": "auth_check",
                "path": "app/deps.py",
                "summary": "Depends get_current_user",
                "subject": "x",
                "predicate": "y",
                "object_ref": None,
                "source_id": "s1",
                "fact_id": "f2",
                "score": 1.0,
            },
        ]
        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[],
            facts=facts,
        )
        assert packet.layer_hits.get("facts") == 2
        assert "route:1" in packet.flow_outline
        assert "auth_check:1" in packet.flow_outline

    def test_packet_flow_outline_includes_structural_segment_from_graph_edges(self):
        plan = build_retrieval_plan(
            query="How is auth implemented?",
            intent=QueryIntent.architecture,
        )
        facts = [
            {
                "fact_type": "route",
                "path": "app/routes.py",
                "summary": "POST /login",
                "subject": "login",
                "predicate": "defines",
                "object_ref": None,
                "source_id": "s1",
                "fact_id": "f1",
                "score": 1.0,
            },
        ]
        edges = [{"source": "app/routes.py", "relationship": "contains", "target": "login"}]
        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[],
            facts=facts,
            graph_edges=edges,
        )
        assert "|| structural:" in packet.flow_outline
        assert "app/routes.py" in packet.flow_outline
        assert "contains" in packet.flow_outline

    def test_packet_does_not_promote_memory_refs_into_file_list(self):
        plan = build_retrieval_plan(
            query="How is auth implemented?",
            intent=QueryIntent.architecture,
        )

        packet = build_evidence_packet(
            plan=plan,
            doctwin_id="twin-1",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "chunk_type": "auth_flow",
                    "source_ref": "__memory__/twin-1",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "score": 0.91,
                    "match_reasons": ["vector"],
                },
                {
                    "chunk_id": "chunk-2",
                    "chunk_type": "code_snippet",
                    "source_ref": "app/auth.py",
                    "source_id": "source-1",
                    "doctwin_id": "twin-1",
                    "snapshot_id": "snap-1",
                    "start_line": 10,
                    "end_line": 20,
                    "score": 0.88,
                    "match_reasons": ["symbol:login_user"],
                },
            ],
            file_matches=[],
            symbol_matches=[],
        )

        assert [file_ref.path for file_ref in packet.files] == ["app/auth.py"]

    def test_packet_promotes_grounded_file_refs_from_memory_provenance(self):
        plan = build_retrieval_plan(
            query="What changed recently in auth?",
            intent=QueryIntent.change_query,
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
            intent=QueryIntent.risk_query,
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
