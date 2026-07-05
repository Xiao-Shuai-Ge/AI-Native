"""Unit tests for the `code_runner` tool.

Uses a fake `SandboxRunner` by default so these tests never require Docker;
`test_docker_sandbox_runner_executes_python` is the only test that launches a
real container and is marked `integration`.
"""

from __future__ import annotations

import shutil

import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools.code_runner import (
    CodeRunnerInput,
    DockerSandboxRunner,
    RunResult,
    run_code,
)


class FakeSandboxRunner:
    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str, float]] = []

    async def run(self, *, language: str, code: str, timeout_seconds: float) -> RunResult:
        self.calls.append((language, code, timeout_seconds))
        return self.result


@pytest.mark.asyncio
async def test_run_code_returns_stdout_on_success() -> None:
    runner = FakeSandboxRunner(RunResult(stdout="hello\n", stderr="", exit_code=0))
    output = await run_code(
        CodeRunnerInput(language="python", code="print('hello')"), runner=runner
    )
    assert output.stdout == "hello\n"
    assert output.exit_code == 0
    assert runner.calls[0][0] == "python"


@pytest.mark.asyncio
async def test_run_code_propagates_nonzero_exit_code() -> None:
    runner = FakeSandboxRunner(RunResult(stdout="", stderr="boom", exit_code=1))
    output = await run_code(CodeRunnerInput(language="shell", code="exit 1"), runner=runner)
    assert output.exit_code == 1
    assert output.stderr == "boom"


@pytest.mark.asyncio
async def test_run_code_raises_timeout_error() -> None:
    runner = FakeSandboxRunner(RunResult(stdout="", stderr="", exit_code=-1, timed_out=True))
    with pytest.raises(ToolError) as excinfo:
        await run_code(
            CodeRunnerInput(language="python", code="while True: pass", timeout_seconds=1),
            runner=runner,
        )
    assert excinfo.value.code == ToolErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_run_code_raises_oversized_response_error() -> None:
    from mcp_server.tools.code_runner import MAX_OUTPUT_BYTES

    runner = FakeSandboxRunner(RunResult(stdout="x" * MAX_OUTPUT_BYTES, stderr="", exit_code=0))
    with pytest.raises(ToolError) as excinfo:
        await run_code(CodeRunnerInput(language="python", code="print('x')"), runner=runner)
    assert excinfo.value.code == ToolErrorCode.OVERSIZED_RESPONSE


def test_input_rejects_unsupported_language() -> None:
    with pytest.raises(ValueError):
        CodeRunnerInput(language="ruby", code="puts 1")  # type: ignore[arg-type]


def test_input_rejects_timeout_over_max() -> None:
    with pytest.raises(ValueError):
        CodeRunnerInput(language="python", code="pass", timeout_seconds=60)


def test_input_rejects_code_over_max_length() -> None:
    with pytest.raises(ValueError):
        CodeRunnerInput(language="python", code="x" * 5000)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_docker_sandbox_runner_executes_python() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available in this environment")

    runner = DockerSandboxRunner()
    result = await runner.run(language="python", code="print(1 + 1)", timeout_seconds=10)
    assert result.exit_code == 0
    assert result.stdout.strip() == "2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_docker_sandbox_runner_has_no_network_access() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available in this environment")

    runner = DockerSandboxRunner()
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=2)\n"
        "    print('network-reachable')\n"
        "except Exception:\n"
        "    print('network-blocked')\n"
    )
    result = await runner.run(language="python", code=code, timeout_seconds=10)
    assert "network-blocked" in result.stdout
