"""
Embedding domain.

Generates vector embeddings for text content.

All embedding calls go through this module — the rest of the system
never imports provider SDKs directly.

Design notes:
  - Retrieval correctness depends on comparing vectors only within the same
    provider/model space. This module exposes explicit embedding profiles so
    callers can keep those spaces separate.
  - Ingestion may fail over from the primary provider to a configured backup
    provider on rate limits, but only when the caller allows a profile switch.
    Query-time embedding must always use the exact profile used to index the
    stored vectors being searched.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domains.knowledge.evidence import hash_text
from app.models.embedding_cache import EmbeddingCacheEntry

logger = get_logger(__name__)
settings = get_settings()

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "text-embedding-3-small",
    "jina": "jina-embeddings-v3",
    "voyage": "voyage-3.5-lite",
    "local": "local-stub",
}


class EmbeddingError(RuntimeError):
    """Base class for embedding failures."""


class EmbeddingRateLimitError(EmbeddingError):
    """Provider rejected the request due to rate limiting (HTTP 429)."""


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class EmbeddingBatchResult:
    embeddings: list[list[float]]
    profile: EmbeddingProfile


class BaseEmbedder(ABC):
    def __init__(self, profile: EmbeddingProfile) -> None:
        self.profile = profile

    @property
    def dimensions(self) -> int:
        return self.profile.dimensions

    @abstractmethod
    async def embed(self, text: str, task: str = "query") -> list[float]:
        """Embed a single text string."""

    async def embed_batch(
        self,
        texts: list[str],
        task: str = "document",
    ) -> list[list[float]]:
        """
        Embed multiple texts.

        The default implementation calls embed() sequentially.
        Provider-specific subclasses may override for batching efficiency.
        """
        results = []
        for text in texts:
            results.append(await self.embed(text, task=task))
        return results


class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI text-embedding-3-small embedder.

    Uses the OpenAI SDK (already a dependency for the LLM provider).
    """

    def __init__(self, profile: EmbeddingProfile) -> None:
        super().__init__(profile)
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed(self, text: str, task: str = "query") -> list[float]:
        truncated = text[:32_000]
        try:
            response = await self._client.embeddings.create(
                model=self.profile.model,
                input=truncated,
                dimensions=self.profile.dimensions,
            )
        except Exception as exc:
            if _is_rate_limited_error(exc):
                raise EmbeddingRateLimitError(str(exc)) from exc
            raise EmbeddingError(str(exc)) from exc
        return response.data[0].embedding

    async def embed_batch(
        self,
        texts: list[str],
        task: str = "document",
    ) -> list[list[float]]:
        truncated = [t[:32_000] for t in texts]
        results: list[list[float]] = []

        try:
            if len(truncated) > 256:
                for i in range(0, len(truncated), 256):
                    batch_response = await self._client.embeddings.create(
                        model=self.profile.model,
                        input=truncated[i : i + 256],
                        dimensions=self.profile.dimensions,
                    )
                    results.extend([d.embedding for d in batch_response.data])
                return results

            response = await self._client.embeddings.create(
                model=self.profile.model,
                input=truncated,
                dimensions=self.profile.dimensions,
            )
        except Exception as exc:
            if _is_rate_limited_error(exc):
                raise EmbeddingRateLimitError(str(exc)) from exc
            raise EmbeddingError(str(exc)) from exc

        return [d.embedding for d in response.data]


