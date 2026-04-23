"""
Manual notes connector.

Handles 'manual' source type — owner-typed notes, profile descriptions,
or any free-form text that the owner wants the twin to know about.

Connection config:
  {
    "content": "This project does X. Key features include...",
    "title":   "Project Overview"  (optional)
  }

The content is treated as a single RawFile with path "manual/{title_slug}.md"
so the knowledge pipeline classifies it as documentation.
"""

import re
from collections.abc import AsyncIterator

from app.connectors.base import BaseConnector, ConnectorResult, RawFile
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_CONTENT_CHARS = 50_000  # Reasonable upper bound for manual notes


class ManualConnector(BaseConnector):

    @property
    def source_type(self) -> str:
        return "manual"

    async def validate_connection(
        self, connection_config: dict, access_token: str | None = None
    ) -> bool:
        content = connection_config.get("content", "").strip()
        if not content:
            raise ValueError("Manual source requires non-empty 'content'")
        if len(content) > _MAX_CONTENT_CHARS:
            raise ValueError(
                f"Manual content exceeds maximum length of {_MAX_CONTENT_CHARS} characters"
            )
        return True

    async def fetch(
        self,
        connection_config: dict,
        access_token: str | None = None,
        last_commit_sha: str | None = None,
        last_page_token: str | None = None,
    ) -> ConnectorResult:
        content = connection_config.get("content", "").strip()
        title = connection_config.get("title", "notes").strip() or "notes"

        # Derive a safe filename from the title
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "notes"
        path = f"manual/{slug}.md"

        file = RawFile(
            path=path,
            content=content,
            size_bytes=len(content.encode("utf-8")),
            metadata={"title": title, "source_type": "manual"},
        )

        logger.info(
            "manual_connector_fetch",
            path=path,
            content_length=len(content),
        )

        return ConnectorResult(
            source_id="",  # Filled in by the ingestion job
            files=[file],
            fetch_metadata={"title": title},
        )

    async def stream(
        self,
        connection_config: dict,
        access_token: str | None = None,
    ) -> AsyncIterator[RawFile]:
        result = await self.fetch(connection_config)
        for f in result.files:
            yield f
