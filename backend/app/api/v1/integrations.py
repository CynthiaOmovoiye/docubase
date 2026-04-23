"""
Integrations API routes.

Handles the full OAuth account-linking lifecycle for GitHub, GitLab, and Google Drive.
Provides repo/file browser endpoints so the frontend can present a source picker
backed by the user's real connected accounts.

All routes except the callback require authentication. The callback is reached
via browser redirect from the OAuth provider so it carries a signed state token
instead of a Bearer header.

Route summary:
  GET  /integrations                          — list connected accounts
  GET  /integrations/{provider}/connect       — get auth URL to start OAuth flow
  GET  /integrations/{provider}/callback      — OAuth callback (browser redirect)
  DELETE /integrations/{account_id}           — disconnect an account
  GET  /integrations/github/repos             — list GitHub repos (paginated)
  GET  /integrations/gitlab/projects         — list GitLab projects (paginated)
  GET  /integrations/google_drive/files       — list Drive files/folders
"""

import uuid
from urllib.parse import quote

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.redis import get_redis
from app.domains.integrations import service as integrations_svc
from app.models.user import User
from app.schemas.integrations import (
    ConnectedAccountResponse,
    DriveFileItem,
    OAuthInitResponse,
    RepoItem,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

# Providers that have dedicated browser endpoints
_GITHUB = "github"
_GITLAB = "gitlab"
_GOOGLE_DRIVE = "google_drive"

_GOOGLE_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


# ─── Account management ───────────────────────────────────────────────────────


@router.get("", response_model=list[ConnectedAccountResponse])
async def list_connected_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active connected OAuth accounts for the authenticated user."""
    accounts = await integrations_svc.get_connected_accounts(str(current_user.id), db)
    return [ConnectedAccountResponse.model_validate(a) for a in accounts]


@router.get("/{provider}/connect", response_model=OAuthInitResponse)
async def initiate_oauth(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the OAuth authorization URL for the given provider.
    The client should redirect the user to this URL to begin the OAuth flow.
    """
    redis = get_redis()
    try:
        auth_url = await integrations_svc.initiate_oauth(
            provider=provider,
            user_id=str(current_user.id),
            db=db,
            redis=redis,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return OAuthInitResponse(auth_url=auth_url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    OAuth callback endpoint — called by the provider after user authorization.

    On success: redirects to {frontend_url}/integrations/connected?provider={provider}
    On failure: redirects to {frontend_url}/integrations/error?message={message}

    This endpoint is hit by the browser (not by API clients), so it uses
    RedirectResponse rather than JSON. Authentication is provided by the
    CSRF state token validated inside the service.
    """
    settings = get_settings()
    redis = get_redis()

    try:
        account = await integrations_svc.handle_callback(
            provider=provider,
            code=code,
            state=state,
            db=db,
            redis=redis,
        )
        await db.commit()
    except ValidationError as exc:
        error_msg = quote(str(exc))
        return RedirectResponse(
            url=f"{settings.frontend_url}/integrations?error={error_msg}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as exc:
        logger.error("oauth_callback_unexpected_error", provider=provider, error=str(exc))
        error_msg = quote("OAuth authorization failed. Please try again.")
        return RedirectResponse(
            url=f"{settings.frontend_url}/integrations?error={error_msg}",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{settings.frontend_url}/integrations?connected={provider}",
        status_code=status.HTTP_302_FOUND,
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect (soft-delete) a connected OAuth account."""
    try:
        await integrations_svc.disconnect_account(
            account_id=str(account_id),
            user_id=str(current_user.id),
            db=db,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()


# ─── Provider resource browsers ───────────────────────────────────────────────


@router.get("/github/repos", response_model=list[RepoItem])
async def list_github_repos(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List GitHub repositories accessible to the user's connected GitHub account.

    Returns repos from the user's primary (first active) GitHub connected account.
    Raises 400 if no GitHub account is connected.
    """
    access_token = await _require_provider_token(_GITHUB, current_user, db)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={
                "page": page,
                "per_page": per_page,
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("github_repos_fetch_failed", status=exc.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch repositories from GitHub",
            )
        data = resp.json()

    return [
        RepoItem(
            id=repo["id"],
            name=repo["name"],
            full_name=repo["full_name"],
            private=repo["private"],
            default_branch=repo.get("default_branch", "main"),
            description=repo.get("description"),
            updated_at=repo.get("updated_at"),
        )
        for repo in data
    ]


@router.get("/gitlab/projects", response_model=list[RepoItem])
async def list_gitlab_projects(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List GitLab projects accessible to the user's connected GitLab account.
    """
    settings = get_settings()
    access_token = await _require_provider_token(_GITLAB, current_user, db)
    gitlab_base = settings.gitlab_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{gitlab_base}/api/v4/projects",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "page": page,
                "per_page": per_page,
                "membership": "true",
                "order_by": "last_activity_at",
                "sort": "desc",
            },
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("gitlab_projects_fetch_failed", status=exc.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch projects from GitLab",
            )
        data = resp.json()

    return [
        RepoItem(
            id=project["id"],
            name=project["name"],
            full_name=project["path_with_namespace"],
            private=project.get("visibility", "public") != "public",
            default_branch=project.get("default_branch", "main"),
            description=project.get("description"),
            updated_at=project.get("last_activity_at"),
        )
        for project in data
    ]


@router.get("/google_drive/files", response_model=list[DriveFileItem])
async def list_google_drive_files(
    folder_id: str = Query(default="root"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List files and folders in a Google Drive folder.

    Defaults to the root folder. Supports navigation by passing any folder ID.
    Only returns files and folders (not Google Docs native formats unless they
    are explicitly included in the Drive query).
    """
    access_token = await _require_provider_token(_GOOGLE_DRIVE, current_user, db)

    query = f"'{folder_id}' in parents and trashed = false"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": query,
                "pageSize": 1000,
                "fields": "files(id,name,mimeType,modifiedTime)",
                "orderBy": "folder,name",
            },
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("gdrive_files_fetch_failed", status=exc.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch files from Google Drive",
            )
        data = resp.json()

    return [
        DriveFileItem(
            id=f["id"],
            name=f["name"],
            mime_type=f["mimeType"],
            modified_time=f.get("modifiedTime"),
            is_folder=(f["mimeType"] == _GOOGLE_DRIVE_FOLDER_MIME),
        )
        for f in data.get("files", [])
    ]


# ─── Internal helpers ─────────────────────────────────────────────────────────


async def _require_provider_token(
    provider: str,
    current_user: User,
    db: AsyncSession,
) -> str:
    """
    Find the first active connected account for the given provider and return
    its decrypted access token. Raises 400 if no account is connected.
    """
    from sqlalchemy import select
    from app.models.integration import ConnectedAccount

    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == current_user.id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.is_active.is_(True),
        )
    )
    account = result.scalars().first()

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No connected {provider} account. Connect one at /integrations/{provider}/connect",
        )

    try:
        return await integrations_svc.refresh_token_if_needed(account, db)
    except Exception as exc:
        logger.error(
            "provider_token_resolution_failed",
            provider=provider,
            user_id=str(current_user.id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to resolve access token for {provider}",
        )
