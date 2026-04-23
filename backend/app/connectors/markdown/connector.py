"""
Markdown connector.

Handles uploaded .md files, documentation folders, or manual markdown content.

Security: when a file_path is supplied it is validated against the configured
upload directory before any filesystem access to prevent path traversal.
Inline content (paste) bypasses filesystem entirely and is safe.
"""

import os
from typing import AsyncIterator
from pathlib import Path

from app.connectors.base import BaseConnector, ConnectorResult, RawFile
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _assert_safe_path(file_path: str) -> str:
    """
    Resolve the absolute path and assert it is inside the configured upload
    directory.  Raises ForbiddenError on any path that escapes the boundary.

    Returns the resolved absolute path on success.
    """
    upload_root = os.path.realpath(settings.storage_local_path)
    resolved = os.path.realpath(file_path)
    if not resolved.startswith(upload_root + os.sep) and resolved != upload_root:
        raise ForbiddenError(
            f"File path is outside the permitted upload directory: {file_path!r}"
        )
    return resolved


class MarkdownConnector(BaseConnector):

    source_type = "markdown"

    async def validate_connection(
        self, connection_config: dict, access_token: str | None = None
    ) -> bool:
        content = connection_config.get("content")
        file_path = connection_config.get("file_path")
        if content:
            return True
        if file_path:
            try:
                safe_path = _assert_safe_path(file_path)
                return os.path.exists(safe_path)
            except (ForbiddenError, Exception):
                return False
        return False

    async def fetch(
        self,
        connection_config: dict,
        access_token: str | None = None,
        last_commit_sha: str | None = None,
        last_page_token: str | None = None,
    ) -> ConnectorResult:
        source_id = connection_config.get("source_id", "unknown")
        files: list[RawFile] = []
        errors: list[str] = []

        # Inline content (pasted markdown) — no filesystem access needed
        if content := connection_config.get("content"):
            files.append(RawFile(
                path="manual.md",
                content=content,
                size_bytes=len(content.encode()),
                metadata={"source": "manual_input"},
            ))

        # File path — must be within the upload directory
        elif raw_path := connection_config.get("file_path"):
            try:
                file_path = _assert_safe_path(raw_path)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                stat = os.stat(file_path)
                files.append(RawFile(
                    path=os.path.basename(file_path),
                    content=content,
                    size_bytes=len(content.encode()),
                    metadata={
                        "source_path": file_path,
                        "revision_id": f"file:{Path(file_path).name}:{int(stat.st_mtime_ns)}:{stat.st_size}",
                    },
                ))
            except ForbiddenError:
                raise  # propagate — do not swallow security errors
            except Exception as e:
                errors.append(f"Failed to read markdown file: {e}")

        return ConnectorResult(
            source_id=source_id,
            files=files,
            fetch_metadata=(files[0].metadata if files else {}),
            errors=errors,
        )

    async def stream(
        self,
        connection_config: dict,
        access_token: str | None = None,
    ) -> AsyncIterator[RawFile]:
        result = await self.fetch(connection_config)
        for file in result.files:
            yield file
