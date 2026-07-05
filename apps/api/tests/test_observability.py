"""Observability unit tests."""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from api.main import app
from llm.protocol import TokenUsage
from observability import metrics
from observability.log_config import JsonFormatter, RedactingFilter, redact_text
from observability.metrics_server import start_metrics_server
from observability.task_tokens import merge_token_usage, token_usage_from_runtime
from observability.tracing import setup_tracing, start_span


@pytest.fixture
async def client() -> AsyncClient:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def test_redact_text_masks_api_key() -> None:
    redacted = redact_text("Authorization: Bearer sk-test-secret-key-12345")
    assert "sk-test" not in redacted
    assert "[REDACTED]" in redacted


def test_redacting_filter_masks_extra_fields() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="provider call",
        args=(),
        exc_info=None,
    )
    record.api_key = "sk-live-secret"
    RedactingFilter().filter(record)
    assert record.api_key == "[REDACTED]"


def test_json_formatter_includes_trace_id() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("observability.test")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    with start_span("test.span", attributes={"task_id": "task-1"}):
        logger.info("hello", extra={"task_id": "task-1"})

    payload = json.loads(stream.getvalue().strip())
    assert payload["message"] == "hello"
    assert "trace_id" in payload
    assert len(payload["trace_id"]) == 32


def test_record_llm_tokens_unknown_when_usage_missing() -> None:
    before = metrics.llm_tokens_total.labels(provider="fake", token_type="unknown")._value.get()  # noqa: SLF001
    metrics.record_llm_tokens(provider="fake", usage=None)
    after = metrics.llm_tokens_total.labels(provider="fake", token_type="unknown")._value.get()  # noqa: SLF001
    assert after == before + 1.0


def test_record_llm_tokens_counts_prompt_and_completion() -> None:
    usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    metrics.record_llm_tokens(provider="fake-count", usage=usage)
    assert (
        metrics.llm_tokens_total.labels(provider="fake-count", token_type="prompt")._value.get()  # noqa: SLF001
        >= 10
    )
    assert (
        metrics.llm_tokens_total.labels(provider="fake-count", token_type="completion")._value.get()  # noqa: SLF001
        >= 5
    )


def test_setup_tracing_disabled_endpoint() -> None:
    setup_tracing(service_name="test", endpoint="none")


def test_metrics_server_serves_prometheus_text() -> None:
    server = start_metrics_server(0)
    host, port = server.server_address
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://{host}:{port}/metrics", timeout=2) as response:  # noqa: S310
            body = response.read().decode()
        assert "api_up" in body
        assert "task_completions_total" in body
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_observability_series(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    for metric_name in (
        "api_up",
        "task_completions_total",
        "task_duration_seconds",
        "llm_requests_total",
        "llm_tokens_total",
        "tool_calls_total",
    ):
        assert metric_name in body


def test_merge_token_usage_sums_known_fields() -> None:
    first = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    second = TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    merged = merge_token_usage(merge_token_usage(None, first), second)
    assert merged["prompt_tokens"] == 13
    assert merged["completion_tokens"] == 7
    assert merged["total_tokens"] == 20
    assert merged["status"] == "known"


def test_merge_token_usage_partial_when_fields_missing() -> None:
    partial = TokenUsage(prompt_tokens=4, completion_tokens=None, total_tokens=None)
    merged = merge_token_usage(None, partial)
    assert merged["prompt_tokens"] == 4
    assert merged["completion_tokens"] is None
    assert merged["status"] == "partial"


def test_token_usage_from_runtime_unknown_when_missing() -> None:
    summary = token_usage_from_runtime(None)
    assert summary["status"] == "unknown"
