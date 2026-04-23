from app.domains.answering.verifier import (
    verify_single_project_answer,
    verify_workspace_answer,
)
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    EvidenceSymbolRef,
    RetrievalEvidencePacket,
)
from app.domains.retrieval.planner import RetrievalMode


def _make_packet(
    *,
    path: str = "app/auth.py",
    symbol_name: str = "get_current_user",
    qualified_name: str = "auth.get_current_user",
) -> RetrievalEvidencePacket:
    return RetrievalEvidencePacket(
        query="how is auth implemented?",
        search_query="how is auth implemented?",
        lexical_query="how is auth implemented?",
        intent="architecture",
        mode=RetrievalMode.implementation,
        files=[EvidenceFileRef(path=path, reasons=["file:lexical"])],
        symbols=[
            EvidenceSymbolRef(
                symbol_name=symbol_name,
                qualified_name=qualified_name,
                symbol_kind="function",
                path=path,
                reasons=["symbol:lexical"],
            )
        ],
        searched_layers=["vector", "lexical", "file", "symbol"],
        negative_evidence_scope=["symbol", "file", "lexical", "path"],
        graph_edges=[{"source": "router", "relationship": "calls", "target": "auth.get_current_user"}],
        chunks=[
            {
                "chunk_id": "chunk-1",
                "chunk_type": "module_description",
                "source_ref": path,
                "content": "Requests pass through get_current_user before route handling.",
                "match_reasons": ["file:lexical"],
            }
        ],
    )


def test_single_project_verifier_requests_retry_when_answer_has_no_grounded_anchor():
    result = verify_single_project_answer(
        answer="Authorization uses token verification and owner checks.",
        doctwin_name="Scaffold",
        packet=_make_packet(),
        allow_retry=True,
    )

    assert not result.verified
    assert result.retry_hint is not None
    assert "missing_grounded_anchor" in result.issues


