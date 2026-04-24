from unittest.mock import AsyncMock, patch

import pytest

from app.domains.answering.generator import generate_answer, generate_workspace_answer
from app.domains.answering.llm_provider import LLMResponse
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    EvidenceSymbolRef,
    RetrievalEvidencePacket,
)
from app.domains.retrieval.planner import RetrievalMode


@pytest.mark.asyncio
async def test_generate_workspace_answer_includes_project_blocks():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content="ok",
            model="test-model",
            input_tokens=10,
            output_tokens=5,
        )
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        response = await generate_workspace_answer(
            workspace_name="Studio",
            query="walk me through the authentication implementations",
            project_contexts=[
                {
                    "name": "Alpha API",
                    "description": "Backend service",
                    "status_note": "1 ready source",
                    "ready_source_names": ["alpha-api"],
                    "chunks": [
                        {
                            "content": "Authentication uses Clerk-issued JWTs verified in middleware.",
                            "source_ref": "app/auth.py",
                        }
                    ],
                }
            ],
            conversation_history=[],
        )

    assert response.content == "ok"
    system_prompt = mock_provider.complete.await_args.kwargs["system_prompt"]
    assert "### Alpha API" in system_prompt
    assert "Studio" in system_prompt
    assert "Conversation memory" in system_prompt
    assert "Clerk-issued JWTs" in system_prompt


@pytest.mark.asyncio
async def test_generate_answer_strips_unsupported_code_examples():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=(
                "Authorization uses role checks.\n\n"
                "```python\n"
                "def authorize_user(user_role, required_role):\n"
                "    if user_role != required_role:\n"
                "        raise HTTPException(status_code=403)\n"
                "```\n"
            ),
            model="test-model",
            input_tokens=12,
            output_tokens=8,
        )
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        response = await generate_answer(
            doctwin_name="Scaffold",
            query="how is authorisation handled?",
            context_chunks=[
                {
                    "chunk_type": "module_description",
                    "content": "Authorization is handled in the API layer with role checks.",
                    "source_ref": "docs/auth.md",
                }
            ],
            conversation_history=[],
            allow_code_snippets=False,
    )

    assert "def authorize_user" not in response.content
    assert "Omitted illustrative code" not in response.content


@pytest.mark.asyncio
async def test_generate_answer_keeps_grounded_code_snippets():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=(
                "Here is the relevant handler:\n\n"
                "```python\n"
                "@app.get('/admin/data')\n"
                "def get_admin_data():\n"
                "    return {'ok': True}\n"
                "```\n"
            ),
            model="test-model",
            input_tokens=12,
            output_tokens=8,
        )
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        response = await generate_answer(
            doctwin_name="Scaffold",
            query="show me the admin handler",
            context_chunks=[
                {
                    "chunk_type": "code_snippet",
                    "content": "@app.get('/admin/data')\ndef get_admin_data():\n    return {'ok': True}",
                    "source_ref": "app/api.py",
                }
            ],
            conversation_history=[],
            allow_code_snippets=True,
        )

    assert "@app.get('/admin/data')" in response.content
    assert "Omitted illustrative code" not in response.content


@pytest.mark.asyncio
async def test_generate_workspace_answer_returns_provider_content_unchanged():
    """Workspace path does not post-process the LLM body (unlike single-twin verifier flows)."""
    body = (
        "## Scaffold\n"
        "Authorization is role-based.\n\n"
        "python\n"
        "    def authorize_user(user_role, required_role):\n"
        "        if user_role != required_role:\n"
        "            raise HTTPException(status_code=403)\n"
    )
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=body,
            model="test-model",
            input_tokens=10,
            output_tokens=6,
        )
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        response = await generate_workspace_answer(
            workspace_name="Studio",
            query="walk me through the authentication implementations",
            project_contexts=[
                {
                    "name": "Scaffold",
                    "description": "Backend service",
                    "status_note": "1 ready source",
                    "ready_source_names": ["scaffold"],
                    "chunks": [
                        {
                            "chunk_type": "module_description",
                            "content": "Authorization is enforced at the API layer.",
                            "source_ref": "docs/auth.md",
                        }
                    ],
                }
            ],
            conversation_history=[],
        )

    assert response.content == body


