from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from app.domains.embedding.embedder import (
    EmbeddingProfile,
    JinaEmbedder,
    EmbeddingRateLimitError,
    embed_batch_with_failover,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        embeddings: list[list[float]] | None = None,
        status_code: int = 200,
        retry_after: str | None = None,
        body: str = "",
    ) -> None:
        self.status_code = status_code
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after
        self.text = body
        self._embeddings = embeddings or []

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        request = httpx.Request("POST", "https://api.jina.ai/v1/embeddings")
        response = httpx.Response(
            self.status_code,
            request=request,
            text=self.text,
            headers=self.headers,
        )
        raise httpx.HTTPStatusError(
            f"{self.status_code} error",
            request=request,
            response=response,
        )

    def json(self) -> dict:
        return {
            "data": [
                {"index": idx, "embedding": embedding}
                for idx, embedding in enumerate(self._embeddings)
            ]
        }


class TestEmbedBatchWithFailover:
    @pytest.mark.asyncio
    async def test_uses_backup_profile_after_primary_rate_limit(self):
        primary = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        backup = EmbeddingProfile("voyage", "voyage-3.5-lite", 1024)

        primary_embedder = MagicMock()
        primary_embedder.embed_batch = AsyncMock(side_effect=EmbeddingRateLimitError("429"))

        backup_embedder = MagicMock()
        backup_embedder.embed_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        def factory(provider: str, model: str | None = None, dimensions: int | None = None):
            if provider == "jina":
                return primary_embedder
            return backup_embedder

        with patch("app.domains.embedding.embedder.get_embedder", side_effect=factory):
            result = await embed_batch_with_failover(
                ["hello world"],
                profiles=[primary, backup],
            )

        assert result.profile == backup
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        primary_embedder.embed_batch.assert_awaited_once()
        backup_embedder.embed_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_cached_embeddings_before_calling_provider(self):
        profile = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        provider_embedder = MagicMock()
        provider_embedder.embed_batch = AsyncMock()

        with (
            patch("app.domains.embedding.embedder.get_embedder", return_value=provider_embedder),
            patch("app.domains.embedding.embedder._load_cached_embeddings", AsyncMock(return_value=[[0.3, 0.4]])),
        ):
            result = await embed_batch_with_failover(
                ["hello world"],
                profiles=[profile],
                db=MagicMock(),
            )

        assert result.profile == profile
        assert result.embeddings == [[0.3, 0.4]]
        provider_embedder.embed_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stores_new_embeddings_in_cache(self):
        profile = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        provider_embedder = MagicMock()
        provider_embedder.embed_batch = AsyncMock(return_value=[[0.8, 0.9]])
        store_cache = AsyncMock()

        with (
            patch("app.domains.embedding.embedder.get_embedder", return_value=provider_embedder),
            patch("app.domains.embedding.embedder._load_cached_embeddings", AsyncMock(return_value=[None])),
            patch("app.domains.embedding.embedder._store_cached_embeddings", store_cache),
        ):
            result = await embed_batch_with_failover(
                ["hello world"],
                profiles=[profile],
                db=MagicMock(),
            )

        assert result.embeddings == [[0.8, 0.9]]
        provider_embedder.embed_batch.assert_awaited_once()
        store_cache.assert_awaited_once()


class TestJinaEmbedder:
    @pytest.mark.asyncio
    async def test_uses_configured_batch_size_and_delay(self):
        profile = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        fake_client = MagicMock()
        request_payloads: list[dict] = []

        async def post(*args, **kwargs):
            payload = kwargs["json"]
            request_payloads.append(payload)
            batch_size = len(payload["input"])
            return _FakeResponse(
                embeddings=[[float(idx)] for idx in range(batch_size)],
            )

        fake_client.post = AsyncMock(side_effect=post)

        with (
            patch("httpx.AsyncClient", return_value=fake_client),
            patch("app.domains.embedding.embedder.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
            patch("app.domains.embedding.embedder.settings.jina_api_key", "test-key"),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_size", 2),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_delay_ms", 250),
            patch("app.domains.embedding.embedder.settings.jina_embed_max_retries", 0),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_base_delay_ms", 100),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_max_delay_ms", 500),
        ):
            embedder = JinaEmbedder(profile)
            vectors = await embedder.embed_batch(
                ["a", "b", "c", "d", "e"],
                task="document",
            )

        assert len(vectors) == 5
        assert [len(payload["input"]) for payload in request_payloads] == [2, 2, 1]
        assert sleep_mock.await_args_list == [call(0.25), call(0.25)]

    @pytest.mark.asyncio
    async def test_retries_after_429_then_succeeds(self):
        profile = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        fake_client = MagicMock()
        fake_client.post = AsyncMock(
            side_effect=[
                _FakeResponse(
                    status_code=429,
                    retry_after="0.5",
                    body='{"detail":"rate limited"}',
                ),
                _FakeResponse(embeddings=[[0.1, 0.2, 0.3]]),
            ]
        )

        with (
            patch("httpx.AsyncClient", return_value=fake_client),
            patch("app.domains.embedding.embedder.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
            patch("app.domains.embedding.embedder.settings.jina_api_key", "test-key"),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_size", 8),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_delay_ms", 0),
            patch("app.domains.embedding.embedder.settings.jina_embed_max_retries", 2),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_base_delay_ms", 1000),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_max_delay_ms", 5000),
        ):
            embedder = JinaEmbedder(profile)
            vectors = await embedder.embed_batch(["hello"], task="document")

        assert vectors == [[0.1, 0.2, 0.3]]
        assert fake_client.post.await_count == 2
        sleep_mock.assert_awaited_once_with(0.5)

    @pytest.mark.asyncio
    async def test_raises_rate_limit_after_retry_budget_exhausted(self):
        profile = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        fake_client = MagicMock()
        fake_client.post = AsyncMock(
            side_effect=[
                _FakeResponse(status_code=429, body='{"detail":"rate limited"}'),
                _FakeResponse(status_code=429, body='{"detail":"rate limited"}'),
                _FakeResponse(status_code=429, body='{"detail":"rate limited"}'),
            ]
        )

        with (
            patch("httpx.AsyncClient", return_value=fake_client),
            patch("app.domains.embedding.embedder.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
            patch("app.domains.embedding.embedder.settings.jina_api_key", "test-key"),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_size", 8),
            patch("app.domains.embedding.embedder.settings.jina_embed_batch_delay_ms", 0),
            patch("app.domains.embedding.embedder.settings.jina_embed_max_retries", 2),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_base_delay_ms", 500),
            patch("app.domains.embedding.embedder.settings.jina_embed_retry_max_delay_ms", 1500),
        ):
            embedder = JinaEmbedder(profile)
            with pytest.raises(EmbeddingRateLimitError):
                await embedder.embed_batch(["hello"], task="document")

        assert fake_client.post.await_count == 3
        assert sleep_mock.await_args_list == [call(0.5), call(1.0)]
