"""Orchestration tests for ``apply_twin_path_quality_gate`` (LLM stubs only)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.answering.llm_provider import LLMResponse
from app.domains.evaluation.quality_gate import (
    ResponseQualityGate,
    apply_twin_path_quality_gate,
)


@pytest.mark.asyncio
async def test_apply_twin_path_quality_gate_accepts_without_extra_generation(db_session):  # noqa: ARG001
    """Gate accepts first draft — no regenerate loop when judge returns acceptable."""

    answer = LLMResponse(
        content="Grounded reply referencing only the excerpt.",
        model="integration-gpt",
        input_tokens=40,
        output_tokens=20,
    )

    gate_ok = ResponseQualityGate(is_acceptable=True, feedback="")

    mock_settings = MagicMock()
    mock_settings.chat_quality_gate_enabled = True
    mock_settings.chat_quality_gate_max_regenerations = 2
    mock_settings.chat_quality_gate_fail_open = True

    with (
        patch("app.domains.evaluation.quality_gate.get_settings", return_value=mock_settings),
        patch(
            "app.domains.evaluation.quality_gate.evaluate_response_gate",
            new=AsyncMock(return_value=gate_ok),
        ),
    ):
        final, extra_gen, extra_verify = await apply_twin_path_quality_gate(
            answer=answer,
            query="Summarize the constraint.",
            context_chunks=[{"source_ref": "manual/notes.md", "content": "Use Postgres for integration tests."}],
            doctwin_name="integration-twin",
            conversation_history=[],
            custom_context=None,
            allow_code_snippets=False,
            trace_id=None,
            sources=[{"name": "manual-notes", "source_type": "manual", "status": "ready"}],
            memory_brief=None,
            retrieval_packet=None,
            pipeline_trace_id=None,
        )

    assert final.content == answer.content
    assert extra_gen == 0.0
    assert extra_verify == 0.0
