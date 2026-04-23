"""
Unit tests for app.domains.retrieval.intent — QueryIntent + classify_intent().

All tests are pure: no I/O, no DB, no LLM. classify_intent() is a regex
classifier that must be deterministic and fast.
"""

import pytest
from app.domains.retrieval.intent import QueryIntent, classify_intent


# ── change_query ──────────────────────────────────────────────────────────────

class TestChangeQueryIntent:
    def test_what_changed(self):
        assert classify_intent("what changed last week?") == QueryIntent.change_query

    def test_recent_changes(self):
        assert classify_intent("Show me recent changes to the codebase") == QueryIntent.change_query

    def test_last_month(self):
        assert classify_intent("What happened last month?") == QueryIntent.change_query

    def test_commits(self):
        assert classify_intent("List the latest commits") == QueryIntent.change_query

    def test_whats_new(self):
        assert classify_intent("what's new in this project?") == QueryIntent.change_query

    def test_recently_updated(self):
        assert classify_intent("Which modules were recently updated?") == QueryIntent.change_query

    def test_this_week(self):
        assert classify_intent("What happened this week?") == QueryIntent.change_query

    def test_activity(self):
        assert classify_intent("show me recent activity") == QueryIntent.change_query


# ── risk_query ────────────────────────────────────────────────────────────────

class TestRiskQueryIntent:
    def test_risky(self):
        assert classify_intent("What are the risky parts?") == QueryIntent.risk_query

    def test_fragile(self):
        assert classify_intent("Which modules are fragile?") == QueryIntent.risk_query

    def test_could_break(self):
        assert classify_intent("What could break under load?") == QueryIntent.risk_query

    def test_technical_debt(self):
        assert classify_intent("Where is the technical debt?") == QueryIntent.risk_query

    def test_todo_fixme(self):
        assert classify_intent("Show me all TODO and FIXME comments") == QueryIntent.risk_query

    def test_problematic(self):
        assert classify_intent("What areas are problematic?") == QueryIntent.risk_query

    def test_unstable(self):
        assert classify_intent("Which parts are unstable?") == QueryIntent.risk_query


# ── architecture ──────────────────────────────────────────────────────────────

class TestArchitectureIntent:
    def test_architecture(self):
        assert classify_intent("Explain the architecture") == QueryIntent.architecture

    def test_overview(self):
        assert classify_intent("Give me a system overview") == QueryIntent.architecture

    def test_structure(self):
        assert classify_intent("How is this codebase structured?") == QueryIntent.architecture

    def test_high_level(self):
        assert classify_intent("Walk me through the high-level design") == QueryIntent.architecture

    def test_system_design(self):
        assert classify_intent("Describe the system design") == QueryIntent.architecture

    def test_tech_stack(self):
        assert classify_intent("What is the tech stack?") == QueryIntent.architecture

    def test_data_flow(self):
        assert classify_intent("Explain the data flow") == QueryIntent.architecture

    def test_key_components(self):
        assert classify_intent("What are the main components?") == QueryIntent.architecture


# ── onboarding ────────────────────────────────────────────────────────────────

class TestOnboardingIntent:
    def test_where_to_start(self):
        assert classify_intent("Where should I start as a new engineer?") == QueryIntent.onboarding

    def test_new_developer(self):
        assert classify_intent("I'm a new developer, how do I get started?") == QueryIntent.onboarding

    def test_getting_started(self):
        assert classify_intent("Getting started guide") == QueryIntent.onboarding

    def test_introduce_me(self):
        assert classify_intent("Introduce me to this codebase") == QueryIntent.onboarding

    def test_new_hire(self):
        assert classify_intent("What should a new hire read first?") == QueryIntent.onboarding

    def test_just_joined(self):
        assert classify_intent("I just joined the team, how do I understand this?") == QueryIntent.onboarding


# ── file_specific ─────────────────────────────────────────────────────────────

class TestFileSpecificIntent:
    def test_python_extension(self):
        assert classify_intent("explain service.py") == QueryIntent.file_specific

    def test_typescript_extension(self):
        assert classify_intent("what does index.ts do?") == QueryIntent.file_specific

    def test_tsx_extension(self):
        assert classify_intent("explain the TwinDetailPage.tsx component") == QueryIntent.file_specific

    def test_path_with_slash(self):
        # Note: "how does auth/service.py work" may hit architecture first due to
        # "how does...work" pattern — this is an accepted overlap
        assert classify_intent("read app/core/config.py") == QueryIntent.file_specific

    def test_go_extension(self):
        assert classify_intent("what is main.go doing?") == QueryIntent.file_specific

    def test_yaml_extension(self):
        assert classify_intent("explain docker-compose.yaml") == QueryIntent.file_specific


# ── general ───────────────────────────────────────────────────────────────────

class TestGeneralIntent:
    def test_simple_greeting(self):
        assert classify_intent("how are you") == QueryIntent.general

    def test_vague_question(self):
        assert classify_intent("Tell me something interesting") == QueryIntent.general

    def test_specific_function(self):
        # "How does X work?" matches the architecture "how does...work" pattern — correct behavior
        assert classify_intent("How does authentication work?") == QueryIntent.architecture

    def test_short_query(self):
        # "dependencies" matches the architecture pattern — tech-stack questions are architecture
        assert classify_intent("dependencies") == QueryIntent.architecture


# ── edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        assert classify_intent("") == QueryIntent.general

    def test_whitespace_only(self):
        assert classify_intent("   ") == QueryIntent.general

    def test_change_beats_general(self):
        """Change query words should win over generic phrasing."""
        result = classify_intent("show me what changed recently")
        assert result == QueryIntent.change_query

    def test_risk_beats_general(self):
        result = classify_intent("are there any risks here?")
        assert result == QueryIntent.risk_query

    def test_change_query_precedes_risk(self):
        """
        When both change and risk patterns appear, change_query wins
        (it's evaluated first in the classifier).
        """
        result = classify_intent("what changed that caused this risky behaviour last week?")
        assert result == QueryIntent.change_query

    def test_case_insensitive(self):
        assert classify_intent("WHAT CHANGED LAST WEEK") == QueryIntent.change_query
        assert classify_intent("ARCHITECTURE OVERVIEW") == QueryIntent.architecture
