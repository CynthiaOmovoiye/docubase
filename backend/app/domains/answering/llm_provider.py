"""
LLM provider abstraction.

All LLM calls go through this interface.
The rest of the product never imports openai, anthropic, or any other
provider SDK directly — only this module does.

This makes provider swapping a single-file change.

Langfuse integration:
  If LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY are set, every `complete()`
  call records a generation span on the provided trace.  Tracing is entirely
  opt-in: callers that don't pass a trace_id simply get no Langfuse tracking.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    # Langfuse generation ID, set when tracing is active
    generation_id: str | None = field(default=None)


class BaseLLMProvider(ABC):

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        # Optional Langfuse trace context
        trace_id: str | None = None,
        generation_name: str = "llm_generation",
    ) -> LLMResponse:
        ...


class OpenAICompatibleProvider(BaseLLMProvider):
    """Chat completions via the OpenAI SDK (OpenAI or OpenRouter-compatible base URL)."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        if settings.llm_provider == "openrouter":
            headers: dict[str, str] = {}
            if settings.openrouter_http_referer:
                headers["HTTP-Referer"] = settings.openrouter_http_referer
            if settings.openrouter_app_title:
                headers["X-Title"] = settings.openrouter_app_title
            self._client = AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                default_headers=headers or None,
            )
            self._model = settings.openrouter_model
        else:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
        trace_id: str | None = None,
        generation_name: str = "llm_generation",
    ) -> LLMResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        generation_id: str | None = None

        # ── Open Langfuse generation span (no-op when not configured) ──────────
        lf_generation = None
        if trace_id:
            from app.core.observability import get_langfuse
            lf = get_langfuse()
            if lf:
                try:
                    lf_generation = lf.generation(
                        trace_id=trace_id,
                        name=generation_name,
                        model=self._model,
                        input=full_messages,
                        model_parameters={
                            "max_tokens": max_tokens or settings.llm_max_tokens,
                            "temperature": temperature if temperature is not None
                                          else settings.llm_temperature,
                        },
                    )
                    generation_id = lf_generation.id
                except Exception as exc:
                    logger.warning("langfuse_generation_open_failed", error=str(exc))

        t_start = time.monotonic()

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=temperature if temperature is not None else settings.llm_temperature,
        )

        latency_ms = int((time.monotonic() - t_start) * 1000)
        choice = response.choices[0]
        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0
        content = choice.message.content or ""

        # ── Close Langfuse generation span ──────────────────────────────────────
        if lf_generation:
            try:
                lf_generation.end(
                    output=content,
                    usage={"input": in_tok, "output": out_tok},
                    metadata={"latency_ms": latency_ms},
                )
            except Exception as exc:
                logger.warning("langfuse_generation_close_failed", error=str(exc))

        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            generation_id=generation_id,
        )


def get_llm_provider() -> BaseLLMProvider:
    """Factory — returns the configured provider."""
    if settings.llm_provider in ("openai", "openrouter"):
        return OpenAICompatibleProvider()
    raise NotImplementedError(f"LLM provider not implemented: {settings.llm_provider}")
