"""TavilySearchTool: live web search for Scout, the CrewAI Researcher agent.

Wired into src/crew.py (Scout's agent only). Scout otherwise
reasons from training knowledge alone; this tool gives it live Tavily
results (1 credit per basic search on the Researcher plan, 1,000/month).

The real API key never leaves Muse's secure storage: each request
carries an hsurr:* surrogate in the Authorization: Bearer header, swapped
for the real key on approved egress to api.tavily.com — the same pattern
as the connector helper at
~/workspace/custom-connectors/custom.tavily/bin/tavily_call.py and
src/vault_llm.py (Gemini).

Failures are soft: after retries on timeouts and retryable HTTP errors,
the tool returns an explanatory string instead of raising, so one failed
search never kills the crew run.
"""
import json
import sys
import time
import urllib.error
import urllib.request

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

CREDENTIAL = "custom.tavily"
HOSTS = ["api.tavily.com"]
BASE = "https://api.tavily.com"
RETRYABLE = {429, 500, 502, 503, 504}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


class TavilySearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "A short web search query, e.g. "
            "'small business social media posting consistency tips'."
        ),
    )
    max_results: int = Field(
        5, description="How many results to return (1-10, default 5)."
    )


def _format_results(results: list[dict]) -> str:
    if not results:
        return "Tavily returned no results for that query."
    lines = []
    for item in results:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = (item.get("content", "") or "")[:300].replace("\n", " ")
        lines.append(f"- {title} ({url}): {snippet}")
    return "\n".join(lines)


class TavilySearchTool(BaseTool):
    """CrewAI tool: one basic Tavily web search per call."""

    name: str = "Tavily web search"
    description: str = (
        "Search the live web for timely topics, news, and facts. Input: a "
        "short search query. Returns a compact list of results, each with "
        "a title, the source URL, and a short snippet. Use it to ground "
        "every research angle in something real, and cite the source URLs "
        "it returns."
    )
    args_schema: type[BaseModel] = TavilySearchInput
    max_attempts: int = 3

    def _run(self, query: str, max_results: int = 5) -> str:
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": max(1, min(int(max_results), 10)),
        }
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | str | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                BASE + "/search", data=body, method="POST"
            )
            request.add_header("Content-Type", "application/json")
            add_surrogate_to_request(request, CREDENTIAL, allowed_hosts=HOSTS)
            try:
                with urllib.request.build_opener(_NoRedirect()).open(
                    request, timeout=90
                ) as response:
                    result = read_json_response(response)
                return _format_results(result.get("results", []))
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:200]
                last_error = f"HTTP {err.code}: {detail}"
                if err.code not in RETRYABLE:
                    break
            except Exception as err:  # timeouts, disconnects: retryable
                last_error = err
            if attempt < self.max_attempts:
                time.sleep(min(5 * attempt, 15))
        return (
            f"Tavily search failed ({last_error}). Continue without live "
            "results and mark anything uncertain as an opinion angle."
        )
