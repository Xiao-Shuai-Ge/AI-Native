"""Runs the MCP Server over Streamable HTTP (`python -m mcp_server`)."""

from __future__ import annotations

import uvicorn

from mcp_server.config import get_settings
from mcp_server.server import create_app


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.mcp_server_host, port=settings.mcp_server_port)


if __name__ == "__main__":
    main()
