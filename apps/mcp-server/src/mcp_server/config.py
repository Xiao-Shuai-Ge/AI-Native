"""MCP Server configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    mcp_server_host: str = Field(default="0.0.0.0", alias="MCP_SERVER_HOST")
    mcp_server_port: int = Field(default=8001, alias="MCP_SERVER_PORT")

    readonly_sql_dsn: str = Field(
        default="postgresql://ainative_readonly:ainative_readonly@localhost:5432/ainative",
        alias="READONLY_SQL_DSN",
    )
    readonly_sql_timeout_seconds: float = Field(default=5.0, alias="READONLY_SQL_TIMEOUT_SECONDS")
    readonly_sql_max_rows: int = Field(default=100, alias="READONLY_SQL_MAX_ROWS")

    web_search_timeout_seconds: float = Field(default=5.0, alias="WEB_SEARCH_TIMEOUT_SECONDS")
    bocha_api_key: str = Field(default="", alias="BOCHA_API_KEY")
    bocha_search_url: str = Field(
        default="https://api.bochaai.com/v1/web-search",
        alias="BOCHA_SEARCH_URL",
    )

    code_runner_image: str = Field(default="python:3.12-alpine", alias="CODE_RUNNER_IMAGE")
    code_runner_timeout_seconds: float = Field(default=5.0, alias="CODE_RUNNER_TIMEOUT_SECONDS")
    code_runner_memory_limit: str = Field(default="128m", alias="CODE_RUNNER_MEMORY_LIMIT")
    code_runner_cpu_limit: str = Field(default="0.5", alias="CODE_RUNNER_CPU_LIMIT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