@pytest.mark.asyncio
async def test_generate_answer_includes_evidence_contract_block():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content="ok",
            model="test-model",
            input_tokens=8,
            output_tokens=4,
        )
    )

    packet = RetrievalEvidencePacket(
        query="how is authorization handled?",
        search_query="how is authorization handled?",
        lexical_query="how is authorization handled?",
        intent="architecture",
        mode=RetrievalMode.implementation,
        files=[EvidenceFileRef(path="app/auth.py", reasons=["file:lexical"])],
        symbols=[
            EvidenceSymbolRef(
                symbol_name="get_current_user",
                qualified_name="auth.get_current_user",
                symbol_kind="function",
                path="app/auth.py",
                reasons=["symbol:lexical"],
            )
        ],
        searched_layers=["vector", "lexical", "file", "symbol"],
        negative_evidence_scope=["symbol", "file", "lexical", "path"],
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        await generate_answer(
            doctwin_name="Scaffold",
            query="how is authorization handled?",
            context_chunks=[
                {
                    "chunk_type": "module_description",
                    "content": "Authentication is verified in get_current_user.",
                    "source_ref": "app/auth.py",
                }
            ],
            conversation_history=[],
            retrieval_packet=packet,
        )

    system_prompt = mock_provider.complete.await_args.kwargs["system_prompt"]
    assert "<answer_contract>" in system_prompt
    assert "<answer_scaffold>" in system_prompt
    assert "file_anchors:" in system_prompt
    assert "mode: implementation" in system_prompt
    assert "JWT/token validation establishes identity" in system_prompt
    assert "Do not say JWT is the authorization layer by itself" in system_prompt
    assert "app/auth.py" in system_prompt
    assert "auth.get_current_user" in system_prompt


@pytest.mark.asyncio
async def test_generate_answer_prepends_implementation_facts_to_knowledge():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content="ok",
            model="test-model",
            input_tokens=8,
            output_tokens=4,
        )
    )

    packet = RetrievalEvidencePacket(
        query="how is routing wired?",
        search_query="how is routing wired?",
        lexical_query="how is routing wired?",
        intent="architecture",
        mode=RetrievalMode.implementation,
        query_labels=["routing", "api"],
        flow_outline="route:2",
        facts=[
            {
                "fact_type": "route",
                "path": "app/main.py",
                "summary": "Registers /health router",
                "subject": "app",
                "predicate": "includes",
                "object_ref": None,
                "source_id": "s1",
                "fact_id": "f1",
                "score": 1.0,
            }
        ],
        files=[],
        symbols=[],
        searched_layers=["vector", "lexical", "facts", "file"],
        negative_evidence_scope=["file", "lexical", "path"],
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        await generate_answer(
            doctwin_name="Scaffold",
            query="how is routing wired?",
            context_chunks=[
                {
                    "chunk_type": "module_description",
                    "content": "Routers are included from submodules.",
                    "source_ref": "app/main.py",
                }
            ],
            conversation_history=[],
            retrieval_packet=packet,
        )

    system_prompt = mock_provider.complete.await_args.kwargs["system_prompt"]
    assert "Implementation facts" in system_prompt
    assert "Registers /health router" in system_prompt
    assert "query_labels:" in system_prompt
    assert "<answer_scaffold>" in system_prompt
    assert "implementation_facts" in system_prompt


@pytest.mark.asyncio
async def test_generate_workspace_answer_includes_workspace_evidence_contract():
    mock_provider = AsyncMock()
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content="ok",
            model="test-model",
            input_tokens=8,
            output_tokens=4,
        )
    )

    packet = RetrievalEvidencePacket(
        query="walk me through auth across projects",
        search_query="walk me through auth across projects",
        lexical_query="walk me through auth across projects",
        intent="architecture",
        mode=RetrievalMode.implementation,
        query_labels=["auth"],
        flow_outline="handler:1",
        facts=[
            {
                "fact_type": "handler",
                "path": "app/auth.py",
                "summary": "login handler validates payload",
                "subject": "login",
                "predicate": "handles",
                "object_ref": None,
                "source_id": "s1",
                "fact_id": "f1",
                "score": 1.0,
            }
        ],
        files=[EvidenceFileRef(path="app/auth.py", reasons=["file:lexical"])],
        symbols=[],
        searched_layers=["vector", "lexical", "file"],
        negative_evidence_scope=["file", "lexical", "path"],
    )

    with patch("app.domains.answering.generator.get_llm_provider", return_value=mock_provider):
        await generate_workspace_answer(
            workspace_name="Studio",
            query="walk me through the authentication implementations",
            project_contexts=[
                {
                    "name": "Alpha API",
                    "description": "Backend service",
                    "status_note": "1 ready source",
                    "ready_source_names": ["alpha-api"],
                    "chunks": [
                        {
                            "content": "Authentication is enforced in auth middleware.",
                            "source_ref": "app/auth.py",
                        }
                    ],
                    "evidence_packet": packet,
                }
            ],
            conversation_history=[],
        )

    system_prompt = mock_provider.complete.await_args.kwargs["system_prompt"]
    assert "<workspace_answer_contract>" in system_prompt
    assert "<workspace_answer_scaffold>" in system_prompt
    assert "<project_evidence_index>" in system_prompt
    assert "give each project a real implementation summary" in system_prompt
    assert "files: app/auth.py [file:lexical]" in system_prompt
    assert "Implementation facts" in system_prompt
    assert "login handler validates payload" in system_prompt