def test_single_project_verifier_rewrites_after_retry_budget_is_spent():
    packet = _make_packet()
    packet.query = "how is billing implemented?"
    result = verify_single_project_answer(
        answer="Authorization uses token verification and owner checks.",
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## Grounded evidence" in result.content
    assert "`app/auth.py`" in result.content
    assert "`auth.get_current_user`" in result.content


def test_single_project_auth_fallback_explains_identity_and_owner_checks():
    packet = _make_packet(path="scaffold/core/auth.py")
    packet.query = "How is authorization handled?"
    packet.chunks = [
        {
            "chunk_id": "chunk-1",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/core/auth.py",
            "content": "async def get_current_user(...):\n    payload = decode_access_token(token)",
        },
        {
            "chunk_id": "chunk-2",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/api/v1/routes/projects.py",
            "content": (
                "if not project or project.owner_id != current_user.id:\n"
                "    raise HTTPException(status_code=404)"
            ),
        },
    ]

    result = verify_single_project_answer(
        answer="Authorization uses invented `DoesNotExist` checks.",
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## Identity Check" in result.content
    assert "## Authorization" in result.content
    assert "owner_id" in result.content
    assert "global RBAC" in result.content


def test_single_project_verifier_bounds_negative_claims():
    result = verify_single_project_answer(
        answer="There is no RBAC layer here.",
        doctwin_name="Scaffold",
        packet=_make_packet(),
        allow_retry=False,
    )

    assert "## Bounds" in result.content
    assert "symbol, file, lexical, path" in result.content


def test_append_negative_bounds_lists_missing_evidence_gaps():
    from app.domains.answering.verifier import _append_negative_bounds

    p = _make_packet()
    p.missing_evidence = ["refresh rotation not indexed"]
    out = _append_negative_bounds("There is no RBAC layer here.", p)
    assert "## Grounded gaps (from retrieval)" in out
    assert "refresh rotation not indexed" in out


def test_single_project_verifier_flags_strong_negative_denying_present_route_facts():
    from app.domains.answering.verifier import _has_contradicted_absence_claim

    packet = RetrievalEvidencePacket(
        query="routing?",
        search_query="routing",
        lexical_query="routing",
        intent=None,
        mode=RetrievalMode.implementation,
        facts=[
            {
                "fact_type": "route",
                "path": "app/routes.py",
                "summary": "GET /health",
                "subject": "/health",
                "predicate": "defines",
                "object_ref": "",
                "source_id": "s",
                "fact_id": "f",
                "score": 1.0,
            }
        ],
        chunks=[],
    )
    assert _has_contradicted_absence_claim(
        "There are no routes in this service.",
        packet,
    )


def test_single_project_verifier_allows_file_paths_declared_only_on_implementation_facts():
    """Phase 6 — fact rows extend the allowed reference namespace."""
    packet = RetrievalEvidencePacket(
        query="where is the handler?",
        search_query="handler",
        lexical_query="handler",
        intent=None,
        mode=RetrievalMode.implementation,
        files=[],
        symbols=[],
        facts=[
            {
                "path": "only/from/facts.py",
                "fact_type": "handler",
                "subject": "handle_ping",
                "predicate": "defined_in",
                "object_ref": "",
                "summary": "health check",
            }
        ],
        chunks=[],
    )
    result = verify_single_project_answer(
        answer="See `only/from/facts.py` where `handle_ping` is defined.",
        doctwin_name="Twin",
        packet=packet,
        allow_retry=False,
    )
    assert result.verified
    assert not result.rewritten


def test_workspace_verifier_requests_retry_when_project_labels_are_missing():
    project_contexts = [
        {"name": "Alpha API", "chunks": [{"chunk_id": "1"}], "evidence_packet": _make_packet(path="alpha/auth.py")},
        {"name": "Beta Web", "chunks": [{"chunk_id": "2"}], "evidence_packet": _make_packet(path="beta/auth.ts")},
    ]

    result = verify_workspace_answer(
        answer="Alpha API uses owner checks. Beta Web uses middleware guards.",
        workspace_name="Studio",
        project_contexts=project_contexts,
        allow_retry=True,
    )

    assert not result.verified
    assert result.retry_hint is not None
    assert "missing_project_labels" in result.issues


def test_workspace_verifier_rewrites_cross_project_leakage_after_retry_budget_is_spent():
    project_contexts = [
        {"name": "Alpha API", "chunks": [{"chunk_id": "1"}], "evidence_packet": _make_packet(path="alpha/auth.py")},
        {"name": "Beta Web", "chunks": [{"chunk_id": "2"}], "evidence_packet": _make_packet(path="beta/auth.ts")},
    ]

    result = verify_workspace_answer(
        answer=(
            "## Alpha API\n"
            "Authentication is handled in Beta Web.\n\n"
            "## Beta Web\n"
            "Authentication is handled in `beta/auth.ts`.\n"
        ),
        workspace_name="Studio",
        project_contexts=project_contexts,
        allow_retry=False,
    )

    assert result.rewritten
    assert "Here is the authentication implementation I can confirm per project" in result.content
    assert "## Alpha API" in result.content
    assert "## Beta Web" in result.content
    assert "Grounded files:" not in result.content


def test_workspace_auth_fallback_explains_flows_instead_of_dumping_refs():
    scaffold_packet = _make_packet(path="scaffold/core/auth.py")
    scaffold_packet.query = "Walk me through the authentication implementations across all covered projects."
    scaffold_packet.files = [
        EvidenceFileRef(path="scaffold/core/auth.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/api/v1/routes/auth.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="frontend/src/pages/LoginPage.tsx", reasons=["file:lexical"]),
        EvidenceFileRef(path="frontend/src/App.tsx", reasons=["file:lexical"]),
    ]
    scaffold_packet.symbols = [
        EvidenceSymbolRef(
            symbol_name="get_current_user",
            qualified_name="get_current_user",
            symbol_kind="function",
            path="scaffold/core/auth.py",
            reasons=["symbol:lexical"],
        ),
        EvidenceSymbolRef(
            symbol_name="register@POST:/register",
            qualified_name="register@POST:/register",
            symbol_kind="route",
            path="scaffold/api/v1/routes/auth.py",
            reasons=["symbol:route"],
        ),
        EvidenceSymbolRef(
            symbol_name="ProtectedRoute",
            qualified_name="ProtectedRoute",
            symbol_kind="component",
            path="frontend/src/App.tsx",
            reasons=["symbol:lexical"],
        ),
    ]
    scaffold_packet.chunks = [
        {
            "chunk_id": "scaffold-auth",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/core/auth.py",
            "content": (
                "oauth2_scheme = OAuth2PasswordBearer(tokenUrl=\"/api/v1/auth/login\")\n"
                "def create_access_token(data: dict) -> str: ...\n"
                "def create_refresh_token(data: dict) -> str: ...\n"
                "async def get_current_user(token: str = Depends(oauth2_scheme)): ..."
            ),
        },
        {
            "chunk_id": "scaffold-routes",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/api/v1/routes/auth.py",
            "content": (
                "@router.post(\"/register\")\nasync def register(...): ...\n"
                "@router.post(\"/login\")\nasync def login(...): ...\n"
                "@router.post(\"/refresh\")\nasync def refresh_tokens(...): ...\n"
                "@router.get(\"/me\")\nasync def me(current_user = Depends(get_current_user)): ..."
            ),
        },
        {
            "chunk_id": "scaffold-frontend",
            "chunk_type": "code_snippet",
            "source_ref": "frontend/src/pages/LoginPage.tsx",
            "content": "await authApi.login(email, password); setSessionTokens(tokens);",
        },
        {
            "chunk_id": "scaffold-app",
            "chunk_type": "code_snippet",
            "source_ref": "frontend/src/App.tsx",
            "content": "function ProtectedRoute() { if (!isAuthenticated()) return <Navigate to=\"/login\" /> }",
        },
    ]

    course_packet = _make_packet(
        path="backend/api/main.py",
        symbol_name="get_current_user_id",
        qualified_name="get_current_user_id",
    )
    course_packet.query = scaffold_packet.query
    course_packet.files = [
        EvidenceFileRef(path="backend/api/main.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="community_contributions/jwt_token_60s_fix.md", reasons=["lexical"]),
    ]
    course_packet.symbols = [
        EvidenceSymbolRef(
            symbol_name="get_current_user_id",
            qualified_name="get_current_user_id",
            symbol_kind="function",
            path="backend/api/main.py",
            reasons=["symbol:lexical"],
        )
    ]
    course_packet.chunks = [
        {
            "chunk_id": "course-main",
            "chunk_type": "code_snippet",
            "source_ref": "backend/api/main.py",
            "content": (
                "from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer\n"
                "clerk_config = ClerkConfig(jwks_url=os.getenv('CLERK_JWKS_URL'))\n"
                "async def get_current_user_id(creds = Depends(clerk_guard)): return creds.decoded['sub']"
            ),
        },
        {
            "chunk_id": "course-jwt",
            "chunk_type": "module_description",
            "source_ref": "community_contributions/jwt_token_60s_fix.md",
            "content": "Clerk JWT tokens can expire during SSE; reconnect with getToken() to fetch a fresh JWT.",
        },
    ]

    project_contexts = [
        {"name": "Scaffold", "chunks": scaffold_packet.chunks, "evidence_packet": scaffold_packet},
        {"name": "someother chat", "chunks": course_packet.chunks, "evidence_packet": course_packet},
        {"name": "docbase", "chunks": [], "evidence_packet": None, "status_note": "no sources attached"},
    ]

    result = verify_workspace_answer(
        answer=(
            "## Scaffold\nAuth is in `made/up.py`.\n\n"
            "## someother chat\nAuth is in `missing/auth.py`.\n\n"
            "## docbase\nNo sources."
        ),
        workspace_name="Cynthia",
        project_contexts=project_contexts,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## Scaffold" in result.content
    assert "JWT-based backend authentication" in result.content
    assert "registration, login, token refresh, current-user lookup" in result.content
    assert "frontend registration/signup page" in result.content
    assert "## someother chat" in result.content
    assert "Clerk appears to be the authentication provider" in result.content
    assert "`get_current_user_id` extracts user identity" in result.content
    assert "Grounded files:" not in result.content
    assert "## docbase" in result.content


def test_single_project_verifier_accepts_route_style_symbols():
    packet = _make_packet(symbol_name="logout@POST:/logout", qualified_name="logout@POST:/logout")

    result = verify_single_project_answer(
        answer=(
            "Authentication is grounded in `app/auth.py`.\n"
            "Key symbols: `logout@POST:/logout`"
        ),
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=True,
    )

    assert result.verified
    assert result.retry_hint is None


def test_single_project_verifier_rejects_unsupported_code_block():
    result = verify_single_project_answer(
        answer=(
            "Here is the flow.\n\n"
            "```python\n"
            "def decodeJwtPayload(token):\n"
            "    pass\n"
            "```"
        ),
        doctwin_name="Scaffold",
        packet=_make_packet(),
        allow_retry=False,
    )

    assert result.rewritten
    assert "decodeJwtPayload" not in result.content


def test_single_project_verifier_rejects_placeholder_code_even_when_signature_matches():
    packet = _make_packet()
    packet.chunks = [
        {
            "chunk_id": "chunk-1",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/core/auth.py",
            "content": (
                "async def get_current_user(\n"
                "    token: str = Depends(oauth2_scheme),\n"
                "    db: AsyncSession = Depends(get_db),\n"
                "):\n"
                "    payload = decode_access_token(token)\n"
                "    return user\n"
            ),
            "match_reasons": ["symbol:get_current_user"],
        }
    ]

    result = verify_single_project_answer(
        answer=(
            "Grounded in `scaffold/core/auth.py`.\n\n"
            "```python\n"
            "async def get_current_user(\n"
            "    token: str = Depends(oauth2_scheme),\n"
            "    db: AsyncSession = Depends(get_db),\n"
            "):\n"
            "    # Logic to decode the token and retrieve the user\n"
            "```\n"
        ),
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=True,
    )

    assert not result.verified
    assert "unsupported_code_block" in result.issues


def test_single_project_verifier_rejects_absence_claim_contradicted_by_packet():
    packet = _make_packet(path="frontend/src/App.tsx")
    packet.chunks = [
        {
            "chunk_id": "chunk-1",
            "chunk_type": "code_snippet",
            "source_ref": "frontend/src/App.tsx",
            "content": "<Route element={<ProtectedRoute />}><Route path=\"/\" element={<DashboardPage />} /></Route>",
        },
        {
            "chunk_id": "chunk-2",
            "chunk_type": "code_snippet",
            "source_ref": "frontend/src/lib/auth.ts",
            "content": "export function clearAuth(): void { localStorage.removeItem(ACCESS_KEY) }",
        },
    ]

    result = verify_single_project_answer(
        answer=(
            "I did not find grounded evidence for frontend route protection.\n"
            "There is no logout evidence in the packet."
        ),
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=True,
    )

    assert not result.verified
    assert "contradicted_absence_claim" in result.issues


def test_single_project_verifier_drops_contradicted_absence_after_retry_budget():
    packet = _make_packet(path="frontend/src/App.tsx")
    packet.chunks = [
        {
            "chunk_id": "chunk-1",
            "chunk_type": "code_snippet",
            "source_ref": "frontend/src/App.tsx",
            "content": "<Route element={<ProtectedRoute />}><Route path=\"/\" element={<DashboardPage />} /></Route>",
        }
    ]

    result = verify_single_project_answer(
        answer=(
            "Grounded in `frontend/src/App.tsx`.\n"
            "- I did not find grounded evidence for frontend route protection.\n"
            "- Error handling is only partially shown."
        ),
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "frontend route protection" not in result.content
    assert "Error handling" in result.content


def test_single_project_engine_fallback_explains_intake_flow():
    packet = _make_packet(
        path="scaffold/api/v1/routes/intake.py",
        symbol_name="run_intake",
        qualified_name="run_intake",
    )
    packet.query = "Tell me about the intake engine in Scaffold"
    packet.files = [
        EvidenceFileRef(path="scaffold/api/v1/routes/intake.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/graph.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/nodes.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/parser.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/brief_confidence.py", reasons=["file:lexical"]),
    ]
    packet.chunks = [
        {
            "chunk_id": "route",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/api/v1/routes/intake.py",
            "content": (
                "from scaffold.engines.intake.graph import run_intake\n"
                "from scaffold.engines.intake.parser import extract_text\n"
            ),
        },
        {
            "chunk_id": "graph",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/engines/intake/graph.py",
            "content": (
                "graph = StateGraph(IntakeState)\n"
                "graph.add_node('parse_input', parse_input)\n"
                "graph.add_node('extract_brief', extract_brief)\n"
                "graph.add_node('validate_brief', validate_brief)\n"
                "graph.add_node('flag_gaps', flag_gaps)\n"
                "async def run_intake(initial): return await intake_graph.ainvoke(initial)\n"
            ),
        },
    ]

    result = verify_single_project_answer(
        answer="The intake engine lives in `made/up.py`.",
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## Intake Engine" in result.content
    assert "parse input" in result.content
    assert "`scaffold/api/v1/routes/intake.py`" in result.content
    assert "Grounded evidence" not in result.content


def test_single_project_engine_verifier_rewrites_weak_intake_answer_with_grounded_anchors():
    packet = _make_packet(
        path="scaffold/api/v1/routes/intake.py",
        symbol_name="run_intake",
        qualified_name="run_intake",
    )
    packet.query = "Tell me about the intake engine in Scaffold"
    packet.files = [
        EvidenceFileRef(path="scaffold/api/v1/routes/intake.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/graph.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/nodes.py", reasons=["file:lexical"]),
    ]
    packet.chunks = [
        {
            "chunk_id": "graph",
            "chunk_type": "code_snippet",
            "source_ref": "scaffold/engines/intake/graph.py",
            "content": (
                "graph.add_node('parse_input', parse_input)\n"
                "graph.add_node('extract_brief', extract_brief)\n"
                "graph.add_node('validate_brief', validate_brief)\n"
                "graph.add_node('flag_gaps', flag_gaps)\n"
                "async def run_intake(initial): return await intake_graph.ainvoke(initial)\n"
            ),
        }
    ]

    result = verify_single_project_answer(
        answer=(
            "The intake engine uses LangGraph in `scaffold/engines/intake/graph.py` "
            "and is connected to `scaffold/api/v1/routes/intake.py` through `run_intake`."
        ),
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## Intake Engine" in result.content
    assert "`parse_input -> extract_brief -> validate_brief -> flag_gaps -> END`" in result.content


def test_single_project_engine_fallback_lists_five_scaffold_engines():
    packet = _make_packet(path="README.md", symbol_name="run_intake", qualified_name="run_intake")
    packet.query = "What are the 5 engines in Scaffold?"
    packet.files = [
        EvidenceFileRef(path="README.md", reasons=["lexical"]),
        EvidenceFileRef(path="scaffold/engines/intake/graph.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/documents/chains.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/tasks/assignment.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/verification/graph.py", reasons=["file:lexical"]),
        EvidenceFileRef(path="scaffold/engines/audit/evaluator.py", reasons=["file:lexical"]),
    ]
    packet.chunks = [
        {
            "chunk_id": "readme",
            "chunk_type": "documentation",
            "source_ref": "README.md",
            "content": (
                "### Intake Engine\n### Document Engine\n### Task Intelligence Engine\n"
                "### Verification Engine\n### Audit Engine\n"
            ),
        }
    ]

    result = verify_single_project_answer(
        answer="The engines are in `wrong/path.md`.",
        doctwin_name="Scaffold",
        packet=packet,
        allow_retry=False,
    )

    assert result.rewritten
    assert "## The Five Engines" in result.content
    assert "Intake Engine" in result.content
    assert "Document Engine" in result.content
    assert "Task Intelligence Engine" in result.content
    assert "Verification Engine" in result.content
    assert "Audit Engine" in result.content
