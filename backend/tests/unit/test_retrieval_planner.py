from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.planner import RetrievalMode, build_retrieval_plan


class TestRetrievalPlanner:
    def test_file_specific_query_enters_implementation_mode(self):
        plan = build_retrieval_plan(
            query="Where is logout implemented in the dashboard?",
            intent=QueryIntent.file_specific,
            expanded_query="Find the logout implementation and the files that handle it.",
            top_k=8,
        )

        assert plan.mode == RetrievalMode.implementation
        assert plan.search_query.startswith("Find the logout implementation")
        assert "symbol" in plan.searched_layers
        assert "file" in plan.searched_layers
        assert "facts" in plan.searched_layers
        assert plan.fact_budget == 12
        assert "symbol" in plan.negative_evidence_scope

    def test_workspace_comparison_mode_is_selected_for_cross_project_query(self):
        plan = build_retrieval_plan(
            query="Walk me through authentication across all projects",
            intent=QueryIntent.architecture,
            workspace_scope=True,
        )

        assert plan.mode == RetrievalMode.workspace_comparison
        assert "graph" in plan.searched_layers
        assert "symbol" in plan.searched_layers

    def test_auth_queries_get_deterministic_expansion_without_llm_analysis(self):
        plan = build_retrieval_plan(
            query="How is authorization handled on Scaffold?",
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
        assert plan.fact_budget == 0
        assert "facts" not in plan.searched_layers

    def test_project_status_queries_expand_week_milestones_for_file_search(self):
        plan = build_retrieval_plan(
            query="This is week 6. What is left after authentication and loading the table?",
            intent=QueryIntent.general,
        )

        assert plan.mode == RetrievalMode.project_status
        assert "week6" in plan.search_query
        assert "planning" in plan.search_query
        assert "auth" in plan.search_query

    def test_change_review_queries_keep_file_layer_for_grounded_change_docs(self):
        plan = build_retrieval_plan(
            query="What changed recently in auth?",
            intent=QueryIntent.change_query,
        )

        assert plan.mode == RetrievalMode.change_review
        assert "file" in plan.searched_layers
        assert "file" in plan.negative_evidence_scope
        assert "logout" in plan.search_query


async def test_analyse_query_identity_skips_llm_expansion():
    from app.domains.retrieval.intent import QueryIntent, analyse_query

    r = await analyse_query("What is your name?")
    assert r.expanded_query == ""
    assert r.intent == QueryIntent.general
