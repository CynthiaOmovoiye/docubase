"""
Unit tests for app.domains.retrieval.intent — QueryIntent + classify_intent().

All tests are pure: no I/O, no DB, no LLM. classify_intent() is a regex
classifier that must be deterministic and fast.
"""

from app.domains.retrieval.intent import QueryIntent, classify_intent


class TestSpecificIntent:
    def test_pdf_file_reference(self):
        assert classify_intent("walk me through the Eshicare SA brief.pdf") == QueryIntent.specific

    def test_docx_file_reference(self):
        assert classify_intent("what does the requirements.docx say?") == QueryIntent.specific

    def test_md_file_reference(self):
        assert classify_intent("summarise README.md for me") == QueryIntent.specific

    def test_txt_file_reference(self):
        assert classify_intent("read notes.txt") == QueryIntent.specific

    def test_section_reference_with_in(self):
        assert classify_intent("what is in the authentication section?") == QueryIntent.specific

    def test_section_reference_with_about(self):
        assert classify_intent("tell me about the billing module") == QueryIntent.specific

    def test_section_reference_with_from(self):
        assert classify_intent("extract key points from the executive summary") == QueryIntent.specific

    def test_section_reference_with_see(self):
        assert classify_intent("see the onboarding guide for details") == QueryIntent.specific


class TestGeneralIntent:
    def test_simple_greeting(self):
        assert classify_intent("how are you") == QueryIntent.general

    def test_vague_question(self):
        assert classify_intent("tell me something interesting") == QueryIntent.general

    def test_identity_question(self):
        assert classify_intent("tell me about yourself") == QueryIntent.general

    def test_empty_string(self):
        assert classify_intent("") == QueryIntent.general

    def test_whitespace_only(self):
        assert classify_intent("   ") == QueryIntent.general

    def test_what_is_your_name(self):
        assert classify_intent("what is your name?") == QueryIntent.general

    def test_broad_experience_question(self):
        assert classify_intent("what is your experience with Python?") == QueryIntent.general

    def test_short_query(self):
        assert classify_intent("authentication") == QueryIntent.general


class TestEdgeCases:
    def test_only_two_intent_values(self):
        assert set(QueryIntent) == {QueryIntent.specific, QueryIntent.general}

    def test_case_insensitive_file_extension(self):
        assert classify_intent("open the project.PDF") == QueryIntent.specific

    def test_returns_general_for_no_match(self):
        assert classify_intent("how does authentication work?") == QueryIntent.general
