"""`web_search` tool: queries Bocha/LangSearch.

Per AGENTS.md section 10 ("`web_search` 必须限制 URL、响应大小、返回条数和超
时"), the endpoint is configured by the server (no user-controlled URL),
results are capped, the raw response body is size-limited, and the request has
a hard timeout.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from mcp_server.errors import ToolError, ToolErrorCode

BOCHA_SEARCH_URL = "https://api.bochaai.com/v1/web-search"
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_RESULTS = 5
MAX_RESPONSE_BYTES = 200_000


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=MAX_RESULTS, ge=1, le=MAX_RESULTS)


class SearchResult(BaseModel):
    title: str
    summary: str
    url: str


class WebSearchOutput(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)


def _require_api_key(api_key: str) -> str:
    resolved = api_key.strip()
    if not resolved:
        raise ToolError(ToolErrorCode.UNAUTHORIZED, "Bocha API key is not configured")
    return resolved


def _first_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    web_pages = data.get("data", {}).get("webPages", {})
    hits = web_pages.get("value") if isinstance(web_pages, dict) else None
    if hits is None:
        hits = data.get("results")
    if not isinstance(hits, list):
        raise ToolError(ToolErrorCode.INTERNAL_ERROR, "search provider returned unexpected payload")
    return [hit for hit in hits if isinstance(hit, dict)]


async def search(
    payload: WebSearchInput,
    *,
    http_client: httpx.AsyncClient,
    api_key: str,
    endpoint: str = BOCHA_SEARCH_URL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> WebSearchOutput:
    resolved_key = _require_api_key(api_key)
    body = {
        "query": payload.query,
        "count": payload.max_results,
        "summary": True,
    }
    try:
        response = await http_client.post(
            endpoint,
            json=body,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
            },
        )
    except httpx.TimeoutException as exc:
        raise ToolError(ToolErrorCode.TIMEOUT, "web search timed out") from exc
    except httpx.HTTPError as exc:
        raise ToolError(ToolErrorCode.INTERNAL_ERROR, "web search request failed") from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ToolError(ToolErrorCode.OVERSIZED_RESPONSE, "search response exceeded size limit")
    if response.status_code in {401, 403}:
        raise ToolError(ToolErrorCode.UNAUTHORIZED, "search provider rejected the API key")
    if response.status_code >= 400:
        raise ToolError(ToolErrorCode.INTERNAL_ERROR, "search provider returned an error")

    try:
        data = response.json()
    except ValueError as exc:
        raise ToolError(
            ToolErrorCode.INTERNAL_ERROR, "search provider returned invalid JSON"
        ) from exc

    hits = _extract_hits(data)

    results = [
        SearchResult(
            title=_first_text(hit.get("name"), hit.get("title")),
            summary=_first_text(hit.get("summary"), hit.get("snippet"), hit.get("description")),
            url=_first_text(hit.get("url"), hit.get("link")),
        )
        for hit in hits[: payload.max_results]
        if _first_text(hit.get("url"), hit.get("link"))
    ]
    return WebSearchOutput(results=results)
