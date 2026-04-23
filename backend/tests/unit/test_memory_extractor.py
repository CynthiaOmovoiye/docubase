"""
Unit tests for app.domains.memory.extractor — JSON parsing helpers and
extraction function behaviour under mock LLM responses.

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
    extract_architecture_chunks,
    extract_change_entry_chunks,
    extract_risk_chunks,
    generate_memory_brief,
)


TWIN_ID = "00000000-0000-0000-0000-000000000001"


# ── JSON parse helpers ────────────────────────────────────────────────────────

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


# ── _select_chunks ────────────────────────────────────────────────────────────

class TestSelectChunks:
    def _make_chunk(self, chunk_type: str, content: str = "x" * 100) -> dict:
        return {"chunk_type": chunk_type, "content": content, "source_ref": "test"}

    def test_filters_by_allowed_types(self):
        chunks = [
            self._make_chunk("module_description"),
            self._make_chunk("code_snippet"),
            self._make_chunk("documentation"),
        ]
        selected = _select_chunks(chunks, {"module_description", "documentation"})
        types = [c["chunk_type"] for c in selected]
        assert "code_snippet" not in types
        assert "module_description" in types
        assert "documentation" in types

    def test_priority_order(self):
        chunks = [
            self._make_chunk("documentation"),
            self._make_chunk("module_description"),
            self._make_chunk("dependency_signal"),
        ]
        selected = _select_chunks(
            chunks,
            {"module_description", "documentation", "dependency_signal"},
        )
        # module_description has highest priority (0)
        assert selected[0]["chunk_type"] == "module_description"

    def test_respects_max_chunks(self):
        chunks = [self._make_chunk("module_description") for _ in range(10)]
        selected = _select_chunks(chunks, {"module_description"}, max_chunks=3)
        assert len(selected) <= 3

    def test_respects_max_chars(self):
        # Each chunk is 100 chars. max_chars=150 should stop after 1 chunk.
        chunks = [self._make_chunk("module_description", "x" * 100) for _ in range(5)]
        selected = _select_chunks(chunks, {"module_description"}, max_chunks=10, max_chars=150)
        assert len(selected) == 1

    def test_empty_input(self):
        assert _select_chunks([], {"module_description"}) == []

    def test_no_matching_types(self):
        chunks = [self._make_chunk("code_snippet")]
        assert _select_chunks(chunks, {"module_description"}) == []


# ── _chunks_to_context ────────────────────────────────────────────────────────

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


# ── extract_architecture_chunks ───────────────────────────────────────────────

ARCH_RESPONSE = json.dumps({
    "repo_type": "product_codebase",
    "repo_type_reasoning": "The repository contains deployable application modules and backend services.",
    "summary": "A FastAPI backend with async SQLAlchemy.",
    "technologies": ["FastAPI: async API layer", "PostgreSQL: primary database"],
    "notable_patterns": ["Routes are grouped by domain"],
    "structure": [
        {"path": "app/main.py", "role": "Application entry point"},
    ],
    "design_decisions": [
        {"decision": "Use ARQ for background jobs", "rationale": "Simple Redis-backed queue"},
    ],
})


class TestExtractArchitectureChunks:
    async def _run_with_mock_response(self, content: str) -> list[dict]:
        mock_response = MagicMock()
        mock_response.content = content

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        existing_chunks = [
            {
                "chunk_type": "module_description",
                "content": "FastAPI application entry point",
                "source_ref": "app/main.py",
                "chunk_metadata": {},
            }
        ]

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            return await extract_architecture_chunks(TWIN_ID, existing_chunks)

    @pytest.mark.asyncio
    async def test_returns_chunks_on_success(self):
        chunks = await self._run_with_mock_response(ARCH_RESPONSE)
        types = [c["chunk_type"] for c in chunks]
        assert "architecture_summary" in types
        assert "hotspot" in types
        assert "decision_record" in types

    @pytest.mark.asyncio
    async def test_memory_ref_on_all_chunks(self):
        chunks = await self._run_with_mock_response(ARCH_RESPONSE)
        for c in chunks:
            assert c["source_ref"] == f"__memory__/{TWIN_ID}"

    @pytest.mark.asyncio
    async def test_returns_empty_on_malformed_json(self):
        chunks = await self._run_with_mock_response("not json at all")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_input_chunks(self):
        mock_provider = MagicMock()
        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_architecture_chunks(TWIN_ID, [])
        assert result == []
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_on_llm_exception(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=Exception("LLM down"))
        existing_chunks = [
            {"chunk_type": "module_description", "content": "x", "source_ref": "y", "chunk_metadata": {}}
        ]
        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_architecture_chunks(TWIN_ID, existing_chunks)
        assert result == []


# ── extract_risk_chunks ───────────────────────────────────────────────────────

RISK_RESPONSE = json.dumps([
    {
        "title": "No error handling in payment flow",
        "description": "The checkout endpoint has no try/except.",
        "affected_paths": ["app/payments/service.py"],
        "severity": "high",
    },
    {
        "title": "Unvalidated webhook",
        "description": "Webhook handler does not verify HMAC.",
        "affected_paths": ["app/webhooks/handler.py"],
        "severity": "high",
    },
])


class TestExtractRiskChunks:
    @pytest.mark.asyncio
    async def test_returns_risk_note_chunks(self):
        mock_response = MagicMock()
        mock_response.content = RISK_RESPONSE
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        chunks = [
            {"chunk_type": "module_description", "content": "payment code here", "source_ref": "app/payments/service.py", "chunk_metadata": {}}
        ]

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_risk_chunks(TWIN_ID, chunks)

        assert len(result) == 2
        for c in result:
            assert c["chunk_type"] == "risk_note"
            assert c["source_ref"] == f"__memory__/{TWIN_ID}"

    @pytest.mark.asyncio
    async def test_severity_in_metadata(self):
        mock_response = MagicMock()
        mock_response.content = RISK_RESPONSE
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        chunks = [
            {"chunk_type": "module_description", "content": "x", "source_ref": "y", "chunk_metadata": {}}
        ]

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_risk_chunks(TWIN_ID, chunks)

        severities = [c["chunk_metadata"]["severity"] for c in result]
        assert all(s == "high" for s in severities)

    @pytest.mark.asyncio
    async def test_returns_empty_on_malformed(self):
        mock_response = MagicMock()
        mock_response.content = "not json"
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        chunks = [
            {"chunk_type": "code_snippet", "content": "x", "source_ref": "y", "chunk_metadata": {}}
        ]

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_risk_chunks(TWIN_ID, chunks)

        assert result == []


# ── extract_change_entry_chunks ───────────────────────────────────────────────

CHANGE_RESPONSE = json.dumps([
    {
        "period": "Week of April 14, 2026",
        "summary": "Added memory extraction pipeline and new chunk types.",
        "files_touched": ["app/domains/memory/service.py", "app/models/chunk.py"],
        "commit_count": 5,
        "themes": ["feature", "database"],
    }
])


class TestExtractChangeEntryChunks:
    @pytest.mark.asyncio
    async def test_returns_change_entry_chunks(self):
        mock_response = MagicMock()
        mock_response.content = CHANGE_RESPONSE
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        commits = [
            {
                "sha": "abc1234",
                "message": "Add memory extraction pipeline",
                "author_name": "Cynthia",
                "author_date": "2026-04-14T10:00:00Z",
                "files_changed": ["app/domains/memory/service.py"],
                "additions": 200,
                "deletions": 10,
            }
        ]

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_change_entry_chunks(TWIN_ID, commits)

        assert len(result) == 1
        assert result[0]["chunk_type"] == "change_entry"
        assert result[0]["source_ref"] == f"__memory__/{TWIN_ID}"
        assert "Week of April 14" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_commits(self):
        mock_provider = MagicMock()
        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await extract_change_entry_chunks(TWIN_ID, [])
        # Should return early without calling LLM
        assert result == []
        mock_provider.complete.assert_not_called()


# ── generate_memory_brief ─────────────────────────────────────────────────────

class TestGenerateMemoryBrief:
    @pytest.mark.asyncio
    async def test_returns_brief_string(self):
        mock_response = MagicMock()
        mock_response.content = "## What This Project Does\n\nA great project."
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await generate_memory_brief(
                twin_id=TWIN_ID,
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
                twin_id=TWIN_ID,
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
                twin_id=TWIN_ID,
                architecture_text=None,
                arch_chunk_dicts=[],
                risk_chunks=[],
                change_chunks=[],
                existing_chunks=[],
            )
        # No context → no LLM call, empty result
        assert result == ""
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_on_llm_exception(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch("app.domains.memory.extractor.get_llm_provider", return_value=mock_provider):
            result = await generate_memory_brief(
                twin_id=TWIN_ID,
                architecture_text="some text",
                arch_chunk_dicts=[],
                risk_chunks=[],
                change_chunks=[],
                existing_chunks=[],
            )
        assert result == ""
