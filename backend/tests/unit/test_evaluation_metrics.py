from app.domains.answering.verifier import AnswerVerificationResult
from app.domains.evaluation.metrics import (
    build_single_project_quality_metrics,
    build_workspace_quality_metrics,
)
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    EvidenceSpan,
    EvidenceSymbolRef,
    RetrievalEvidencePacket,
)
from app.domains.retrieval.planner import RetrievalMode


def _packet() -> RetrievalEvidencePacket:
    return RetrievalEvidencePacket(
        query="How is auth handled?",
        search_query="How is auth handled?",
        lexical_query="How is auth handled?",
        intent="architecture",
        mode=RetrievalMode.implementation,
        searched_layers=["vector", "lexical", "symbol"],
        negative_evidence_scope=["symbol", "file", "lexical"],
        missing_evidence=["tests"],
        files=[EvidenceFileRef(path="app/auth.py")],
        symbols=[
            EvidenceSymbolRef(
                symbol_name="get_current_user",
                qualified_name="auth.get_current_user",
                symbol_kind="function",
                path="app/auth.py",
            )
        ],
        spans=[
            EvidenceSpan(
                chunk_id="1",
                chunk_type="documentation",
                path="app/auth.py",
                doctwin_id="t1",
                source_id="s1",
                snapshot_id="sha:test",
                start_line=1,
                end_line=20,
                score=0.9,
            )
        ],
    )


def test_single_project_metrics_count_grounded_citations():
    metrics = build_single_project_quality_metrics(
        answer="Authorization is checked in `app/auth.py` via `auth.get_current_user`.",
        packet=_packet(),
        verification=AnswerVerificationResult(content="ok", verified=True),
        retry_requested=False,
    )

    assert metrics.mode == "implementation"
    assert metrics.citation_count >= 2
    assert metrics.grounded_anchor_present is True
    assert metrics.negative_claims_bounded is True
    assert metrics.false_not_present_risk is False


def test_workspace_metrics_track_labels_and_leakage():
    verification = AnswerVerificationResult(
        content="ok",
        verified=False,
        rewritten=True,
        issues=["cross_project_leakage:Scaffold"],
    )
    metrics = build_workspace_quality_metrics(
        answer="## Scaffold\nUses `app/auth.py`\n\n## someother chat\nUses `auth.get_current_user`",
        project_contexts=[
            {"name": "Scaffold", "evidence_packet": _packet()},
            {"name": "someother chat", "evidence_packet": _packet()},
        ],
        verification=verification,
        retry_requested=True,
    )

    assert metrics.workspace_project_count == 2
    assert metrics.workspace_labels_complete is True
    assert metrics.cross_project_leakage_detected is True
    assert metrics.verifier_retry_requested is True
