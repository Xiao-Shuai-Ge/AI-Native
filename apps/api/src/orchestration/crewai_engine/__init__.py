"""CrewAI implementation of the `OrchestrationEngine` protocol."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# `crewai.Crew()` unconditionally creates a `KickoffTaskOutputsSQLiteStorage`
# (used for its own kickoff-replay cache, which this project does not use --
# our persistence layer is PostgreSQL/Redis per AGENTS.md section 11) and
# resolves its file path via `appdirs.user_data_dir(...)`, which defaults to a
# per-user directory under `$HOME` (e.g. `~/Library/Application Support/<app>`
# on macOS, `~/.local/share/<app>` on Linux). That directory is outside the
# workspace/container-controlled paths and is not guaranteed to be writable
# (restricted sandboxes, read-only-HOME containers, CI runners), which crashes
# every CrewAI role call with `DatabaseOperationError: unable to open database
# file`. Point it at a guaranteed-writable temp directory unless the deployer
# explicitly overrides `CREWAI_STORAGE_DIR` (e.g. to a persistent volume).
# This must run before any `crewai.Crew(...)` is constructed, so it lives at
# this package's import time rather than deep inside `roles_runner.py`.
os.environ.setdefault(
    "CREWAI_STORAGE_DIR",
    str(Path(tempfile.gettempdir()) / "ainative-crewai-storage"),
)

# CrewAI also phones home to `telemetry.crewai.com` by default on every Crew
# run. In network-restricted environments (this project's sandboxed tests,
# offline dev, egress-locked containers) each blocked request retries with
# backoff for tens of seconds, and unconditionally sending call metadata
# externally is undesirable regardless of network policy. Opt out unless the
# deployer explicitly re-enables it.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
