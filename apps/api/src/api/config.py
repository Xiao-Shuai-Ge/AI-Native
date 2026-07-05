"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All secrets and connection strings must come from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="ainative", alias="POSTGRES_USER")
    postgres_password: str = Field(default="ainative", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="ainative", alias="POSTGRES_DB")

    dapr_http_port: int = Field(default=3500, alias="DAPR_HTTP_PORT")
    dapr_grpc_port: int = Field(default=50001, alias="DAPR_GRPC_PORT")
    workflow_dapr_grpc_host: str | None = Field(default=None, alias="WORKFLOW_DAPR_GRPC_HOST")
    workflow_dapr_grpc_port: int | None = Field(default=None, alias="WORKFLOW_DAPR_GRPC_PORT")

    mcp_server_url: str = Field(default="http://localhost:8001", alias="MCP_SERVER_URL")
    mcp_service_invocation_app_id: str = Field(
        default="mcp-server", alias="MCP_SERVICE_INVOCATION_APP_ID"
    )
    mcp_tool_call_timeout_seconds: float = Field(
        default=15.0, alias="MCP_TOOL_CALL_TIMEOUT_SECONDS"
    )
    mcp_use_dapr_invocation: bool = Field(default=True, alias="MCP_USE_DAPR_INVOCATION")

    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )

    # Day 2 LLM settings
    llm_provider: str = Field(default="deepseek", alias="LLM_PROVIDER")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen3:8b", alias="OLLAMA_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-3-5-sonnet-latest", alias="ANTHROPIC_MODEL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=1, alias="LLM_MAX_RETRIES")

    task_delay_seconds: float = Field(default=0.0, alias="TASK_DELAY_SECONDS")

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
