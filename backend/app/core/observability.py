"""
Langfuse observability client.

Provides a lazily-initialised Langfuse singleton.  Returns None when
Langfuse is not configured so callers can guard with a simple `if lf:`.

Usage (Langfuse Python SDK 2.x — see ``pyproject.toml`` pin; v3+ removed ``trace()``/``generation()``):

    from app.core.observability import get_langfuse

    lf = get_langfuse()
    if lf:
        trace = lf.trace(name="chat_message", user_id="...", metadata={...})
        gen = trace.generation(name="llm", model="gpt-4o-mini", input=messages)
        gen.end(output=content, usage={"input": in_tok, "output": out_tok})
        trace.score(name="completeness", value=4.5)
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_langfuse():
    """
    Return an initialised Langfuse client, or None if not configured.

    Result is cached — only one client is created per process.
    """
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import-untyped]

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            # Flush events at shutdown automatically
            flush_at=20,
            flush_interval=5.0,
        )
        if not hasattr(client, "trace"):
            logger.warning(
                "langfuse_sdk_incompatible",
                host=settings.langfuse_host,
                hint="Docbase chat uses Langfuse Python SDK 2.x (trace/generation/span). "
                "Pin langfuse>=2.57.0,<3 in the image, or upgrade observability to SDK v3.",
            )
            return None
        logger.info("langfuse_client_initialised", host=settings.langfuse_host)
        return client

    except ImportError:
        logger.warning(
            "langfuse_not_installed",
            hint="Add langfuse>=2.0.0 to dependencies and rebuild the container",
        )
        return None
    except Exception as exc:
        logger.error("langfuse_init_failed", error=str(exc))
        return None
