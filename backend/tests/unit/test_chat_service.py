from app.domains.chat.service import (
    _build_no_grounding_response,
    _build_workspace_scope_response,
    _build_workspace_topic_gap_response,
    _is_any_project_query,
    _resolve_workspace_doctwin_from_query,
)


class TestNoGroundingFallback:
    def test_greeting_with_no_sources_is_honest(self):
        response = _build_no_grounding_response(
            query="hi",
            scope_name="This Project",
            sources=[],
            has_context_chunks=False,
            has_memory_brief=False,
            is_workspace_scope=False,
        )

        assert response is not None
        assert "don't have any knowledge sources attached" in response
        assert "This Project" in response

    def test_source_query_with_no_sources_mentions_missing_sources(self):
        response = _build_no_grounding_response(
            query="what do you have?",
            scope_name="This Project",
            sources=[],
            has_context_chunks=False,
            has_memory_brief=False,
            is_workspace_scope=False,
        )

        assert response is not None
        assert "don't have any knowledge sources attached" in response
        assert "Drive file, document, PDF, website, or notes source" in response

    def test_question_with_only_non_ready_sources_blocks_answer(self):
        response = _build_no_grounding_response(
            query="tell me about this project",
            scope_name="This Project",
            sources=[
                {"name": "production", "source_type": "google_drive", "status": "processing"},
                {"name": "resume", "source_type": "pdf", "status": "failed"},
            ],
            has_context_chunks=False,
            has_memory_brief=False,
            is_workspace_scope=False,
        )

        assert response is not None
        assert "none are ready yet" in response
        assert "production (processing)" in response
        assert "resume (failed)" in response

    def test_ready_sources_without_grounding_refuses_to_guess(self):
        response = _build_no_grounding_response(
            query="yea details on the architecture",
            scope_name="This Project",
            sources=[
                {"name": "production", "source_type": "google_drive", "status": "ready"},
            ],
            has_context_chunks=False,
            has_memory_brief=False,
            is_workspace_scope=False,
        )

        assert response is not None
        assert "indexed content" in response.lower()
        assert "This Project" in response

    def test_greeting_with_ready_sources_does_not_short_circuit(self):
        response = _build_no_grounding_response(
            query="hello",
            scope_name="This Project",
            sources=[
                {"name": "production", "source_type": "google_drive", "status": "ready"},
            ],
            has_context_chunks=False,
            has_memory_brief=False,
            is_workspace_scope=False,
        )

        assert response is None


class TestWorkspaceScopeResponse:
    def test_greeting_and_self_intro_do_not_short_circuit(self):
        """Regressions: "Hi, my name is …" must reach the LLM, not deterministic workspace copy."""
        assert _build_workspace_scope_response("Hi!", {}) is None
        assert (
            _build_workspace_scope_response(
                "Hi, my name is Alex",
                {
                    "workspace_name": "W",
                    "total_twins": 1,
                    "ready_twins": 1,
                    "active_twins": 1,
                    "twins": [
                        {
                            "name": "Twin A",
                            "description": None,
                            "is_active": True,
                            "source_count": 1,
                            "ready_source_count": 1,
                            "ready_source_names": ["x"],
                        }
                    ],
                },
            )
            is None
        )

    def test_workspace_coverage_query_lists_all_twins(self):
        response = _build_workspace_scope_response(
            "what projects can you help with?",
            {
                "workspace_name": "Client Workspace",
                "total_twins": 3,
                "ready_twins": 2,
                "active_twins": 3,
                "twins": [
                    {
                        "name": "Alpha API",
                        "description": "Backend API for Client Alpha.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 1,
                        "ready_source_names": ["alpha-api"],
                    },
                    {
                        "name": "Portfolio Twin",
                        "description": None,
                        "is_active": True,
                        "source_count": 2,
                        "ready_source_count": 1,
                        "ready_source_names": ["portfolio.pdf"],
                    },
                    {
                        "name": "Docs Twin",
                        "description": "Internal docs and onboarding notes.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 0,
                        "ready_source_names": [],
                    },
                ],
            },
        )

        assert response is not None
        assert "**3 twins**" in response
        assert "**Alpha API**" in response
        assert "**Portfolio Twin**" in response
        assert "**Docs Twin**" in response
        assert "portfolio.pdf" in response

    def test_workspace_doctwin_count_query_reports_ready_and_active_counts(self):
        response = _build_workspace_scope_response(
            "how many twins are you serving?",
            {
                "workspace_name": "Studio",
                "total_twins": 2,
                "ready_twins": 1,
                "active_twins": 1,
                "twins": [
                    {
                        "name": "Main Project",
                        "description": "Primary product twin.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 1,
                        "ready_source_names": ["production"],
                    },
                    {
                        "name": "Archive Twin",
                        "description": "Older materials.",
                        "is_active": False,
                        "source_count": 1,
                        "ready_source_count": 0,
                        "ready_source_names": [],
                    },
                ],
            },
        )

        assert response is not None
        assert "**2 twins**" in response
        assert "**1** has ready sources" in response
        assert "**1** is marked active" in response
        assert "Inactive." in response

    def test_non_workspace_meta_query_returns_none(self):
        response = _build_workspace_scope_response(
            "tell me about the auth architecture",
            {
                "workspace_name": "Studio",
                "total_twins": 1,
                "ready_twins": 1,
                "active_twins": 1,
                "twins": [
                    {
                        "name": "Main Project",
                        "description": "Primary product twin.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 1,
                        "ready_source_names": ["production"],
                    },
                ],
            },
        )

        assert response is None


class TestWorkspaceRoutingModes:
    def test_resolves_named_project_from_workspace_query(self):
        match = _resolve_workspace_doctwin_from_query(
            "walk me through the auth implementation on Alpha API project",
            {
                "workspace_name": "Studio",
                "twins": [
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "slug": "alpha-api",
                        "canonical_name": "Alpha API",
                        "name": "Alpha API",
                        "description": "Backend service.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 1,
                        "ready_source_names": ["alpha-api"],
                    },
                    {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "slug": "beta-web",
                        "canonical_name": "Beta Web",
                        "name": "Beta Web",
                        "description": "Frontend app.",
                        "is_active": True,
                        "source_count": 1,
                        "ready_source_count": 1,
                        "ready_source_names": ["beta-web"],
                    },
                ],
            },
        )

        assert match is not None
        assert match["name"] == "Alpha API"

    def test_detects_any_project_query(self):
        assert _is_any_project_query("walk me through any of the authentications implemented")
        assert not _is_any_project_query("walk me through the authentication implementations")

    def test_workspace_topic_gap_response_labels_each_project(self):
        response = _build_workspace_topic_gap_response(
            "walk me through the authentication implementations",
            "Product Studio",
            [
                {
                    "name": "Alpha API",
                    "ready_source_count": 1,
                    "chunks": [],
                },
                {
                    "name": "Beta Web",
                    "ready_source_count": 0,
                    "chunks": [],
                },
            ],
        )

        assert "## Alpha API" in response
        assert "## Beta Web" in response
        assert "authentication implementation" in response
        assert "does not have any ready sources yet" in response
