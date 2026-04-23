"""
Base connector interface.

All source connectors implement this interface.
The ingestion pipeline works with BaseConnector only — it never
knows about the specific connector type.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class RawFile:
    """
    A single raw file fetched from a source.

    Connectors return these. The ingestion pipeline passes them to
    the knowledge processing domain.

    Note: this represents raw content BEFORE policy checks.
    The ingestion pipeline runs policy checks before processing.
    """
    path: str           # e.g., "src/auth/service.py", "README.md"
    content: str        # Raw text content
    size_bytes: int
    metadata: dict = field(default_factory=dict)


@dataclass
class ConnectorResult:
    """
    Result of a source fetch.

    is_full_sync=True  → caller should clear all existing chunks first (fresh ingest).
    is_full_sync=False → caller should only delete chunks whose source_ref is in
                         deleted_paths, then upsert new/changed chunks.
    head_sha           → for git sources, the HEAD commit SHA at time of fetch.
                         Stored on the Source row as last_commit_sha after a successful sync.
    next_page_token    → for Drive sources, the pageToken to use for the *next* delta sync.
                         Stored on the Source row as last_page_token after success.
    """
    source_id: str
    files: list[RawFile]
    fetch_metadata: dict = field(default_factory=dict)   # repo info, commit SHA, etc.
    errors: list[str] = field(default_factory=list)
    is_full_sync: bool = True                             # False for delta (incremental) runs
    deleted_paths: list[str] = field(default_factory=list)  # paths removed since last sync
    head_sha: str | None = None                           # git HEAD SHA after sync
    next_page_token: str | None = None                    # Drive Changes API pageToken
    # Commit history — populated by git connectors when fetch_commit_history() is called.
    # Each entry: {sha, message, author_name, author_date (ISO8601), files_changed: list[str],
    #              additions: int, deletions: int}
    # Never contains file content. Used by the memory extraction job only.
    commit_history: list[dict] = field(default_factory=list)


class BaseConnector(ABC):
    """
    Interface all source connectors must implement.

    A connector is responsible for:
    1. Authenticating with the external system
    2. Fetching raw content
    3. Returning a ConnectorResult

    A connector is NOT responsible for:
    - Applying policy
    - Processing or chunking content
    - Storing anything
    """

    @abstractmethod
    async def validate_connection(
        self, connection_config: dict, access_token: str | None = None
    ) -> bool:
        """
        Verify the connection config is valid and accessible.
        Called before ingestion starts.

        access_token — decrypted OAuth token for providers that require one.
        Connectors that do not need a token (manual, markdown, pdf) may ignore it.
        """
        ...

    @abstractmethod
    async def fetch(
        self,
        connection_config: dict,
        access_token: str | None = None,
        last_commit_sha: str | None = None,
        last_page_token: str | None = None,
    ) -> ConnectorResult:
        """
        Fetch relevant content from the source.

        access_token    — decrypted OAuth token.
        last_commit_sha — git HEAD from the previous successful sync (enables delta mode).
        last_page_token — Drive Changes API cursor from the previous sync (enables delta mode).

        When last_commit_sha / last_page_token is provided and the connector supports
        incremental sync, the result will have is_full_sync=False and only contain
        files changed since that point.  Deleted files appear in result.deleted_paths.

        Returns raw files — policy checking happens after this.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        connection_config: dict,
        access_token: str | None = None,
    ) -> AsyncIterator[RawFile]:
        """
        Stream files one at a time for large sources.
        Preferred for repos with many files.
        """
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """The SourceType enum value this connector handles."""
        ...
