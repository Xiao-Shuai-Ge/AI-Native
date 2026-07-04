"""Test helpers for database migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config() -> Config:
    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    return cfg


def upgrade_database_to_head() -> None:
    command.upgrade(_alembic_config(), "head")


def stamp_database_head() -> None:
    command.stamp(_alembic_config(), "head")
