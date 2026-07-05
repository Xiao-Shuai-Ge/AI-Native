"""`code_runner` tool: runs short Python/Shell snippets in an isolated container.

Per AGENTS.md section 10, `code_runner` may only run inside an independent
sandbox container: non-root user, no network, read-only root filesystem,
dropped Linux capabilities, and CPU/memory/process/time limits. The sandbox
container never mounts the host project directory, the Docker socket, or any
secrets — only this MCP server process (which itself runs in its own
container, see `infra/docker/Dockerfile.mcp-server`) talks to the host Docker
daemon to launch one-shot sandbox containers.

`SandboxRunner` is a small Protocol so tests can inject a fake runner and
never require Docker to be installed; only `integration`-marked tests
exercise `DockerSandboxRunner` for real.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from mcp_server.errors import ToolError, ToolErrorCode

MAX_CODE_LENGTH = 4_000
MAX_OUTPUT_BYTES = 20_000
DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 10.0
DEFAULT_SANDBOX_IMAGE = "python:3.12-alpine"

_LANGUAGE_COMMANDS: dict[str, list[str]] = {
    "python": ["python3", "-"],
    "shell": ["sh", "-s"],
}


class CodeRunnerInput(BaseModel):
    language: Literal["python", "shell"]
    code: str = Field(min_length=1, max_length=MAX_CODE_LENGTH)
    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0, le=MAX_TIMEOUT_SECONDS)


class CodeRunnerOutput(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class SandboxRunner(Protocol):
    async def run(self, *, language: str, code: str, timeout_seconds: float) -> RunResult: ...


class DockerSandboxRunner:
    """Launches one `docker run --rm` sandbox container per call.

    Flags implement AGENTS.md section 10's isolation requirements: no
    network, read-only rootfs, non-root user, dropped capabilities, and
    resource limits. Code is piped over stdin so the read-only container
    never needs a writable bind mount for the script file.
    """

    def __init__(
        self,
        *,
        image: str = DEFAULT_SANDBOX_IMAGE,
        memory_limit: str = "128m",
        cpu_limit: str = "0.5",
        pids_limit: int = 64,
    ) -> None:
        self._image = image
        self._memory_limit = memory_limit
        self._cpu_limit = cpu_limit
        self._pids_limit = pids_limit

    async def run(self, *, language: str, code: str, timeout_seconds: float) -> RunResult:
        container_name = f"ainative-sandbox-{uuid.uuid4().hex[:12]}"
        command = _LANGUAGE_COMMANDS[language]
        docker_args = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "--network=none",
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop=ALL",
            "--pids-limit",
            str(self._pids_limit),
            "--memory",
            self._memory_limit,
            "--cpus",
            self._cpu_limit,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            self._image,
            *command,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ToolError(
                ToolErrorCode.INTERNAL_ERROR, "sandbox runtime is not available"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(code.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            await self._force_kill(container_name, process)
            return RunResult(stdout="", stderr="execution timed out", exit_code=-1, timed_out=True)

        stdout = stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        stderr = stderr_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        return RunResult(stdout=stdout, stderr=stderr, exit_code=process.returncode or 0)

    @staticmethod
    async def _force_kill(container_name: str, process: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        kill_process = await asyncio.create_subprocess_exec(
            "docker",
            "kill",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await kill_process.wait()


async def run_code(payload: CodeRunnerInput, *, runner: SandboxRunner) -> CodeRunnerOutput:
    result = await runner.run(
        language=payload.language,
        code=payload.code,
        timeout_seconds=payload.timeout_seconds,
    )
    if result.timed_out:
        raise ToolError(ToolErrorCode.TIMEOUT, "code execution exceeded the time limit")
    if len(result.stdout) >= MAX_OUTPUT_BYTES or len(result.stderr) >= MAX_OUTPUT_BYTES:
        raise ToolError(ToolErrorCode.OVERSIZED_RESPONSE, "code output exceeded the size limit")
    return CodeRunnerOutput(stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code)
