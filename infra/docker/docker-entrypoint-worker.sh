#!/bin/sh
set -e

exec uv run python -m workflows.worker_main
