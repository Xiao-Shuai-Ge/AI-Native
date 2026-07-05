"""Builds an `MCPClient` pointed at the MCP server via Dapr Service Invocation.

Per AGENTS.md section 9 ("MCP app 必须优先通过 Dapr Service Invocation 调用"),
`api`/`worker` reach `mcp-server` through their local Dapr sidecar's HTTP
invoke endpoint rather than a hardcoded service URL, so tracing headers and
mTLS/access-control policies apply uniformly. `MCP_USE_DAPR_INVOCATION=false`
falls back to calling `MCP_SERVER_URL` directly for local dev without Dapr.
"""

from __future__ import annotations

from api.config import Settings
from mcp_client.client import MCPClient


def resolve_mcp_base_url(settings: Settings) -> str:
    if settings.mcp_use_dapr_invocation:
        return (
            f"http://localhost:{settings.dapr_http_port}"
            f"/v1.0/invoke/{settings.mcp_service_invocation_app_id}/method"
        )
    return settings.mcp_server_url


def create_mcp_client(
    settings: Settings, *, trace_headers: dict[str, str] | None = None
) -> MCPClient:
    return MCPClient(
        base_url=resolve_mcp_base_url(settings),
        headers=trace_headers,
        timeout=settings.mcp_tool_call_timeout_seconds,
    )
