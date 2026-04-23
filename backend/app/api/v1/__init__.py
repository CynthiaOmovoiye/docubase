from fastapi import APIRouter

from app.api.v1 import (
    admin,
    chat,
    integrations,
    sharing,
    sources,
    twins,
    users,
    webhooks,
    workspaces,
)

router = APIRouter()

router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
router.include_router(twins.router, prefix="/twins", tags=["twins"])
router.include_router(sources.router, prefix="/sources", tags=["sources"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(sharing.router, prefix="/share", tags=["sharing"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
