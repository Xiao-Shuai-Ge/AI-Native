#!/bin/sh
set -e
cd /app/apps/api
uv run alembic upgrade head
exec uv run uvicorn api.main:app --app-dir src --host 0.0.0.0 --port 8000
