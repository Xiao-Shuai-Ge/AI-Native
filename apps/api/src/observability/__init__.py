"""Observability initialization for API and worker processes."""

from __future__ import annotations

import logging
import os

from api.config import Settings
from observability import metrics
from observability.log_config import setup_logging
from observability.tracing import setup_tracing


def init_observability(settings: Settings, service_name: str) -> None:
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    setup_logging()
    setup_tracing(
        service_name=service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
    )
    metrics.set_api_up(1.0)
    logging.getLogger(__name__).info(
        "observability initialized",
        extra={"service_name": service_name},
    )
