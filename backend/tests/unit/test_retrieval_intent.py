"""
Unit tests for query intent analysis (LLM path + regex fallback).

Covers:
  - LLM provider failure → regex fallback
  - Malformed JSON from LLM → regex fallback
  - Empty query → immediate general without LLM call
  - Happy-path LLM response → full QueryAnalysis with expanded_query
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.retrieval.intent import (
    QueryAnalysis,
    QueryIntent,
    analyse_query,
    classify_intent,
    extract_path_hint,
)

# ── regex-only helpers ────────────────────────────────────────────────────────

class TestClassifyIntent:
    def test_file_reference_is_specific(self):
        assert classify_intent("show me resume.pdf") == QueryIntent.specific

    def test_preposition_reference_is_specific(self):
        assert classify_intent("tell me about the Eshicare SA brief") == QueryIntent.specific

    def test_broad_question_is_general(self):
        assert classify_intent("what projects have you built?") == QueryIntent.general

    def test_tell_me_about_yourself_is_general(self):
        assert classify_intent("tell me about yourself") == QueryIntent.general


class TestExtractPathHint:
    def test_week_number_extracted(self):
        assert extract_path_hint("show me week 3") == "week3"

    def test_finale_extracted(self):
        assert extract_path_hint("What was covered in the finale?") == "finale"

    def test_no_hint_returns_none(self):
        assert extract_path_hint("tell me about yourself") is None


# ── analyse_query: LLM path ───────────────────────────────────────────────────

class TestAnalyseQuery:
    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_regex(self):
        """
        When get_llm_provider raises, analyse_query must return a valid
        QueryAnalysis derived from the regex fallback — never propagate.
        """
        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            side_effect=RuntimeError("provider unavailable"),
        ):
            result = await analyse_query("tell me about the Eshicare SA brief")

        assert isinstance(result, QueryAnalysis)
        # _SPECIFIC_RE should match "about the Eshicare SA brief"
        assert result.intent == QueryIntent.specific
        # Regex fallback never produces an expanded query
        assert result.expanded_query == ""

    @pytest.mark.asyncio
    async def test_llm_provider_complete_raises_falls_back_to_regex(self):
        """
        When provider.complete() raises (e.g. timeout), the fallback fires
        and the function returns a regex-based analysis without re-raising.
        """
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=TimeoutError("upstream timeout"))

        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await analyse_query("what projects have you built?")

        assert isinstance(result, QueryAnalysis)
        assert result.intent == QueryIntent.general
        assert result.expanded_query == ""

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_regex(self):
        """
        Malformed JSON in the LLM response triggers the except branch
        and the regex fallback is returned — no crash, no empty result.
        """
        mock_response = MagicMock()
        mock_response.content = "sorry, I cannot classify that query"

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await analyse_query("what projects have you built?")

        assert isinstance(result, QueryAnalysis)
        assert result.intent == QueryIntent.general
        assert result.expanded_query == ""

    @pytest.mark.asyncio
    async def test_empty_query_skips_llm(self):
        """
        An empty (or whitespace-only) query must return general immediately
        without making any LLM call.
        """
        with patch(
            "app.domains.answering.llm_provider.get_llm_provider"
        ) as mock_get:
            result = await analyse_query("   ")

        mock_get.assert_not_called()
        assert result.intent == QueryIntent.general

    @pytest.mark.asyncio
    async def test_llm_success_returns_structured_analysis(self):
        """
        Happy path: well-formed LLM JSON → intent, path_hints, expanded_query
        all populated correctly.
        """
        mock_response = MagicMock()
        mock_response.content = (
            '{"intent":"specific",'
            '"path_hints":["eshicare-sa-brief"],'
            '"expanded_query":"Eshicare SA brief pricing cost structure"}'
        )

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await analyse_query(
                "what does the Eshicare SA brief say about pricing?"
            )

        assert result.intent == QueryIntent.specific
        assert "eshicare-sa-brief" in result.path_hints
        assert "Eshicare" in result.expanded_query

    @pytest.mark.asyncio
    async def test_llm_success_strips_markdown_fences(self):
        """
        If the model wraps its JSON in markdown fences, the fences are stripped
        and the result is still parsed correctly.
        """
        mock_response = MagicMock()
        mock_response.content = (
            "```json\n"
            '{"intent":"general","path_hints":[],'
            '"expanded_query":"background skills experience"}\n'
            "```"
        )

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await analyse_query("tell me about yourself")

        assert result.intent == QueryIntent.general
        assert "experience" in result.expanded_query

    @pytest.mark.asyncio
    async def test_unknown_intent_value_coerces_to_general(self):
        """
        If the LLM returns an unrecognised intent string, the Pydantic
        field_validator coerces it to 'general' rather than raising.
        """
        mock_response = MagicMock()
        mock_response.content = (
            '{"intent":"code_search","path_hints":[],"expanded_query":"code"}'
        )

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value=mock_response)

        with patch(
            "app.domains.answering.llm_provider.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await analyse_query("show me the auth implementation")

        assert result.intent == QueryIntent.general
