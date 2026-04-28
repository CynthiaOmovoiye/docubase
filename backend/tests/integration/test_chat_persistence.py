"""Chat domain persists user + assistant rows against real sessions."""

from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from app.domains.answering.llm_provider import LLMResponse
from app.domains.chat.service import create_doctwin_session, send_message
from app.models.chat import Message, MessageRole

from .helpers import (
    create_manual_source_row,
    create_owner_workspace_twin,
    ingest_manual_full_sync,
)


def _stub_llm_provider():
    provider = MagicMock()

    async def complete(**kwargs):
        gen = kwargs.get("generation_name") or ""
        if gen == "intent_classification":
            raw = '{"intent":"general","path_hints":[],"expanded_query":""}'
            return LLMResponse(content=raw, model="mock-intent", input_tokens=5, output_tokens=5)
        return LLMResponse(
            content="Assistant cites INTEGRATION_CHAT_UNIQUE_CHARLIE from indexed notes.",
            model="mock-chat",
            input_tokens=12,
            output_tokens=24,
        )

    provider.complete = AsyncMock(side_effect=complete)
    return provider


async def test_send_message_persists_user_and_assistant_rows(db_session, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

    scenario = await create_owner_workspace_twin(db_session)
    marker = "INTEGRATION_CHAT_UNIQUE_CHARLIE"
    src = await create_manual_source_row(
        db_session,
        twin_id=scenario.twin_id,
        title="Chat corpus",
        body=f"# Facts\n\nImportant token: {marker}.",
    )
    await ingest_manual_full_sync(db_session, scenario=scenario, source=src)

    session = await create_doctwin_session(
        scenario.twin_id,
        scenario.user_id,
        db_session,
    )
    await db_session.commit()

    stub = _stub_llm_provider()
    monkeypatch.setattr(
        "app.domains.answering.generator.get_llm_provider",
        MagicMock(return_value=stub),
    )

    await send_message(
        session.id,
        f"What token appears in the indexed manual source ({marker})?",
        scenario.user_id,
        db_session,
        include_answer_diagnostics=False,
    )
    await db_session.commit()

    msgs = (
        await db_session.execute(
            select(Message).where(Message.session_id == session.id).order_by(Message.created_at),
        )
    ).scalars().all()

    assert len(msgs) == 2
    assert msgs[0].role == MessageRole.user
    assert msgs[1].role == MessageRole.assistant
    assert marker in msgs[1].content or "CHARLIE" in msgs[1].content