class JinaEmbedder(BaseEmbedder):
    """
    Jina AI jina-embeddings-v3 embedder.
    """

    _BASE_URL = "https://api.jina.ai/v1/embeddings"

    def __init__(self, profile: EmbeddingProfile) -> None:
        import httpx

        super().__init__(profile)
        if not settings.jina_api_key:
            raise EmbeddingError(
                "JINA_API_KEY is not set. Get a key at https://jina.ai/ and add it to your .env."
            )

        self._headers = {
            "Authorization": f"Bearer {settings.jina_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._http = httpx.AsyncClient(timeout=60.0)
        self._max_batch = max(1, settings.jina_embed_batch_size)
        self._batch_delay_seconds = max(0, settings.jina_embed_batch_delay_ms) / 1000
        self._max_retries = max(0, settings.jina_embed_max_retries)
        self._retry_base_delay_seconds = (
            max(0, settings.jina_embed_retry_base_delay_ms) / 1000
        )
        self._retry_max_delay_seconds = (
            max(0, settings.jina_embed_retry_max_delay_ms) / 1000
        )

    async def embed(self, text: str, task: str = "query") -> list[float]:
        return (await self.embed_batch([text], task=task))[0]

    async def embed_batch(
        self,
        texts: list[str],
        task: str = "document",
    ) -> list[list[float]]:
        import httpx

        truncated = [t[:32_000] for t in texts]
        results: list[list[float]] = []
        jina_task = "retrieval.query" if task == "query" else "retrieval.passage"

        for batch_index, i in enumerate(range(0, len(truncated), self._max_batch)):
            batch = truncated[i : i + self._max_batch]
            payload = {
                "model": self.profile.model,
                "input": batch,
                "dimensions": self.profile.dimensions,
                "task": jina_task,
                "normalized": True,
            }
            resp = await self._post_with_retry(
                payload,
                batch_index=batch_index,
                batch_size=len(batch),
            )

            data = resp.json()
            items = sorted(data["data"], key=lambda x: x["index"])
            results.extend(item["embedding"] for item in items)

            if self._batch_delay_seconds > 0 and i + self._max_batch < len(truncated):
                logger.info(
                    "jina_embed_batch_pacing",
                    batch_index=batch_index,
                    delay_seconds=self._batch_delay_seconds,
                    next_batch_size=min(self._max_batch, len(truncated) - (i + self._max_batch)),
                )
                await asyncio.sleep(self._batch_delay_seconds)

        return results

    async def _post_with_retry(
        self,
        payload: dict,
        *,
        batch_index: int,
        batch_size: int,
    ):
        import httpx

        attempt = 0
        while True:
            try:
                resp = await self._http.post(
                    self._BASE_URL,
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "jina_embed_http_error",
                    status=exc.response.status_code,
                    body=exc.response.text[:500],
                )
                if exc.response.status_code != 429:
                    raise EmbeddingError(str(exc)) from exc
                if attempt >= self._max_retries:
                    raise EmbeddingRateLimitError(str(exc)) from exc

                delay_seconds = self._compute_retry_delay(
                    attempt,
                    exc.response.headers.get("Retry-After"),
                )
                logger.warning(
                    "jina_embed_retrying",
                    batch_index=batch_index,
                    batch_size=batch_size,
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    delay_seconds=delay_seconds,
                )
                await asyncio.sleep(delay_seconds)
                attempt += 1
            except Exception as exc:
                raise EmbeddingError(str(exc)) from exc

    def _compute_retry_delay(self, attempt: int, retry_after: str | None) -> float:
        retry_after_seconds = _parse_retry_after_seconds(retry_after)
        if retry_after_seconds is not None:
            return retry_after_seconds

        if self._retry_base_delay_seconds <= 0:
            return 0.0

        delay_seconds = self._retry_base_delay_seconds * (2**attempt)
        if self._retry_max_delay_seconds > 0:
            return min(delay_seconds, self._retry_max_delay_seconds)
        return delay_seconds


class VoyageEmbedder(BaseEmbedder):
    """
    Voyage AI text embedding embedder.
    """

    _BASE_URL = "https://api.voyageai.com/v1/embeddings"
    _MAX_BATCH = 256

    def __init__(self, profile: EmbeddingProfile) -> None:
        import httpx

        super().__init__(profile)
        if not settings.voyage_api_key:
            raise EmbeddingError(
                "VOYAGE_API_KEY is not set. Configure it before enabling the Voyage embedder."
            )
        self._headers = {
            "Authorization": f"Bearer {settings.voyage_api_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(timeout=60.0)

    async def embed(self, text: str, task: str = "query") -> list[float]:
        return (await self.embed_batch([text], task=task))[0]

    async def embed_batch(
        self,
        texts: list[str],
        task: str = "document",
    ) -> list[list[float]]:
        import httpx

        truncated = [t[:32_000] for t in texts]
        results: list[list[float]] = []
        input_type = "query" if task == "query" else "document"

        for i in range(0, len(truncated), self._MAX_BATCH):
            batch = truncated[i : i + self._MAX_BATCH]
            payload = {
                "input": batch,
                "model": self.profile.model,
                "input_type": input_type,
                "truncation": True,
                "output_dimension": self.profile.dimensions,
                "output_dtype": "float",
            }
            try:
                resp = await self._http.post(
                    self._BASE_URL,
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "voyage_embed_http_error",
                    status=exc.response.status_code,
                    body=exc.response.text[:500],
                )
                if exc.response.status_code == 429:
                    raise EmbeddingRateLimitError(str(exc)) from exc
                raise EmbeddingError(str(exc)) from exc
            except Exception as exc:
                raise EmbeddingError(str(exc)) from exc

            data = resp.json()
            items = data.get("data", [])
            items = sorted(items, key=lambda x: x.get("index", 0))
            results.extend(item["embedding"] for item in items)

        return results


class LocalStubEmbedder(BaseEmbedder):
    """
    Deterministic stub embedder for local development.

    Produces a unit-normalised vector derived from the SHA-256 hash of the
    input text. No semantic meaning — purely structural.
    """

    def __init__(self, profile: EmbeddingProfile | None = None) -> None:
        super().__init__(
            profile
            or EmbeddingProfile(
                provider="local",
                model=_DEFAULT_MODELS["local"],
                dimensions=settings.embedding_dimensions,
            )
        )

    async def embed(self, text: str, task: str = "query") -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = []
        i = 0
        while len(raw) < self.profile.dimensions:
            raw.append((digest[i % len(digest)] - 127.5) / 127.5)
            i += 1
        raw = raw[: self.profile.dimensions]

        norm = math.sqrt(sum(x * x for x in raw))
        if norm > 0:
            raw = [x / norm for x in raw]
        return raw


def get_primary_embedding_profile() -> EmbeddingProfile:
    return resolve_embedding_profile(settings.embedding_provider, settings.embedding_model)


def get_fallback_embedding_profile() -> EmbeddingProfile | None:
    provider = settings.embedding_fallback_provider.strip().lower()
    if not provider:
        return None
    return resolve_embedding_profile(
        provider,
        settings.embedding_fallback_model or None,
        settings.embedding_dimensions,
        use_default_model=True,
    )


def resolve_embedding_profile(
    provider: str,
    model: str | None = None,
    dimensions: int | None = None,
    *,
    use_default_model: bool = False,
) -> EmbeddingProfile:
    provider_name = (provider or "local").strip().lower()
    resolved_model = model or (
        _DEFAULT_MODELS.get(provider_name, _DEFAULT_MODELS["local"])
        if use_default_model
        else settings.embedding_model
    )
    return EmbeddingProfile(
        provider=provider_name,
        model=resolved_model or _DEFAULT_MODELS.get(provider_name, _DEFAULT_MODELS["local"]),
        dimensions=dimensions or settings.embedding_dimensions,
    )


def get_embedder(
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
) -> BaseEmbedder:
    """Factory — returns an embedder for the requested profile."""
    profile = resolve_embedding_profile(
        provider or settings.embedding_provider,
        model,
        dimensions,
    )
    if profile.provider == "openai":
        return OpenAIEmbedder(profile)
    if profile.provider == "jina":
        return JinaEmbedder(profile)
    if profile.provider == "voyage":
        return VoyageEmbedder(profile)
    if profile.provider == "local":
        return LocalStubEmbedder(profile)

    logger.warning(
        "embedding_provider_unknown",
        configured=profile.provider,
        reason="unrecognised EMBEDDING_PROVIDER; falling back to local stub",
    )
    return LocalStubEmbedder(
        EmbeddingProfile(
            provider="local",
            model=_DEFAULT_MODELS["local"],
            dimensions=profile.dimensions,
        )
    )


async def embed_batch_with_failover(
    texts: list[str],
    *,
    task: str = "document",
    profiles: list[EmbeddingProfile] | None = None,
    db: AsyncSession | None = None,
) -> EmbeddingBatchResult:
    """
    Embed a batch using the first working profile in `profiles`.

    Callers control the profile order. This keeps fallback explicit and avoids
    silently switching vector spaces on query-time retrieval.
    """
    if not texts:
        return EmbeddingBatchResult([], (profiles or [get_primary_embedding_profile()])[0])

    ordered_profiles = _dedupe_profiles(profiles or _default_failover_profiles())
    last_error: Exception | None = None

    for idx, profile in enumerate(ordered_profiles):
        embedder = get_embedder(profile.provider, profile.model, profile.dimensions)
        try:
            cached_vectors = await _load_cached_embeddings(
                texts,
                profile,
                task=task,
                db=db,
            )
            missing_indices = [
                index for index, vector in enumerate(cached_vectors)
                if vector is None
            ]
            if not missing_indices:
                return EmbeddingBatchResult(
                    [vector for vector in cached_vectors if vector is not None],
                    profile,
                )

            new_vectors = await embedder.embed_batch(
                [texts[index] for index in missing_indices],
                task=task,
            )
            for index, vector in zip(missing_indices, new_vectors):
                cached_vectors[index] = vector
            await _store_cached_embeddings(
                texts=[texts[index] for index in missing_indices],
                embeddings=new_vectors,
                profile=profile,
                task=task,
                db=db,
            )
            vectors = [vector for vector in cached_vectors if vector is not None]
            return EmbeddingBatchResult(vectors, profile)
        except EmbeddingRateLimitError as exc:
            last_error = exc
            has_more = idx < len(ordered_profiles) - 1
            logger.warning(
                "embedding_rate_limited",
                provider=profile.provider,
                model=profile.model,
                dimensions=profile.dimensions,
                fallback_available=has_more,
                error=str(exc),
            )
            if not has_more:
                raise
        except Exception as exc:
            last_error = exc
            raise

    if last_error:
        raise last_error
    raise EmbeddingError("No embedding profiles were available")


async def embed_text_with_profile(
    text: str,
    profile: EmbeddingProfile,
    *,
    task: str = "query",
    db: AsyncSession | None = None,
) -> list[float]:
    cached_vectors = await _load_cached_embeddings([text], profile, task=task, db=db)
    if cached_vectors and cached_vectors[0] is not None:
        return cached_vectors[0]
    embedder = get_embedder(profile.provider, profile.model, profile.dimensions)
    vector = await embedder.embed(text, task=task)
    await _store_cached_embeddings(
        texts=[text],
        embeddings=[vector],
        profile=profile,
        task=task,
        db=db,
    )
    return vector


def _default_failover_profiles() -> list[EmbeddingProfile]:
    profiles = [get_primary_embedding_profile()]
    fallback = get_fallback_embedding_profile()
    if fallback is not None:
        profiles.append(fallback)
    return profiles


def _dedupe_profiles(profiles: list[EmbeddingProfile]) -> list[EmbeddingProfile]:
    unique: list[EmbeddingProfile] = []
    seen: set[tuple[str, str, int]] = set()
    for profile in profiles:
        key = (profile.provider, profile.model, profile.dimensions)
        if key in seen:
            continue
        seen.add(key)
        unique.append(profile)
    return unique


def _normalise_cache_text(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def _cache_text_hash(text: str) -> str:
    return hash_text(_normalise_cache_text(text))


async def _load_cached_embeddings(
    texts: list[str],
    profile: EmbeddingProfile,
    *,
    task: str,
    db: AsyncSession | None,
) -> list[list[float] | None]:
    if db is None or not texts:
        return [None] * len(texts)

    hashes = [_cache_text_hash(text) for text in texts]
    try:
        result = await db.execute(
            select(EmbeddingCacheEntry.text_hash, EmbeddingCacheEntry.embedding).where(
                EmbeddingCacheEntry.text_hash.in_(hashes),
                EmbeddingCacheEntry.provider == profile.provider,
                EmbeddingCacheEntry.model == profile.model,
                EmbeddingCacheEntry.dimensions == profile.dimensions,
                EmbeddingCacheEntry.task == task,
            )
        )
    except Exception as exc:
        logger.warning(
            "embedding_cache_load_failed",
            provider=profile.provider,
            model=profile.model,
            task=task,
            error=str(exc),
        )
        return [None] * len(texts)

    by_hash = {str(row.text_hash): list(row.embedding or []) for row in result.fetchall()}
    return [by_hash.get(text_hash) for text_hash in hashes]


async def _store_cached_embeddings(
    *,
    texts: list[str],
    embeddings: list[list[float]],
    profile: EmbeddingProfile,
    task: str,
    db: AsyncSession | None,
) -> None:
    if db is None or not texts:
        return

    values = []
    for text, embedding in zip(texts, embeddings):
        values.append(
            {
                "text_hash": _cache_text_hash(text),
                "provider": profile.provider,
                "model": profile.model,
                "dimensions": profile.dimensions,
                "task": task,
                "embedding": embedding,
            }
        )
    if not values:
        return

    try:
        stmt = pg_insert(EmbeddingCacheEntry).values(values)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_embedding_cache_profile_text",
        )
        await db.execute(stmt)
        await db.flush()
    except Exception as exc:
        logger.warning(
            "embedding_cache_store_failed",
            provider=profile.provider,
            model=profile.model,
            task=task,
            error=str(exc),
        )


def _parse_retry_after_seconds(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        return None


def _is_rate_limited_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    return exc.__class__.__name__ == "RateLimitError"
