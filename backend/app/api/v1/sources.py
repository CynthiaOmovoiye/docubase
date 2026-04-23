"""
Source API routes.

Attach, detach, and manage sources on a twin.
Trigger re-ingestion.

ALL routes require authentication.  Ownership of the twin (and therefore its
sources) is verified by the service layer via the authenticated user.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.domains.sources import service as sources_svc
from app.models.source import SourceStatus, SourceType
from app.models.user import User
from app.schemas.sources import (
    AttachSourceRequest,
    BackfillLegacySourcesResponse,
    SourceResponse,
    TriggerSyncResponse,
)

_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

router = APIRouter()


@router.get("/twin/{twin_id}", response_model=list[SourceResponse])
async def list_sources(
    twin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sources attached to a twin."""
    try:
        sources = await sources_svc.list_sources(twin_id, current_user.id, db)
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return [SourceResponse.from_source(s) for s in sources]


@router.post("/twin/{twin_id}", status_code=status.HTTP_201_CREATED, response_model=SourceResponse)
async def attach_source(
    twin_id: uuid.UUID,
    body: AttachSourceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Attach a new source to a twin.
    Triggers background ingestion job automatically.
    """
    try:
        source = await sources_svc.attach_source(
            twin_id=twin_id,
            user_id=current_user.id,
            source_type=body.source_type,
            name=body.name,
            connection_config=body.connection_config,
            connected_account_id=body.connected_account_id,
            db=db,
        )
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except sources_svc.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    await db.commit()

    # Enqueue background ingestion job
    await _enqueue_ingestion(str(source.id))

    return SourceResponse.from_source(source)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get source details and ingestion status."""
    try:
        source = await sources_svc.get_source(source_id, current_user.id, db)
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    return SourceResponse.from_source(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_source(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detach and delete a source from a twin (cascades chunks)."""
    try:
        await sources_svc.detach_source(source_id, current_user.id, db)
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()


@router.post("/{source_id}/sync", response_model=TriggerSyncResponse)
async def trigger_sync(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a re-ingestion for this source."""
    try:
        source = await sources_svc.get_source(source_id, current_user.id, db)
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    # Mark as pending before enqueuing
    await sources_svc.update_source_status(str(source_id), SourceStatus.pending, None, db)
    await db.commit()

    await _enqueue_ingestion(str(source_id))

    return TriggerSyncResponse(
        source_id=source_id,
        message="Re-ingestion queued",
    )


@router.post(
    "/twin/{twin_id}/backfill-legacy",
    response_model=BackfillLegacySourcesResponse,
)
async def backfill_legacy_sources(
    twin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a trust-layer backfill for all eligible legacy-index sources on a twin."""
    try:
        candidates = await sources_svc.list_legacy_backfill_candidates(
            twin_id,
            current_user.id,
            db,
        )
    except sources_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    source_ids = [str(source.id) for source in candidates]
    if source_ids:
        await sources_svc.mark_sources_pending_for_backfill(source_ids, db)
        await db.commit()
        await _enqueue_ingestions(source_ids)

    return BackfillLegacySourcesResponse(
        twin_id=twin_id,
        queued_sources=len(source_ids),
        source_ids=[uuid.UUID(source_id) for source_id in source_ids],
        message=(
            f"Queued {len(source_ids)} legacy source(s) for backfill"
            if source_ids
            else "No eligible legacy sources found"
        ),
    )


@router.post(
    "/twin/{twin_id}/upload-pdf",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceResponse,
)
async def upload_pdf_source(
    twin_id: uuid.UUID,
    name: str = Form(..., description="Human-readable name for this source"),
    file: UploadFile = File(..., description="PDF file to upload (max 20 MB)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF file and attach it as a source to a twin.

    The PDF is saved to the configured upload directory.  The file path is
    stored in connection_config so the ingestion job can read it.
    Path traversal is prevented both here (safe filename) and in the PDF
    connector (_assert_safe_path).
    """
    settings = get_settings()

    # Validate file type by content-type AND extension
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are accepted.",
        )

    # Read and size-check the file
    content = await file.read()
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds maximum size of {_MAX_PDF_BYTES // 1_048_576} MB.",
        )

    # Ensure upload directory exists
    upload_dir = settings.storage_local_path
    os.makedirs(upload_dir, mode=0o700, exist_ok=True)

    # Build a safe, collision-resistant filename
    safe_stem = "".join(
        c if c.isalnum() or c in "-_." else "_"
        for c in os.path.splitext(filename)[0]
    )[:80]
    dest_filename = f"{uuid.uuid4().hex}_{safe_stem}.pdf"
    dest_path = os.path.join(upload_dir, dest_filename)

    # Write to disk
    try:
        with open(dest_path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc

    # Attach as a PDF source
    try:
        source = await sources_svc.attach_source(
            twin_id=twin_id,
            user_id=current_user.id,
            source_type=SourceType.pdf,
            name=name,
            connection_config={"file_path": dest_path},
            db=db,
        )
    except sources_svc.NotFoundError as exc:
        os.unlink(dest_path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sources_svc.ForbiddenError as exc:
        os.unlink(dest_path)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except sources_svc.ValidationError as exc:
        os.unlink(dest_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    await db.commit()
    await _enqueue_ingestion(str(source.id))

    return SourceResponse.from_source(source)


# ─── Background job enqueueing ────────────────────────────────────────────────

async def _enqueue_ingestion(source_id: str) -> None:
    """
    Enqueue an ingestion job via ARQ.

    Uses a fire-and-forget pattern — we create a short-lived Redis connection
    to enqueue and then close it. The worker picks it up asynchronously.
    """
    from app.domains.ops.arq_enqueue import enqueue_ingest_source_job

    await enqueue_ingest_source_job(source_id)


async def _enqueue_ingestions(source_ids: list[str]) -> None:
    for source_id in source_ids:
        await _enqueue_ingestion(source_id)
