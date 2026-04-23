"""
Connector registry.

Maps SourceType values to their connector classes.
The ingestion pipeline uses this to get the right connector for a given source.
"""

from app.connectors.base import BaseConnector
from app.connectors.google_drive.connector import GoogleDriveConnector
from app.connectors.manual.connector import ManualConnector
from app.connectors.markdown.connector import MarkdownConnector
from app.connectors.pdf.connector import PDFConnector
from app.models.source import SourceType


def get_connector(source_type: SourceType, **kwargs) -> BaseConnector:
    """
    Return an instantiated connector for the given source type.

    Additional kwargs are passed to the connector constructor
    (e.g., token for authenticated connectors).
    """
    registry: dict[SourceType, type[BaseConnector]] = {
        SourceType.google_drive: GoogleDriveConnector,
        SourceType.pdf: PDFConnector,
        SourceType.markdown: MarkdownConnector,
        SourceType.manual: ManualConnector,
    }

    connector_cls = registry.get(source_type)
    if not connector_cls:
        raise NotImplementedError(f"No connector implemented for source_type: {source_type}")

    return connector_cls(**kwargs)
