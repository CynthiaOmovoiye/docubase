import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.answering.llm_provider import LLMResponse
from app.domains.evaluation.quality_gate import (
    ResponseQualityGate,
    _conversation_excerpt_for_gate,
    _parse_gate_json,
    apply_twin_path_quality_gate,
    apply_workspace_aggregate_quality_gate,
)


def test_parse_gate_json_accepts_plain_object():
    raw = '{"is_acceptable": true, "feedback": ""}'
    g = _parse_gate_json(raw)
    assert g.is_acceptable is True
    assert g.feedback == ""


def test_parse_gate_json_strips_fences():
    raw = '```json\n{"is_acceptable": false, "feedback": "Too vague."}\n```'
    g = _parse_gate_json(raw)
    assert g.is_acceptable is False
    assert "vague" in g.feedback


def test_response_quality_gate_model_rejects_extra_keys():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResponseQualityGate.model_validate(
            {"is_acceptable": True, "feedback": "", "extra": 1}
        )


def test_conversation_excerpt_for_gate_includes_recent_roles():
    history = [
        {"role": "user", "content": "My name is Alex."},
        {"role": "assistant", "content": "Nice to meet you."},
        {"role": "user", "content": "What is my name?"},
    ]
    excerpt = _conversation_excerpt_for_gate(history)
    assert "USER:" in excerpt
    assert "Alex" in excerpt
    assert "ASSISTANT:" in excerpt


# ── exhaustion-branch tests ───────────────────────────────────────────────────

def _make_settings(*, enabled: bool = True, max_regenerations: int = 0) -> MagicMock:
    """Return a mock Settings object wired for quality gate behaviour."""
    s = MagicMock()
    s.chat_quality_gate_enabled = enabled
    s.chat_quality_gate_max_regenerations = max_regenerations
    return s


def _make_answer(content: str = "This is a draft answer.", model: str = "gpt-4o") -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        input_tokens=100,
        output_tokens=50,
    )


# ── twin path ─────────────────────────────────────────────────────────────────

class TestTwinPathExhaustion:
    @pytest.mark.asyncio
    async def test_exhaustion_log_includes_served_answer_preview(self):
        """
        When the gate rejects the answer and max_regenerations=0 (no retries
        allowed), apply_twin_path_quality_gate must emit a warning that
        includes 'served_answer_preview' and 'attempts'.

        This verifies that operators can assess what was served to the user
        without opening a separate investigation.
        """
        answer = _make_answer("The applicant has experience in product design.")

        rejected_gate = ResponseQualityGate(
            is_acceptable=False,
            feedback="Answer is not grounded in retrieved context.",
        )

        mock_settings = _make_settings(enabled=True, max_regenerations=0)
        mock_logger = MagicMock()

        with (
            patch(
                "app.domains.evaluation.quality_gate.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.domains.evaluation.quality_gate.evaluate_response_gate",
                new=AsyncMock(return_value=rejected_gate),
            ),
            patch("app.domains.evaluation.quality_gate.logger", mock_logger),
        ):
            result_answer, _, _ = await apply_twin_path_quality_gate(
                answer=answer,
                query="tell me about yourself",
                context_chunks=[{"source_ref": "doc.pdf", "content": "Some context."}],
                doctwin_name="test-twin",
                conversation_history=[],
                custom_context=None,
                allow_code_snippets=False,
                trace_id=None,
                sources=[],
                memory_brief=None,
                retrieval_packet=None,
                pipeline_trace_id=None,
            )

        # The original answer must be returned unchanged (exhausted, not improved)
        assert result_answer.content == answer.content

        # The warning must carry both diagnostic fields for operator triage
        warning_calls = mock_logger.warning.call_args_list
        assert warning_calls, "Expected logger.warning to be called on exhaustion"

        exhaustion_call = next(
            (c for c in warning_calls if "quality_gate_twin_exhausted" in c.args),
            None,
        )
        assert exhaustion_call is not None, (
            "'quality_gate_twin_exhausted' warning not emitted"
        )
        kwargs = exhaustion_call.kwargs
        assert "served_answer_preview" in kwargs, (
            "Exhaustion log must include 'served_answer_preview' for operator triage"
        )
        assert "attempts" in kwargs, (
            "Exhaustion log must include 'attempts' count"
        )
        assert kwargs["attempts"] == 1
        assert answer.content[:300] in kwargs["served_answer_preview"] or \
               kwargs["served_answer_preview"] in answer.content

    @pytest.mark.asyncio
    async def test_gate_disabled_skips_evaluation(self):
        """When chat_quality_gate_enabled=False the gate is a no-op."""
        answer = _make_answer()
        mock_settings = _make_settings(enabled=False)

        with (
            patch(
                "app.domains.evaluation.quality_gate.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.domains.evaluation.quality_gate.evaluate_response_gate",
                new=AsyncMock(side_effect=AssertionError("should not be called")),
            ),
        ):
            result, extra_gen, extra_verify = await apply_twin_path_quality_gate(
                answer=answer,
                query="what is this?",
                context_chunks=[],
                doctwin_name="test-twin",
                conversation_history=[],
                custom_context=None,
                allow_code_snippets=False,
                trace_id=None,
                sources=[],
                memory_brief=None,
                retrieval_packet=None,
                pipeline_trace_id=None,
            )

        assert result is answer
        assert extra_gen == 0.0
        assert extra_verify == 0.0

    @pytest.mark.asyncio
    async def test_deterministic_model_skips_gate(self):
        """Answers from deterministic models bypass the gate entirely."""
        answer = _make_answer(model="deterministic-fallback")
        mock_settings = _make_settings(enabled=True, max_regenerations=0)

        with (
            patch(
                "app.domains.evaluation.quality_gate.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.domains.evaluation.quality_gate.evaluate_response_gate",
                new=AsyncMock(side_effect=AssertionError("should not be called")),
            ),
        ):
            result, extra_gen, extra_verify = await apply_twin_path_quality_gate(
                answer=answer,
                query="what is this?",
                context_chunks=[],
                doctwin_name="test-twin",
                conversation_history=[],
                custom_context=None,
                allow_code_snippets=False,
                trace_id=None,
                sources=[],
                memory_brief=None,
                retrieval_packet=None,
                pipeline_trace_id=None,
            )

        assert result is answer


