"""
Chat API routes.

Handles both single-twin chat and workspace-wide chat (with automatic twin routing).
Also handles public share surface chat (anonymous sessions).

Auth rules:
  - /twin/* and /workspace/* and /session/* — authenticated (get_current_user)
  - /public/* — intentionally unauthenticated, must be rate-limited when implemented
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.domains.chat import service as chat_svc
from app.models.user import User
from app.schemas.chat import (
    ChatSessionSummary,
    CreatePublicSessionRequest,
    CreateSessionResponse,
    HistoryResponse,
    MessageResponse,
    SendMessageRequest,
)

router = APIRouter()

_VISITOR_ID_QUERY = Query(
    ...,
    min_length=8,
    max_length=64,
    pattern=r"^[a-zA-Z0-9_-]+$",
    description="Opaque visitor key; must match the id used when sessions were created.",
)


# ─── Authenticated routes ─────────────────────────────────────────────────────

@router.post(
    "/twin/{doctwin_id}/session",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateSessionResponse,
)
async def create_doctwin_session(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new chat session for a specific twin."""
    try:
        session = await chat_svc.create_doctwin_session(doctwin_id, current_user.id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()
    await db.refresh(session)
    return CreateSessionResponse.from_session(session)


@router.post(
    "/workspace/{workspace_id}/session",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateSessionResponse,
)
async def create_workspace_session(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a workspace-level chat session.
    The system will route each message to the most relevant twin automatically.
    """
    try:
        session = await chat_svc.create_workspace_session(workspace_id, current_user.id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()
    await db.refresh(session)
    return CreateSessionResponse.from_session(session)


@router.post(
    "/session/{session_id}/message",
    response_model=MessageResponse,
)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message in an existing session.
    Returns the assistant response (grounded in retrieved context).
    """
    try:
        result = await chat_svc.send_message(
            session_id=session_id,
            content=body.content,
            user_id=current_user.id,
            db=db,
            include_answer_diagnostics=body.include_answer_diagnostics,
        )
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()
    return MessageResponse.from_message(
        result.message,
        answer_diagnostics=result.answer_diagnostics,
    )


@router.get(
    "/session/{session_id}/history",
    response_model=HistoryResponse,
)
async def get_history(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch message history for a session."""
    try:
        messages = await chat_svc.get_history(session_id, current_user.id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return HistoryResponse(
        session_id=session_id,
        messages=[MessageResponse.from_message(m) for m in messages],
    )


@router.get(
    "/twin/{doctwin_id}/sessions",
    response_model=list[ChatSessionSummary],
)
async def list_doctwin_sessions(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List recent chat sessions for a twin owned by the current user.
    Returns lightweight summaries for the session history UI.
    """
    try:
        summaries = await chat_svc.list_sessions_for_twin(doctwin_id, current_user.id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return [ChatSessionSummary(**s) for s in summaries]


@router.get(
    "/workspace/{workspace_id}/sessions",
    response_model=list[ChatSessionSummary],
)
async def list_workspace_sessions(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List recent workspace-scoped chat sessions for a workspace owned by the current user.
    Returns lightweight summaries for the workspace history UI.
    """
    try:
        summaries = await chat_svc.list_sessions_for_workspace(workspace_id, current_user.id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return [ChatSessionSummary(**s) for s in summaries]


# ─── Public (share surface) routes ────────────────────────────────────────────
# No auth required. Rate limiting MUST be applied here when implemented.

@router.post(
    "/public/{public_slug}/session",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateSessionResponse,
)
async def create_public_session(
    public_slug: str,
    body: CreatePublicSessionRequest = CreatePublicSessionRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an anonymous chat session via a public share link.
    No auth required. The share surface must be active.
    """
    try:
        session = await chat_svc.create_public_session(
            public_slug,
            db,
            visitor_id=body.visitor_id,
        )
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    await db.commit()
    await db.refresh(session)
    return CreateSessionResponse.from_session(session)


@router.get(
    "/public/{public_slug}/sessions",
    response_model=list[ChatSessionSummary],
)
async def list_public_chat_sessions(
    public_slug: str,
    visitor_id: str = _VISITOR_ID_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """List sessions for this share link that belong to the given visitor id."""
    try:
        summaries = await chat_svc.list_public_sessions(public_slug, visitor_id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return [ChatSessionSummary(**s) for s in summaries]


@router.get(
    "/public/{public_slug}/session/{session_id}/history",
    response_model=HistoryResponse,
)
async def get_public_chat_history(
    public_slug: str,
    session_id: uuid.UUID,
    visitor_id: str = _VISITOR_ID_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """Fetch message history for a visitor-bound public session."""
    try:
        messages = await chat_svc.get_public_history(public_slug, session_id, visitor_id, db)
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return HistoryResponse(
        session_id=session_id,
        messages=[MessageResponse.from_message(m) for m in messages],
    )


@router.post(
    "/public/{public_slug}/message",
    response_model=MessageResponse,
)
async def send_public_message(
    public_slug: str,
    session_id: uuid.UUID,
    body: SendMessageRequest,
    visitor_id: str | None = Query(
        default=None,
        max_length=64,
        description="Required when the session was created with a visitor_id.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message in a public (anonymous) session.
    session_id passed as query parameter.
    """
    try:
        assistant_message = await chat_svc.send_public_message(
            public_slug=public_slug,
            session_id=session_id,
            content=body.content,
            db=db,
            visitor_id=visitor_id,
        )
    except chat_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except chat_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()
    return MessageResponse.from_message(assistant_message)
