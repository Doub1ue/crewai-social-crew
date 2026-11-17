"""VaultOpenRouterLLM: a CrewAI LLM backed by OpenRouter's free models,
using the vault-held API key from the custom.openrouter connector.

Wired into src/crew.py as the FALLBACK model: build_llm() wraps the
primary Gemini LLM in src/fallback_llm.py's FallbackLLM, so this LLM is
only called when the Gemini call fails after Gemini's own retries. (The
first vault paste on 2026-11-17 was a bad copy and returned 401; the key
was re-pasted the same day and verified live — a /key read and chat
calls succeed.)

Why this exists: the real API key never leaves secure storage. Each
request carries an hsurr:* surrogate in the Authorization header, swapped
for the real key on approved egress to openrouter.ai — the same pattern as
src/vault_llm.py (Gemini) and the helper at
~/workspace/custom-connectors/custom.openrouter/bin/openrouter_call.py.

Model: "openrouter/free" (the auto-router over $0 models, as used by
openrouter_call.py chat), overridable with the OPENROUTER_MODEL env var.
Free-tier notes from the 2026-11-17 shortlist: ~50 requests/day default,
draft-grade only — no client-sensitive text on free endpoints.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from crewai.llms.base_llm import BaseLLM

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

CREDENTIAL = "custom.openrouter"
HOSTS = ["openrouter.ai"]
BASE = "https://openrouter.ai/api/v1"
RETRYABLE = {429, 500, 502, 503, 504}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def _to_openai_messages(messages) -> list[dict]:
    """Convert CrewAI messages (str / dicts / objects) to OpenAI format."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    out: list[dict] = []
    for msg in messages:
        if isinstance(msg, dict):
            role, content = msg.get("role", "user"), msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type", "text") == "text"
            )
        if role not in ("system", "user", "assistant"):
            role = "user"
        out.append({"role": role, "content": str(content)})
    if not out:
        out.append({"role": "user", "content": ""})
    return out


class VaultOpenRouterLLM(BaseLLM):
    """CrewAI LLM backed by OpenRouter free models + the vault surrogate."""

    model: str = "openrouter/free"
    temperature: float = 0.7
    max_attempts: int = 4

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
        payload: dict[str, Any] = {
            "model": os.getenv("OPENROUTER_MODEL", self.model),
            "messages": _to_openai_messages(messages),
            "temperature": self.temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                BASE + "/chat/completions", data=body, method="POST"
            )
            request.add_header("Content-Type", "application/json")
            request.add_header("X-OpenRouter-Title", "CrewAI Social Crew")
            add_surrogate_to_request(request, CREDENTIAL, allowed_hosts=HOSTS)
            try:
                with urllib.request.build_opener(_NoRedirect()).open(
                    request, timeout=120
                ) as response:
                    result = read_json_response(response)
                text = (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    or ""
                )
                if text:
                    return text
                last_error = RuntimeError(
                    f"empty OpenRouter response: {str(result)[:200]}"
                )
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:200]
                last_error = RuntimeError(
                    f"OpenRouter HTTP {err.code}: {detail}"
                )
                if err.code not in RETRYABLE:
                    raise last_error from err
            except Exception as err:  # timeouts, disconnects: retryable here
                last_error = err
            if attempt < self.max_attempts:
                time.sleep(min(10 * attempt, 40))
        raise RuntimeError(
            f"OpenRouter failed after {self.max_attempts} attempts: {last_error}"
        )
