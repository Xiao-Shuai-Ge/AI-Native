"""OpenTelemetry tracing helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

_tracer_provider: TracerProvider | None = None


def setup_tracing(*, service_name: str, endpoint: str) -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    if endpoint and endpoint.lower() not in {"none", "disabled", ""}:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 4317)
        insecure = parsed.scheme in {"http", "grpc"}
        exporter = OTLPSpanExporter(endpoint=f"{host}:{port}", insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


def inject_trace_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    inject(headers)
    return headers


def extract_traceparent(traceparent: str | None) -> Mapping[str, str] | None:
    if not traceparent:
        return None
    return {"traceparent": traceparent}


@contextmanager
def attach_trace_context(traceparent: str | None) -> Iterator[None]:
    carrier = extract_traceparent(traceparent)
    if carrier is None:
        yield
        return
    token = attach(extract(carrier))
    try:
        yield
    finally:
        detach(token)


@contextmanager
def start_span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    tracer_name: str = "ainative",
) -> Iterator[Span]:
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def set_span_ok(span: Span) -> None:
    span.set_status(Status(StatusCode.OK))
