"""FallbackLLM: a CrewAI LLM wrapper — primary first, fallback on failure.

Wired in src/crew.py build_llm(): agents get a FallbackLLM whose primary
is the normal Gemini LLM (VaultGeminiLLM with the vault-held key, or
CrewAI's native LLM) and whose fallback is VaultOpenRouterLLM
(OpenRouter's free models via the vault-held key).

How it triggers: call() delegates to the primary. The primary already
retries internally (VaultGeminiLLM makes up to 6 attempts with backoff),
so the fallback only fires when the primary call ultimately raises —
exactly "Gemini failed after its retries". The same messages and tool
context are then handed to OpenRouter's openrouter/free router and its
answer is returned as if the primary had answered. If the fallback also
fails, its error propagates.

Free-tier caution (from the 2026-11-17 shortlist): OpenRouter free
endpoints are draft-grade and may retain data — fine for these public
social drafts, never for client-sensitive text.
"""
from typing import Any

from crewai.llms.base_llm import BaseLLM
from pydantic import PrivateAttr


class FallbackLLM(BaseLLM):
    """Try the primary LLM; on any exception, try the fallback LLM."""

    model: str = "fallback"
    temperature: float = 0.7
    _primary: Any = PrivateAttr()
    _fallback: Any = PrivateAttr(default=None)

    def __init__(self, primary: Any, fallback: Any = None, **kwargs: Any):
        super().__init__(
            model=kwargs.pop("model", str(getattr(primary, "model", "fallback"))),
            temperature=kwargs.pop(
                "temperature", float(getattr(primary, "temperature", 0.7) or 0.7)
            ),
            **kwargs,
        )
        self._primary = primary
        self._fallback = fallback

    def call(
        self,
        messages: Any,
        tools: list | None = None,
        callbacks: list | None = None,
        available_functions: dict | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        try:
            return self._primary.call(
                messages,
                tools=tools,
                callbacks=callbacks,
                available_functions=available_functions,
                from_task=from_task,
                from_agent=from_agent,
                response_model=response_model,
            )
        except Exception as primary_error:
            if self._fallback is None:
                raise
            print(
                "[FallbackLLM] primary LLM failed "
                f"({type(primary_error).__name__}: {str(primary_error)[:200]}); "
                "falling back to OpenRouter free models."
            )
            return self._fallback.call(
                messages,
                tools=tools,
                callbacks=callbacks,
                available_functions=available_functions,
                from_task=from_task,
                from_agent=from_agent,
                response_model=response_model,
            )

    def supports_stop_words(self) -> bool:
        fn = getattr(self._primary, "supports_stop_words", None)
        return fn() if callable(fn) else super().supports_stop_words()

    def get_context_window_size(self) -> int:
        fn = getattr(self._primary, "get_context_window_size", None)
        if callable(fn):
            return fn()
        return super().get_context_window_size()
