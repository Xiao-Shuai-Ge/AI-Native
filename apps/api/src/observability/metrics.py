"""Prometheus metrics with low-cardinality labels only."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from llm.protocol import TokenUsage

api_up = Gauge("api_up", "API process is running.")

task_completions_total = Counter(
    "task_completions_total",
    "Total task completions by engine and status.",
    ["engine", "status"],
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task duration from initialize to finalize.",
    ["engine"],
    buckets=(1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests by provider and status.",
    ["provider", "status"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds.",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens by provider and token type.",
    ["provider", "token_type"],
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total MCP tool calls by engine and status.",
    ["engine", "status"],
)


def set_api_up(value: float = 1.0) -> None:
    api_up.set(value)


def record_task_completion(*, engine: str, status: str) -> None:
    task_completions_total.labels(engine=engine, status=status).inc()


def record_task_duration(*, engine: str, duration_seconds: float) -> None:
    task_duration_seconds.labels(engine=engine).observe(duration_seconds)


def record_llm_request(*, provider: str, status: str, duration_seconds: float) -> None:
    llm_requests_total.labels(provider=provider, status=status).inc()
    llm_request_duration_seconds.labels(provider=provider).observe(duration_seconds)


def record_llm_tokens(*, provider: str, usage: TokenUsage | None) -> None:
    if usage is None:
        llm_tokens_total.labels(provider=provider, token_type="unknown").inc()
        return

    has_value = False
    if usage.prompt_tokens is not None:
        llm_tokens_total.labels(provider=provider, token_type="prompt").inc(usage.prompt_tokens)
        has_value = True
    if usage.completion_tokens is not None:
        llm_tokens_total.labels(provider=provider, token_type="completion").inc(
            usage.completion_tokens
        )
        has_value = True
    if usage.total_tokens is not None:
        llm_tokens_total.labels(provider=provider, token_type="total").inc(usage.total_tokens)
        has_value = True
    if not has_value:
        llm_tokens_total.labels(provider=provider, token_type="unknown").inc()


def record_tool_call(*, engine: str, status: str) -> None:
    tool_calls_total.labels(engine=engine, status=status).inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
