"""MCP client error types.

Mirrors `mcp_server.errors.ToolErrorCode` on the client side so callers get
the same audit-safe error taxonomy regardless of whether the failure
happened inside the tool (`{"error_code": ..., "error_message": ...}`
payload) or at the transport/protocol layer (timeout, connection refused,
unknown tool).
"""

from __future__ import annotations

from enum import StrEnum


class MCPToolErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    OVERSIZED_RESPONSE = "oversized_response"
    INTERNAL_ERROR = "internal_error"


class MCPToolError(Exception):
    """Raised by `MCPClient` for both tool-reported and transport-level failures."""

    def __init__(self, code: MCPToolErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")
