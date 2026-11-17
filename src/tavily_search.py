"""Tavily web search helpers (plain-function form).

The CrewAI tool the Researcher actually uses is src/tavily_tool.py
(TavilySearchTool, a BaseTool subclass with retries), wired into
src/crew.py on 2026-11-17. This module remains as a small standalone
helper for one-off searches outside the crew. The vault key was verified
live through the vault on 2026-11-17: Researcher plan, 1,000
credits/month.

Why this exists: the Researcher currently has no search tool, so it can
only reason from the model's training knowledge. Tavily gives it live web
results (1 credit per basic search). The real API key never leaves secure
storage: each request carries an hsurr:* surrogate, swapped for the real
key on approved egress to api.tavily.com — the same pattern as
src/vault_llm.py (Gemini) and the helper at
~/workspace/custom-connectors/custom.tavily/bin/tavily_call.py.

To use outside the crew:
  from src.tavily_search import search_tavily, format_results
"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

CREDENTIAL = "custom.tavily"
HOSTS = ["api.tavily.com"]
BASE = "https://api.tavily.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """One basic Tavily search. Returns [{title, url, snippet}]."""
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(BASE + "/search", data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    add_surrogate_to_request(request, CREDENTIAL, allowed_hosts=HOSTS)
    with urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=60
    ) as response:
        result = read_json_response(response)
    out = []
    for item in result.get("results", []):
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": (item.get("content", "") or "")[:300],
            }
        )
    return out


def format_results(results: list[dict]) -> str:
    if not results:
        return "Tavily returned no results."
    lines = []
    for item in results:
        lines.append(f"- {item['title']} ({item['url']}): {item['snippet']}")
    return "\n".join(lines)


try:
    from crewai.tools import tool as _crewai_tool

    @_crewai_tool("Tavily web search")
    def tavily_search_tool(query: str) -> str:
        """Search the live web for timely topics, news, or facts.

        Args:
            query: a short search query, e.g. 'small business email tips 2026'.
        Returns a short list of results with title, URL, and snippet each.
        """
        try:
            return format_results(search_tavily(query, max_results=5))
        except urllib.error.HTTPError as err:
            return f"Tavily search failed: HTTP {err.code}."
        except Exception as err:  # noqa: BLE001 - fail soft, keep the crew running
            return f"Tavily search failed: {err}"

except Exception:  # pragma: no cover - crewai.tools unavailable
    tavily_search_tool = None  # type: ignore[assignment]
