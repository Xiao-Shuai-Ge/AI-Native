"""Standard, audit-safe tool error codes.

Per AGENTS.md section 10 ("工具异常返回可审计的错误码，不向模型泄露堆栈、连接串或
内部路径"), every tool failure must be mapped to one of these codes with a
short human-readable message. Internal exception details (stack traces,
connection strings, file paths) must never be included in `message`.
"""

from __future__ import annotations

from enum import StrEnum


class ToolErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    UNAUTHORIZED = "unauthorized"
    OVERSIZED_RESPONSE = "oversized_response"
    INTERNAL_ERROR = "internal_error"


class ToolError(Exception):
    """Raised by tool implementations; carries an audit-safe error code."""

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")
