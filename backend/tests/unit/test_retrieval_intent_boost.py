"""
Unit tests for the simplified document-only retrieval contract.

The router now uses just two intents (specific / general) with fixed top_k values.
Mode score adjustments have been removed — scoring is cosine + source diversity demotion.
"""

from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.router import _INTENT_TOP_K


class TestIntentTopK:
    def test_both_intents_have_entries(self):
        assert QueryIntent.specific in _INTENT_TOP_K
        assert QueryIntent.general in _INTENT_TOP_K

    def test_specific_gets_more_chunks_than_general(self):
        """Named-document queries need more chunks to answer precisely."""
        assert _INTENT_TOP_K[QueryIntent.specific] > _INTENT_TOP_K[QueryIntent.general]

    def test_all_top_k_values_are_positive_ints(self):
        for intent, k in _INTENT_TOP_K.items():
            assert isinstance(k, int), f"top_k for {intent} is not int: {k!r}"
            assert k > 0, f"top_k for {intent} is not positive"

    def test_top_k_values_are_reasonable(self):
        """top_k should be between 4 and 32 for all intents."""
        for intent, k in _INTENT_TOP_K.items():
            assert 4 <= k <= 32, f"top_k for {intent} out of range: {k}"

    def test_no_code_centric_intents_remain(self):
        """Retired code-centric intent names must not appear in _INTENT_TOP_K."""
        retired = {"change_query", "risk_query", "architecture", "onboarding", "file_specific"}
        for intent in _INTENT_TOP_K:
            assert intent.value not in retired, f"Retired intent in _INTENT_TOP_K: {intent}"
