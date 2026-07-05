"""Dependency readiness checks for /ready endpoint."""

import asyncio
import logging
from typing import Any

import asyncpg
import httpx
import redis.asyncio as aioredis

from api.config import Settings
from mcp_client.errors import MCPToolError
from mcp_client.factory import create_mcp_client

logger = logging.getLogger(__name__)


async def check_redis(settings: Settings) -> dict[str, Any]:
    client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2.0,
    )
    try:
        pong = await client.ping()
        return {"status": "ok" if pong else "error"}
    except Exception as exc:
        logger.warning("redis readiness check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}
    finally:
        await client.aclose()


async def check_postgres(settings: Settings) -> dict[str, Any]:
    try:
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            timeout=2.0,
        )
        try:
            value = await conn.fetchval("SELECT 1")
            return {"status": "ok" if value == 1 else "error"}
        finally:
            await conn.close()
    except Exception as exc:
        logger.warning("postgres readiness check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}


async def check_dapr(settings: Settings) -> dict[str, Any]:
    url = f"http://127.0.0.1:{settings.dapr_http_port}/v1.0/healthz"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            if response.status_code == 204:
                return {"status": "ok"}
            return {"status": "error", "detail": f"unexpected status {response.status_code}"}
    except Exception as exc:
        logger.warning("dapr readiness check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}


async def check_mcp(settings: Settings) -> dict[str, Any]:
    try:
        client = create_mcp_client(settings)
        tools = await asyncio.wait_for(client.discover_tools(), timeout=3.0)
    except MCPToolError as exc:
        logger.warning("mcp readiness check failed", extra={"error": exc.message})
        return {"status": "error", "detail": exc.code.value}
    except Exception as exc:
        logger.warning("mcp readiness check failed", extra={"error": str(exc)})
        return {"status": "error", "detail": str(exc)}

    tool_count = len(tools)
    if tool_count >= 4:
        return {"status": "ok", "detail": f"{tool_count} tools discovered"}
    return {"status": "error", "detail": f"expected at least 4 tools, got {tool_count}"}


async def run_readiness_checks(settings: Settings) -> dict[str, Any]:
    redis_result, postgres_result, dapr_result, mcp_result = await asyncio.gather(
        check_redis(settings),
        check_postgres(settings),
        check_dapr(settings),
        check_mcp(settings),
    )
    checks = {
        "redis": redis_result,
        "postgres": postgres_result,
        "dapr": dapr_result,
        "mcp": mcp_result,
    }
    required_ok = all(
        checks[name]["status"] == "ok" for name in ("redis", "postgres", "dapr", "mcp")
    )
    return {
        "status": "ready" if required_ok else "not_ready",
        "checks": checks,
    }
