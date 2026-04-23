"""
Unit tests for retrieval score boosts in app.domains.retrieval.router.

The router now applies score adjustments by RetrievalMode, while QueryIntent
still controls top_k defaults. These tests keep the retrieval tuning contract
explicit without pinning production code to the older intent-boost map.
"""

import pytest

from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.planner import RetrievalMode
from app.domains.retrieval.router import (
    _INTENT_TOP_K,
    _MODE_SCORE_ADJUSTMENTS,
    _build_mode_boost_sql,
)


class TestBuildModeBoostSql:
    def test_returns_empty_for_general_mode(self):
        result = _build_mode_boost_sql(RetrievalMode.general)
        assert result == ""

    def test_contains_mode_adjustment_value(self):
        result = _build_mode_boost_sql(RetrievalMode.implementation)
        assert "0.35" in result

    def test_change_review_boosts_change_entry(self):
        result = _build_mode_boost_sql(RetrievalMode.change_review)
        assert "change_entry" in result
        assert "CASE" in result
        assert "WHEN" in result

    def test_risk_review_boosts_risk_note(self):
        result = _build_mode_boost_sql(RetrievalMode.risk_review)
        assert "risk_note" in result

    def test_architecture_boosts_structural_types(self):
        result = _build_mode_boost_sql(RetrievalMode.architecture)
        assert "module_description" in result
        assert "decision_record" in result
        assert "feature_summary" in result

    def test_onboarding_boosts_memory_brief_and_onboarding_artifacts(self):
        result = _build_mode_boost_sql(RetrievalMode.onboarding)
        assert "memory_brief" in result
        assert "onboarding_map" in result
        assert "module_description" in result

    def test_implementation_boosts_code_snippet_and_module(self):
        result = _build_mode_boost_sql(RetrievalMode.implementation)
        assert "code_snippet" in result
        assert "module_description" in result

    def test_sql_contains_else_zero(self):
        """ELSE 0 must be present to avoid null score additions."""
        for mode in [RetrievalMode.change_review, RetrievalMode.risk_review, RetrievalMode.architecture]:
            result = _build_mode_boost_sql(mode)
            assert "ELSE 0" in result

    def test_no_user_data_in_sql(self):
        """Boost SQL must never interpolate user data, only literal config keys."""
        for mode in RetrievalMode:
            result = _build_mode_boost_sql(mode)
            # Should only contain known chunk type names (no format strings left open)
            assert "{" not in result
            assert "}" not in result


class TestModeScoreAdjustments:
    def test_all_modes_have_entries(self):
        for mode in RetrievalMode:
            assert mode in _MODE_SCORE_ADJUSTMENTS, f"{mode} missing from _MODE_SCORE_ADJUSTMENTS"

    def test_general_has_no_adjustments(self):
        assert _MODE_SCORE_ADJUSTMENTS[RetrievalMode.general] == {}

    def test_change_review_boosts_change_entry(self):
        assert _MODE_SCORE_ADJUSTMENTS[RetrievalMode.change_review]["change_entry"] > 0

    def test_risk_review_boosts_risk_note(self):
        assert _MODE_SCORE_ADJUSTMENTS[RetrievalMode.risk_review]["risk_note"] > 0

    def test_architecture_boosts_multiple_types(self):
        boosted = _MODE_SCORE_ADJUSTMENTS[RetrievalMode.architecture]
        assert "module_description" in boosted
        assert "decision_record" in boosted
        assert "feature_summary" in boosted

    def test_onboarding_includes_memory_brief(self):
        assert "memory_brief" in _MODE_SCORE_ADJUSTMENTS[RetrievalMode.onboarding]
        assert "onboarding_map" in _MODE_SCORE_ADJUSTMENTS[RetrievalMode.onboarding]

    def test_no_duplicate_types_per_mode(self):
        for mode, adjustments in _MODE_SCORE_ADJUSTMENTS.items():
            keys = list(adjustments)
            assert len(keys) == len(set(keys)), f"Duplicates in {mode} score adjustments"

    def test_all_adjusted_types_are_strings_and_scores_are_numbers(self):
        for mode, adjustments in _MODE_SCORE_ADJUSTMENTS.items():
            for chunk_type, adjustment in adjustments.items():
                assert isinstance(chunk_type, str), f"Non-string type in {mode}: {chunk_type!r}"
                assert isinstance(adjustment, float), f"Non-float score in {mode}: {adjustment!r}"


class TestIntentTopK:
    def test_all_intents_have_top_k(self):
        for intent in QueryIntent:
            assert intent in _INTENT_TOP_K, f"{intent} missing from _INTENT_TOP_K"

    def test_onboarding_has_highest_top_k(self):
        """Onboarding needs the most context to give a full reading order."""
        assert _INTENT_TOP_K[QueryIntent.onboarding] >= 12

    def test_change_query_gets_more_than_default(self):
        """Change queries benefit from more chunks to cover multiple weeks."""
        assert _INTENT_TOP_K[QueryIntent.change_query] > 8

    def test_all_top_k_values_are_positive_ints(self):
        for intent, k in _INTENT_TOP_K.items():
            assert isinstance(k, int), f"top_k for {intent} is not int: {k!r}"
            assert k > 0, f"top_k for {intent} is not positive: {k}"

    def test_top_k_values_are_reasonable(self):
        """top_k should be between 4 and 32 for all intents."""
        for intent, k in _INTENT_TOP_K.items():
            assert 4 <= k <= 32, f"top_k for {intent} is out of expected range: {k}"


class TestBoostValues:
    def test_adjustments_are_meaningful_but_not_dominating(self):
        """
        Adjustments should reorder similar results without completely
        overriding semantic/lexical similarity.
        """
        for adjustments in _MODE_SCORE_ADJUSTMENTS.values():
            for value in adjustments.values():
                assert -0.4 <= value <= 0.4
