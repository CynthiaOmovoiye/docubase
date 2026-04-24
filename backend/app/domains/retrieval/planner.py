"""
Retrieval planning for hybrid evidence search.

Phase 2 introduces a lightweight planner that chooses:
- the retrieval mode for the question
- which search layers to use
- candidate budgets per layer
- the query forms used for dense and lexical search

The planner stays deterministic and cheap so it can run on every turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.domains.retrieval.intent import QueryIntent

_IMPLEMENTATION_RE = re.compile(
    r"\b("
    r"where\s+(does|do)\b|"
    r"where\s+is\b|"
    r"where\s+are\b|"
    r"which\s+file|"
    r"which\s+files|"
    r"walk\s+me\s+through|"
    r"tests?|"
    r"how\s+is\s+.+\bimplemented\b|"
    r"how\s+does\s+.+\bwork\b|"
    r"add\s+.+\b(feature|flow|functionality)\b|"
    r"logout|sign[\s-]?up|sign[\s-]?in|login|auth(entication|orization)?"
    r")\b",
    re.IGNORECASE,
)
_RECRUITER_RE = re.compile(
    r"\b("
    r"experience\s+with|"
    r"experience\s+(?:is|are|demonstrated)|"
    r"demonstrated\s+.*experience|"
    r"candidate|"
    r"recruiter|"
    r"capabilit(?:y|ies)|"
    r"can\s+do\s+today|"
    r"skills?|"
    r"used\s+(python|fastapi|react|terraform|docker|aws)"
    r")\b",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"\b("
    r"what\s+is\s+left|"
    r"what['’]s\s+left|"
    r"remaining|"
    r"done|"
    r"progress|"
    r"status|"
    r"week\s+\d+|"
    r"sprint|"
    r"next\s+step"
    r")\b",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"\b("
    r"across\s+all|"
    r"across\s+projects|"
    r"all\s+projects|"
    r"compare|"
    r"which\s+projects|"
    r"covered\s+projects"
    r")\b",
    re.IGNORECASE,
)

_AUTH_FLOW_RE = re.compile(
    r"\b("
    r"auth|authentication|authorization|login|logout|register|"
    r"sign[\s-]?up|sign[\s-]?in|refresh|token|session|jwt|current[_\s-]?user|"
    r"protected|guard|middleware"
    r")\b",
    re.IGNORECASE,
)
_DASHBOARD_RE = re.compile(
    r"\b(dashboard|load|loaded|loading|query|fetch|usequery|page)\b",
    re.IGNORECASE,
)
_PROJECT_FLOW_RE = re.compile(
    r"\b(projects?|project\s+lifecycle|owner(?:ship)?|create\s+project|list\s+projects?)\b",
    re.IGNORECASE,
)
_DATA_MODEL_RE = re.compile(
    r"\b(data\s+model|models?|schema|entities|database\s+model)\b",
    re.IGNORECASE,
)
_FRONTEND_RE = re.compile(
    r"\b(frontend|front-end|react|ui|browser|page|component|route\s+guard)\b",
    re.IGNORECASE,
)
_TEST_RE = re.compile(
    r"\b(tests?|test\s+strategy|e2e|regression|pytest|coverage|prove)\b",
    re.IGNORECASE,
)
_ENGINE_RE = re.compile(
    r"\b(engine|engines|intake|documents?|task\s+intelligence|verification|audit)\b",
    re.IGNORECASE,
)
_CODE_SNIPPET_RE = re.compile(
    r"\b(code\s+snippet|code\s+sample|show\s+me\s+the\s+code|provide\s+code)\b",
    re.IGNORECASE,
)
_WEEK_MILESTONE_RE = re.compile(r"\bweek\s+(\d+)\b", re.IGNORECASE)


class RetrievalMode(StrEnum):
    implementation = "implementation"
    architecture = "architecture"
    onboarding = "onboarding"
    change_review = "change_review"
    risk_review = "risk_review"
    workspace_comparison = "workspace_comparison"
    recruiter_summary = "recruiter_summary"
    project_status = "project_status"
    general = "general"


@dataclass(slots=True)
class RetrievalPlan:
    mode: RetrievalMode
    intent: QueryIntent
    query: str
    search_query: str
    lexical_query: str
    path_hints: list[str] = field(default_factory=list)
    searched_layers: list[str] = field(default_factory=list)
    negative_evidence_scope: list[str] = field(default_factory=list)
    top_k: int = 8
    dense_budget: int = 8
    lexical_budget: int = 6
    file_budget: int = 4
    symbol_budget: int = 6
    graph_budget: int = 4
    rerank_budget: int = 12


def build_retrieval_plan(
    *,
    query: str,
    intent: QueryIntent,
    expanded_query: str = "",
    path_hints: list[str] | None = None,
    top_k: int = 8,
    workspace_scope: bool = False,
) -> RetrievalPlan:
    """
    Build a deterministic search plan for a retrieval turn.

    Phase 2 keeps this heuristic on purpose. We already have an intent analyser;
    the planner turns that signal into layer budgets and evidence requirements.
    """
    stripped_query = query.strip()
    search_query = _augment_search_query(
        query=stripped_query,
        expanded_query=expanded_query,
        intent=intent,
        workspace_scope=workspace_scope,
    )
    lexical_query = search_query if len(search_query) <= 280 else stripped_query
    hints = list(path_hints or [])

    mode = _classify_mode(
        query=stripped_query,
        intent=intent,
        workspace_scope=workspace_scope,
    )

    searched_layers = ["vector", "lexical", "path"]
    negative_scope = ["path", "lexical"]
    dense_budget = max(top_k, 8)
    lexical_budget = 6
    file_budget = 4
    symbol_budget = 6
    graph_budget = 4
    rerank_budget = max(top_k * 2, 12)

    if mode == RetrievalMode.implementation:
        searched_layers = ["vector", "lexical", "path", "symbol", "file", "graph"]
        negative_scope = ["symbol", "file", "lexical", "path"]
        lexical_budget = 8
        file_budget = 6
        symbol_budget = 8
        graph_budget = 5
        rerank_budget = max(top_k * 3, 16)
    elif mode == RetrievalMode.onboarding:
        searched_layers = ["vector", "lexical", "path", "file", "symbol", "graph"]
        negative_scope = ["symbol", "file", "path", "lexical"]
        lexical_budget = 6
        file_budget = 6
        symbol_budget = 6
        graph_budget = 5
    elif mode == RetrievalMode.architecture:
        searched_layers = ["vector", "lexical", "path", "file", "graph"]
        negative_scope = ["file", "path", "lexical"]
        lexical_budget = 7
        file_budget = 5
        symbol_budget = 4
        graph_budget = 5
    elif mode == RetrievalMode.change_review:
        searched_layers = ["vector", "lexical", "file", "graph"]
        negative_scope = ["file", "lexical", "graph"]
        lexical_budget = 5
        file_budget = 4
        symbol_budget = 2
        graph_budget = 5
    elif mode == RetrievalMode.risk_review:
        searched_layers = ["vector", "lexical", "file", "graph"]
        negative_scope = ["file", "lexical", "graph"]
        lexical_budget = 6
        file_budget = 5
        symbol_budget = 3
        graph_budget = 5
    elif mode == RetrievalMode.workspace_comparison:
        searched_layers = ["vector", "lexical", "path", "file", "symbol", "graph"]
        negative_scope = ["symbol", "file", "lexical", "path"]
        lexical_budget = 7
        file_budget = 5
        symbol_budget = 6
        graph_budget = 4
    elif mode == RetrievalMode.recruiter_summary:
        searched_layers = ["vector", "lexical", "file", "symbol"]
        negative_scope = ["symbol", "file", "lexical"]
        lexical_budget = 7
        file_budget = 5
        symbol_budget = 7
        graph_budget = 2
    elif mode == RetrievalMode.project_status:
        searched_layers = ["vector", "lexical", "file", "graph"]
        negative_scope = ["file", "lexical", "graph"]
        lexical_budget = 6
        file_budget = 5
        symbol_budget = 3
        graph_budget = 5

    return RetrievalPlan(
        mode=mode,
        intent=intent,
        query=stripped_query,
        search_query=search_query,
        lexical_query=lexical_query,
        path_hints=hints,
        searched_layers=searched_layers,
        negative_evidence_scope=negative_scope,
        top_k=top_k,
        dense_budget=dense_budget,
        lexical_budget=lexical_budget,
        file_budget=file_budget,
        symbol_budget=symbol_budget,
        graph_budget=graph_budget,
        rerank_budget=rerank_budget,
    )


def _augment_search_query(
    *,
    query: str,
    expanded_query: str,
    intent: QueryIntent,
    workspace_scope: bool,
) -> str:
    base = expanded_query.strip() or query.strip()
    mode = _classify_mode(
        query=query,
        intent=intent,
        workspace_scope=workspace_scope,
    )
    aliases: list[str] = []
    lowered = query.lower()

    if mode in {
        RetrievalMode.implementation,
        RetrievalMode.onboarding,
        RetrievalMode.workspace_comparison,
        RetrievalMode.architecture,
    }:
        if _AUTH_FLOW_RE.search(lowered):
            aliases.extend(
                [
                    "auth",
                    "authentication",
                    "authorization",
                    "login",
                    "logout",
                    "register",
                    "signup",
                    "signin",
                    "refresh token",
                    "access token",
                    "session",
                    "jwt",
                    "protected route",
                    "guard",
                    "middleware",
                    "current_user",
                ]
            )
        if _DASHBOARD_RE.search(lowered):
            aliases.extend(
                [
                    "dashboard",
                    "load dashboard",
                    "dashboard page",
                    "query",
                    "fetch",
                    "useQuery",
                    "useProjects",
                    "projectsApi",
                    "list projects",
                    "api route",
                ]
            )
        if _PROJECT_FLOW_RE.search(lowered):
            aliases.extend(
                [
                    "project",
                    "projects",
                    "create_project",
                    "get_project",
                    "list projects",
                    "projectsApi",
                    "owner_id",
                    "current_user",
                ]
            )
        if _DATA_MODEL_RE.search(lowered):
            aliases.extend(["data model", "models", "Project", "Task", "User", "owner_id", "status"])
        if _FRONTEND_RE.search(lowered):
            aliases.extend(
                [
                    "frontend",
                    "React",
                    "App.tsx",
                    "DashboardPage",
                    "LoginPage",
                    "ProtectedRoute",
                    "useProjects",
                    "PageShell",
                    "api.ts",
                ]
            )
        if _TEST_RE.search(lowered):
            aliases.extend(["tests", "test_e2e_flow.py", "register", "login", "project", "audit", "regression"])
        if _ENGINE_RE.search(lowered):
            aliases.extend(
                [
                    "engine",
                    "engines",
                    "intake engine",
                    "document engine",
                    "task intelligence engine",
                    "verification engine",
                    "audit engine",
                    "scaffold/engines/intake",
                    "scaffold/engines/documents",
                    "scaffold/engines/tasks",
                    "scaffold/engines/verification",
                    "scaffold/engines/audit",
                    "run_intake",
                    "generate_document",
                    "recommend_assignments",
                    "process_commit",
                    "evaluate_all_controls",
                ]
            )
        if _CODE_SNIPPET_RE.search(lowered):
            aliases.extend(
                [
                    "code snippet",
                    "implementation file",
                    "function",
                    "route",
                    "module",
                ]
            )

    if mode == RetrievalMode.recruiter_summary and "python" in lowered:
        aliases.extend(["python", "backend", "fastapi", "api", "service"])
    if mode == RetrievalMode.recruiter_summary and _FRONTEND_RE.search(lowered):
        aliases.extend(
            [
                "frontend",
                "React",
                "App.tsx",
                "DashboardPage",
                "useProjects",
                "authApi",
                "guides/7_frontend.md",
            ]
        )

    if mode == RetrievalMode.change_review and _AUTH_FLOW_RE.search(lowered):
        aliases.extend(["auth", "authentication", "authorization", "logout", "login", "refresh token", "session"])

    if mode == RetrievalMode.risk_review and _AUTH_FLOW_RE.search(lowered):
        aliases.extend(["auth", "authentication", "authorization", "logout", "login", "refresh token", "session"])

    if mode == RetrievalMode.project_status:
        aliases.extend(["remaining", "todo", "pending", "next step", "progress"])
        if week_match := _WEEK_MILESTONE_RE.search(lowered):
            aliases.extend(
                [
                    f"week{week_match.group(1)}",
                    "planning",
                    "milestone",
                    f"planning/week{week_match.group(1)}.md",
                ]
            )
        if _AUTH_FLOW_RE.search(lowered):
            aliases.extend(["auth", "authentication", "authorization", "logout", "login"])
        if _DASHBOARD_RE.search(lowered):
            aliases.extend(["dashboard", "table", "load dashboard"])

    if not aliases:
        return base

    deduped = list(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))
    return f"{base} {' '.join(deduped)}".strip()


def _classify_mode(
    *,
    query: str,
    intent: QueryIntent,
    workspace_scope: bool,
) -> RetrievalMode:
    lowered = query.lower()

    if workspace_scope and _COMPARE_RE.search(lowered):
        return RetrievalMode.workspace_comparison
    if _RECRUITER_RE.search(lowered):
        return RetrievalMode.recruiter_summary
    if _STATUS_RE.search(lowered):
        return RetrievalMode.project_status
    if intent == QueryIntent.change_query:
        return RetrievalMode.change_review
    if intent == QueryIntent.risk_query:
        return RetrievalMode.risk_review
    if intent == QueryIntent.onboarding:
        return RetrievalMode.onboarding
    if intent == QueryIntent.architecture and _IMPLEMENTATION_RE.search(lowered):
        return RetrievalMode.implementation
    if intent == QueryIntent.file_specific:
        return RetrievalMode.implementation
    if "dashboard" in lowered and any(token in lowered for token in ("load", "loaded", "loading", "query", "fetch")):
        return RetrievalMode.implementation
    if _ENGINE_RE.search(lowered):
        return RetrievalMode.implementation
    if _IMPLEMENTATION_RE.search(lowered):
        return RetrievalMode.implementation
    if intent == QueryIntent.architecture:
        return RetrievalMode.architecture
    return RetrievalMode.general
