"""MCP tool discovery route: lists tools dynamically found on `mcp-server`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.config import Settings, get_settings
from mcp_client.errors import MCPToolError
from mcp_client.factory import create_mcp_client

router = APIRouter(prefix="/api", tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    tools: list[ToolInfo] = Field(default_factory=list)


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ToolListResponse:
    client = create_mcp_client(settings)
    try:
        discovered = await client.discover_tools()
    except MCPToolError as exc:
        raise HTTPException(
            status_code=503, detail=f"mcp-server unavailable: {exc.code.value}"
        ) from exc
    return ToolListResponse(
        tools=[
            ToolInfo(name=tool.name, description=tool.description, input_schema=tool.input_schema)
            for tool in discovered
        ]
    )
