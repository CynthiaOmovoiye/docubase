"""
Unit tests for app.domains.memory.extractor — JSON parsing helpers,
chunk budgeting, and generate_memory_brief under mock LLM responses.

All LLM calls are mocked. No network. No DB.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.memory.extractor import (
    _chunks_to_context,
    _parse_json_array,
    _parse_json_object,
    _select_chunks,
    generate_memory_brief,
)

doctwin_ID = "00000000-0000-0000-0000-000000000001"


class TestParseJsonObject:
    def test_clean_json(self):
        result = _parse_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_strips_markdown_fences(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        assert _parse_json_object(text) == {"key": "value"}

    def test_strips_plain_fences(self):
        text = "```\n{\"a\": 1}\n```"
        assert _parse_json_object(text) == {"a": 1}

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_object("not json")

    def test_nested_object(self):
        data = {"a": {"b": [1, 2, 3]}}
        assert _parse_json_object(json.dumps(data)) == data


class TestParseJsonArray:
    def test_clean_array(self):
        assert _parse_json_array("[1, 2, 3]") == [1, 2, 3]

    def test_strips_markdown_fences(self):
        text = "```json\n[{\"a\": 1}]\n```"
        assert _parse_json_array(text) == [{"a": 1}]

    def test_raises_on_invalid(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_array("not an array")

    def test_empty_array(self):
        assert _parse_json_array("[]") == []


class TestSelectChunks:
    def _make_chunk(self, chunk_type: str, content: str = "x" * 100) -> dict:
        return {"chunk_type": chunk_type, "content": content, "source_ref": "test"}

    def test_respects_max_chunks(self):
        chunks = [self._make_chunk("documentation") for _ in range(10)]
        selected = _select_chunks(chunks, max_chunks=3)
        assert len(selected) == 3

    def test_respects_max_chars(self):
        chunks = [self._make_chunk("documentation", "x" * 100) for _ in range(5)]
        selected = _select_chunks(chunks, max_chunks=10, max_chars=150)
        assert len(selected) == 1

    def test_empty_input(self):
        assert _select_chunks([]) == []

    def test_preserves_order(self):
        chunks = [
            self._make_chunk("a", "a"),
            self._make_chunk("b", "b"),
        ]
        selected = _select_chunks(chunks, max_chunks=2)
        assert [c["chunk_type"] for c in selected] == ["a", "b"]


class TestChunksToContext:
    def test_formats_single_chunk(self):
        chunks = [{"chunk_type": "module_description", "source_ref": "app/main.py", "content": "Main entry"}]
        result = _chunks_to_context(chunks)
        assert "[module_description]" in result
        assert "app/main.py" in result
        assert "Main entry" in result

    def test_separates_multiple_chunks(self):
        chunks = [
            {"chunk_type": "a", "source_ref": "ref1", "content": "first"},
            {"chunk_type": "b", "source_ref": "ref2", "content": "second"},
        ]
        result = _chunks_to_context(chunks)
        assert "---" in result
        assert "first" in result
        assert "second" in result

    def test_handles_empty(self):
        assert _chunks_to_context([]) == ""


class TestGenerateMemoryBrief:
    @pytest.mark.asyncio
    async def test_returns_brief_string(self):
        mock_response = MagicMock()
        mock_response.content = "## What This Project Does\n\nA great project."
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await generate_memory_brief(
                doctwin_id=doctwin_ID,
                architecture_text="FastAPI backend",
                arch_chunk_dicts=[{"chunk_type": "hotspot", "content": "**app/main.py**\nApplication entry point"}],
                risk_chunks=[{"content": "Risk: no error handling"}],
                change_chunks=[{"content": "Week 1: added auth"}],
                existing_chunks=[
                    {"chunk_type": "module_description", "content": "main entry", "source_ref": "app/main.py"}
                ],
                structure_overview=[{"dir_path": "app", "file_paths": ["app/main.py"], "file_count": 1}],
            )

        assert "## What This Project Does" in result

    @pytest.mark.asyncio
    async def test_passes_implementation_fact_digest_into_llm_context(self):
        digest = "## Implementation facts (deterministic, indexed)\n\n- `app/x.py` **route** — edge"
        mock_response = MagicMock()
        mock_response.content = "## Brief\n\nOK."
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            await generate_memory_brief(
                doctwin_id=doctwin_ID,
                architecture_text=None,
                arch_chunk_dicts=[],
                risk_chunks=[{"content": "Risk: something"}],
                change_chunks=[],
                existing_chunks=[],
                implementation_fact_digest=digest,
            )

        user_content = mock_provider.complete.await_args.kwargs["messages"][0]["content"]
        assert digest in user_content

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_context(self):
        mock_provider = MagicMock()
        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await generate_memory_brief(
                doctwin_id=doctwin_ID,
                architecture_text=None,
                arch_chunk_dicts=[],
                risk_chunks=[],
                change_chunks=[],
                existing_chunks=[],
            )
        assert result == ""
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_on_llm_exception(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await generate_memory_brief(
                doctwin_id=doctwin_ID,
                architecture_text="some text",
                arch_chunk_dicts=[],
                risk_chunks=[],
                change_chunks=[],
                existing_chunks=[],
            )
        assert result == ""
