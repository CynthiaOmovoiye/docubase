from app.domains.evaluation.quality_gate import (
    ResponseQualityGate,
    _conversation_excerpt_for_gate,
    _parse_gate_json,
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