# ── workspace aggregate path ──────────────────────────────────────────────────

class TestWorkspaceExhaustion:
    @pytest.mark.asyncio
    async def test_exhaustion_log_includes_served_answer_preview(self):
        """
        apply_workspace_aggregate_quality_gate must emit
        'quality_gate_workspace_exhausted' with 'served_answer_preview'
        and 'attempts' when all regeneration attempts are spent.
        """
        import uuid

        answer = _make_answer("Workspace summary content here.")
        rejected_gate = ResponseQualityGate(
            is_acceptable=False,
            feedback="Missing grounding in project excerpts.",
        )

        mock_settings = _make_settings(enabled=True, max_regenerations=0)
        mock_logger = MagicMock()

        with (
            patch(
                "app.domains.evaluation.quality_gate.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.domains.evaluation.quality_gate.evaluate_response_gate",
                new=AsyncMock(return_value=rejected_gate),
            ),
            patch("app.domains.evaluation.quality_gate.logger", mock_logger),
        ):
            result_answer, _, _ = await apply_workspace_aggregate_quality_gate(
                answer=answer,
                query="tell me about this workspace",
                merged_chunks=[{"source_ref": "doc.pdf", "content": "context"}],
                workspace_name="test-workspace",
                project_contexts=[],
                conversation_history=[],
                workspace_memory=None,
                trace_id=None,
                workspace_id=uuid.uuid4(),
            )

        assert result_answer.content == answer.content

        warning_calls = mock_logger.warning.call_args_list
        exhaustion_call = next(
            (c for c in warning_calls if "quality_gate_workspace_exhausted" in c.args),
            None,
        )
        assert exhaustion_call is not None, (
            "'quality_gate_workspace_exhausted' warning not emitted"
        )
        kwargs = exhaustion_call.kwargs
        assert "served_answer_preview" in kwargs, (
            "Workspace exhaustion log must include 'served_answer_preview'"
        )
        assert "attempts" in kwargs, (
            "Workspace exhaustion log must include 'attempts' count"
        )
        assert kwargs["attempts"] == 1
