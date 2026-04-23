"""
Unit tests for connector behavior.
Tests use fixtures rather than live APIs.
"""


import pytest

from app.connectors.base import ConnectorResult
from app.connectors.markdown.connector import MarkdownConnector


class TestMarkdownConnector:

    @pytest.fixture
    def connector(self):
        return MarkdownConnector()

    @pytest.mark.asyncio
    async def test_validate_inline_content(self, connector):
        config = {"content": "# Hello\nThis is markdown."}
        result = await connector.validate_connection(config)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_empty_config_fails(self, connector):
        result = await connector.validate_connection({})
        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_inline_content(self, connector):
        config = {"source_id": "test-123", "content": "# Project\nThis is a test project."}
        result = await connector.fetch(config)
        assert isinstance(result, ConnectorResult)
        assert len(result.files) == 1
        assert result.files[0].content == "# Project\nThis is a test project."
        assert result.errors == []
