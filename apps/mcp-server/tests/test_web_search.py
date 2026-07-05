"""Unit tests for the `web_search` tool."""

from __future__ import annotations

import httpx
import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools.web_search import MAX_RESPONSE_BYTES, WebSearchInput, search


def _bocha_payload(count: int) -> dict:
    return {
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": f"Result {i}",
                        "summary": f"Summary {i}",
                        "url": f"https://example.com/{i}",
                    }
                    for i in range(count)
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_search_returns_parsed_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["content-type"] == "application/json"
        assert request.read() == b'{"query":"dapr workflow","count":5,"summary":true}'
        return httpx.Response(200, json=_bocha_payload(3))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await search(
        WebSearchInput(query="dapr workflow", max_results=5),
        http_client=client,
        api_key="test-key",
    )
    assert len(result.results) == 3
    assert result.results[0].summary == "Summary 0"
    assert result.results[0].url == "https://example.com/0"
    await client.aclose()


@pytest.mark.asyncio
async def test_search_caps_results_to_max_results() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_bocha_payload(5))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await search(
        WebSearchInput(query="topic", max_results=2),
        http_client=client,
        api_key="test-key",
    )
    assert len(result.results) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_search_raises_timeout_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ToolError) as excinfo:
        await search(WebSearchInput(query="topic"), http_client=client, api_key="test-key")
    assert excinfo.value.code == ToolErrorCode.TIMEOUT
    await client.aclose()


@pytest.mark.asyncio
async def test_search_raises_oversized_response_error() -> None:
    big_body = b"x" * (MAX_RESPONSE_BYTES + 1)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_body, headers={"content-type": "application/json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ToolError) as excinfo:
        await search(WebSearchInput(query="topic"), http_client=client, api_key="test-key")
    assert excinfo.value.code == ToolErrorCode.OVERSIZED_RESPONSE
    await client.aclose()


@pytest.mark.asyncio
async def test_search_requires_bocha_api_key() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    with pytest.raises(ToolError) as excinfo:
        await search(WebSearchInput(query="topic"), http_client=client, api_key="")
    assert excinfo.value.code == ToolErrorCode.UNAUTHORIZED
    await client.aclose()


@pytest.mark.asyncio
async def test_search_maps_rejected_api_key_to_unauthorized() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ToolError) as excinfo:
        await search(WebSearchInput(query="topic"), http_client=client, api_key="bad-key")
    assert excinfo.value.code == ToolErrorCode.UNAUTHORIZED
    await client.aclose()


def test_input_rejects_empty_query() -> None:
    with pytest.raises(ValueError):
        WebSearchInput(query="")


def test_input_rejects_over_max_results() -> None:
    with pytest.raises(ValueError):
        WebSearchInput(query="topic", max_results=100)
