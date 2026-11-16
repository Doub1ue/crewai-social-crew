"""VaultGeminiLLM: a CrewAI LLM that talks to Google Gemini using the
vault-held API key from the google-gemini connector.

Why this exists: the real API key never leaves Muse's secure storage.
Each request carries an hsurr:* surrogate in the x-goog-api-key header,
swapped for the real key on approved egress to Google. Calls go through
urllib with explicit retries/backoff, because the free tier regularly
answers 503 (high demand) and the egress path can be slow.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from crewai.llms.base_llm import BaseLLM

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

CREDENTIAL = "custom.google-gemini"
HOSTS = ["generativelanguage.googleapis.com"]
BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE = {429, 500, 502, 503, 504}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def _message_parts(messages) -> tuple[str, list[dict]]:
    """Split CrewAI messages into (system_instruction, gemini contents)."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    system_chunks: list[str] = []
    contents: list[dict] = []
    for msg in messages:
        if isinstance(msg, dict):
            role, content = msg.get("role", "user"), msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
        if isinstance(content, list):  # multimodal-style parts: keep text only
            content = "\n".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type", "text") == "text"
            )
        text = str(content)
        if role == "system":
            system_chunks.append(text)
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})
    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]
    return "\n\n".join(system_chunks), contents


class VaultGeminiLLM(BaseLLM):
    """CrewAI LLM backed by Gemini + the vault surrogate, with retries."""

    model: str = "gemini-3.5-flash-lite"
    temperature: float = 0.7
    max_attempts: int = 6

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
        system_instruction, contents = _message_parts(messages)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": self.temperature},
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        stops = getattr(self, "stop_sequences", None)
        if stops:
            payload["generationConfig"]["stopSequences"] = list(stops)

        url = f"{BASE}/models/{self.model}:generateContent"
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(url, data=body, method="POST")
            request.add_header("Content-Type", "application/json")
            add_surrogate_to_request(request, CREDENTIAL, allowed_hosts=HOSTS)
            try:
                with urllib.request.build_opener(_NoRedirect()).open(
                    request, timeout=180
                ) as response:
                    result = read_json_response(response)
                parts = (
                    result.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                text = "".join(part.get("text", "") for part in parts)
                if text:
                    return text
                last_error = RuntimeError(f"empty Gemini response: {str(result)[:200]}")
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:200]
                last_error = RuntimeError(f"Gemini HTTP {err.code}: {detail}")
                if err.code not in RETRYABLE:
                    raise last_error from err
            except Exception as err:  # timeouts, disconnects: retryable here
                last_error = err
            if attempt < self.max_attempts:
                time.sleep(min(15 * attempt, 75))
        raise RuntimeError(
            f"Gemini call failed after {self.max_attempts} attempts: {last_error}"
        )
