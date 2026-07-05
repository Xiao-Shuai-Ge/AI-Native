"""Bridges CrewAI's `BaseLLM` interface to the project's shared `LLMClient`.

CrewAI ships with litellm-based providers that would otherwise bypass our
`LLMClient` abstraction (see AGENTS.md section 2: "所有供应商必须走同一个
`LLMClient` 接口"). Subclassing `crewai.llms.base_llm.BaseLLM` lets every
CrewAI Agent call our existing DeepSeek/Ollama/OpenAI/Claude adapters instead
of talking to providers directly.

`BaseLLM.call()` is a synchronous method invoked by CrewAI's agent executor
(itself run inside a worker thread by `Crew.kickoff_async`). The bridge
schedules async `LLMClient` work back onto the Activity loop captured by
`roles_runner` via `asyncio.run_coroutine_threadsafe`, with an Activity-aligned
timeout. When no loop is available (unit tests), it falls back to a short-lived
thread with the same timeout budget.

When constructed with `mcp_client`/`tools`, `call()` runs the exact same
`agents.tool_loop.run_tool_loop` used by the LangGraph engine (AGENTS.md
section 8: "两个引擎共用...实现") instead of CrewAI's native `tools`/
`available_functions` mechanism, which would require bypassing `LLMClient`.
Every tool call made during a `call()` is appended to `tool_call_records` so
`roles_runner` can read it back after `Crew.kickoff_async()` completes.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from crewai.llms.base_llm import BaseLLM
from pydantic import BaseModel

from agents.tool_loop import run_tool_loop
from llm.protocol import ChatMessage, ChatRole, LLMClient, ToolDefinition
from mcp_client.client import MCPClient
from orchestration.models import ToolCallRecord

if TYPE_CHECKING:
    from crewai.agents.agent_builder.base_agent import BaseAgent
    from crewai.task import Task
    from crewai.tools.base_tool import BaseTool
    from crewai.utilities.types import LLMMessage

logger = logging.getLogger(__name__)

# Slightly below the default CrewAI Activity timeout so bridge calls fail first.
DEFAULT_LLM_CALL_TIMEOUT_SECONDS = 115.0


def _run_coroutine_sync[T](
    coro: Coroutine[Any, Any, T],
    *,
    timeout: float | None,
) -> T:
    """Runs an async coroutine to completion from synchronous code.

    Fallback when no caller event loop is available: uses a short-lived thread.
    """
    result: dict[str, T] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised on caller thread
            error["exc"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        msg = "CrewAI LLM call timed out"
        raise TimeoutError(msg)
    if "exc" in error:
        raise error["exc"]
    return result["value"]


def _run_async_llm[T](
    coro: Coroutine[Any, Any, T],
    *,
    async_loop: asyncio.AbstractEventLoop | None,
    timeout: float | None,
) -> T:
    """Runs an LLM coroutine from CrewAI's synchronous `BaseLLM.call()`.

    Prefer scheduling on the caller's running loop (the Activity worker loop
    captured by `roles_runner`) so we avoid spawning extra threads and can
    honour Activity-aligned timeouts via `future.result(timeout=...)`.
    """
    if async_loop is not None and async_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, async_loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            msg = "CrewAI LLM call timed out"
            raise TimeoutError(msg) from exc

    return _run_coroutine_sync(coro, timeout=timeout)


def _to_chat_messages(messages: str | list[LLMMessage]) -> list[ChatMessage]:
    if isinstance(messages, str):
        return [ChatMessage(role=ChatRole.USER, content=messages)]
    converted: list[ChatMessage] = []
    for message in messages:
        role_value = message.get("role", "user")
        try:
            role = ChatRole(role_value)
        except ValueError:
            role = ChatRole.USER
        converted.append(ChatMessage(role=role, content=str(message.get("content", ""))))
    return converted


class CrewAILLMBridge(BaseLLM):
    """CrewAI `BaseLLM` implementation backed by the shared `LLMClient`."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        task_id: str | None = None,
        async_loop: asyncio.AbstractEventLoop | None = None,
        call_timeout: float | None = DEFAULT_LLM_CALL_TIMEOUT_SECONDS,
        mcp_client: MCPClient | None = None,
        tools: list[ToolDefinition] | None = None,
    ) -> None:
        provider_info = llm_client.provider_info
        super().__init__(model=f"{provider_info.provider}/{provider_info.model}")
        self._llm_client = llm_client
        self._task_id = task_id
        self._async_loop = async_loop
        self._call_timeout = call_timeout
        self._mcp_client = mcp_client
        self._tools = tools or []
        self.tool_call_records: list[ToolCallRecord] = []

    def call(
        self,
        messages: str | list[LLMMessage],
        tools: list[dict[str, BaseTool]] | None = None,  # noqa: ARG002 - see class docstring
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,  # noqa: ARG002
        from_task: Task | None = None,
        from_agent: BaseAgent | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        chat_messages = _to_chat_messages(messages)
        if response_model is not None:
            parsed = _run_async_llm(
                self._llm_client.chat_structured(
                    chat_messages,
                    response_model,
                    task_id=self._task_id,
                ),
                async_loop=self._async_loop,
                timeout=self._call_timeout,
            )
            return parsed.model_dump_json()

        if self._tools and self._mcp_client is not None:
            loop_result = _run_async_llm(
                run_tool_loop(
                    llm=self._llm_client,
                    messages=chat_messages,
                    tools=self._tools,
                    mcp_client=self._mcp_client,
                    task_id=self._task_id,
                ),
                async_loop=self._async_loop,
                timeout=self._call_timeout,
            )
            self.tool_call_records.extend(loop_result.tool_calls)
            return loop_result.final_content

        response = _run_async_llm(
            self._llm_client.chat(chat_messages, task_id=self._task_id),
            async_loop=self._async_loop,
            timeout=self._call_timeout,
        )
        return response.content
