"""Pytest configuration for API tests."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "none")

API_SRC = Path(__file__).resolve().parents[1] / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))


@pytest.fixture(scope="session", autouse=True)
def ensure_integration_schema(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("-m", default=""):
        return
    marker_expr = request.config.getoption("-m", default="")
    if "integration" not in marker_expr:
        return

    from tests.db_helpers import upgrade_database_to_head

    upgrade_database_to_head()
