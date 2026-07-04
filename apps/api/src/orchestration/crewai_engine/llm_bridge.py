"""Bridges CrewAI's `BaseLLM` interface to the project's shared `LLMClient`.

CrewAI ships with litellm-based providers that would otherwise bypass our
`LLMClient` abstraction (see AGENTS.md section 2: "所有供应商必须走同一个
`LLMClient` 接口"). Subclassing `crewai.llms.base_llm.BaseLLM` lets every
CrewAI Agent call our existing DeepSeek/Ollama/OpenAI/Claude adapters instead
of talking to providers directly.

`BaseLLM.call()` is a synchronous method invoked by CrewAI's agent executor
(itself run inside a worker thread by `Crew.kickoff_async`), so each call
spins up a short-lived event loop in a dedicated thread to run the async
`LLMClient` methods without touching whatever loop is driving the workflow
activity.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from crewai.llms.base_llm import BaseLLM
from pydantic import BaseModel

from llm.protocol import ChatMessage, ChatRole, LLMClient

if TYPE_CHECKING:
    from crewai.agents.agent_builder.base_agent import BaseAgent
    from crewai.task import Task
    from crewai.tools.base_tool import BaseTool
    from crewai.utilities.types import LLMMessage

logger = logging.getLogger(__name__)


def _run_coroutine_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Runs an async coroutine to completion from synchronous code.

    Always executes in a fresh thread + event loop so this is safe to call
    regardless of whether the calling thread already has a running loop.
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
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result["value"]


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

    def __init__(self, *, llm_client: LLMClient, task_id: str | None = None) -> None:
        provider_info = llm_client.provider_info
        super().__init__(model=f"{provider_info.provider}/{provider_info.model}")
        self._llm_client = llm_client
        self._task_id = task_id

    def call(
        self,
        messages: str | list[LLMMessage],
        tools: list[dict[str, BaseTool]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Task | None = None,
        from_agent: BaseAgent | None = None,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        chat_messages = _to_chat_messages(messages)
        if response_model is not None:
            parsed = _run_coroutine_sync(
                self._llm_client.chat_structured(
                    chat_messages,
                    response_model,
                    task_id=self._task_id,
                )
            )
            return parsed.model_dump_json()
        response = _run_coroutine_sync(self._llm_client.chat(chat_messages, task_id=self._task_id))
        return response.content
