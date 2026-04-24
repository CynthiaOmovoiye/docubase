"""
PDF connector.

Handles uploaded PDF files (resumes, case studies, portfolio docs).
Extracts text content per page.

Security: file_path is validated against the configured upload directory
before any filesystem access to prevent path traversal attacks.
"""

import os
from collections.abc import AsyncIterator

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


class PDFConnector(BaseConnector):

    source_type = "pdf"

    async def validate_connection(
        self, connection_config: dict, access_token: str | None = None
    ) -> bool:
        """Check that the file path is safe, exists, and is a readable PDF."""
        file_path = connection_config.get("file_path")
        if not file_path:
            return False
        try:
            safe_path = _assert_safe_path(file_path)
            return os.path.exists(safe_path) and safe_path.lower().endswith(".pdf")
        except (ForbiddenError, Exception):
            return False

    async def fetch(
        self,
        connection_config: dict,
        access_token: str | None = None,
        last_commit_sha: str | None = None,
        last_page_token: str | None = None,
    ) -> ConnectorResult:
        """Extract text content from a PDF file."""
        raw_path = connection_config["file_path"]
        source_id = connection_config.get("source_id", "unknown")

        # Resolve and validate path — raises ForbiddenError on traversal attempt
        file_path = _assert_safe_path(raw_path)

        logger.info("pdf_fetch_start", file_path=file_path)

        files: list[RawFile] = []
        errors: list[str] = []

        try:
            from app.connectors.pdf.text_extract import extract_readable_pdf_text_from_path

            stat = os.stat(file_path)
            full_text = extract_readable_pdf_text_from_path(file_path)
            if not full_text:
                errors.append("No readable text extracted from PDF (parse failure or tagged-PDF noise)")
            else:
                files.append(
                    RawFile(
                        path=os.path.basename(file_path),
                        content=full_text,
                        size_bytes=len(full_text.encode()),
                        metadata={
                            "page_count": full_text.count("--- Page "),
                            "source_path": file_path,
                            "revision_id": (
                                f"file:{os.path.basename(file_path)}:{int(stat.st_mtime_ns)}:{stat.st_size}"
                            ),
                        },
                    )
                )

        except ForbiddenError:
            raise  # propagate — do not swallow security errors
        except Exception as e:
            errors.append(f"Failed to read PDF: {e}")
            logger.error("pdf_fetch_error", error=str(e))

        logger.info("pdf_fetch_complete", errors=len(errors))

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
