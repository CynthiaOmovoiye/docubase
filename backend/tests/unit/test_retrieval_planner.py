from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.planner import RetrievalMode, build_retrieval_plan


class TestRetrievalPlanner:
    def test_specific_intent_sets_higher_top_k(self):
        plan = build_retrieval_plan(
            query="walk me through the Eshicare SA brief.pdf",
            intent=QueryIntent.specific,
            top_k=12,
        )
        assert plan.top_k == 12

    def test_auth_queries_get_deterministic_expansion_without_llm_analysis(self):
        plan = build_retrieval_plan(
            query="How is authorization handled?",
            intent=QueryIntent.general,
        )

        assert plan.mode == RetrievalMode.implementation
        assert "authentication" in plan.search_query
        assert "refresh token" in plan.search_query
        assert "current_user" in plan.search_query

    def test_recruiter_summary_reduces_graph_budget(self):
        plan = build_retrieval_plan(
            query="Tell me this candidate's experience with Python",
            intent=QueryIntent.general,
        )

        assert plan.mode == RetrievalMode.recruiter_summary
        assert plan.graph_budget == 2
        assert plan.symbol_budget >= 7

    def test_project_status_queries_expand_week_milestones_for_file_search(self):
        plan = build_retrieval_plan(
            query="This is week 6. What is left after authentication and loading the table?",
            intent=QueryIntent.general,
        )

        assert plan.mode == RetrievalMode.project_status
        assert "week6" in plan.search_query
        assert "planning" in plan.search_query
        assert "auth" in plan.search_query

    def test_workspace_comparison_mode_is_selected_for_cross_project_query(self):
        plan = build_retrieval_plan(
            query="Walk me through authentication across all projects",
            intent=QueryIntent.general,
            workspace_scope=True,
        )

        assert plan.mode == RetrievalMode.workspace_comparison

    def test_general_intent_uses_vector_and_lexical_layers(self):
        plan = build_retrieval_plan(
            query="tell me about yourself",
            intent=QueryIntent.general,
        )
        assert "vector" in plan.searched_layers
        assert "lexical" in plan.searched_layers

    def test_specific_intent_keeps_same_layers(self):
        plan = build_retrieval_plan(
            query="summarise the onboarding.md file",
            intent=QueryIntent.specific,
        )
        assert "vector" in plan.searched_layers
        assert "lexical" in plan.searched_layers


async def test_analyse_query_identity_skips_llm_expansion():
    from app.domains.retrieval.intent import QueryIntent, analyse_query

    r = await analyse_query("What is your name?")
    assert r.expanded_query == ""
    assert r.intent == QueryIntent.general
