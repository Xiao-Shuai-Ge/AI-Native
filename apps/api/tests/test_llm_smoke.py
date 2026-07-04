"""Optional smoke tests against real LLM providers."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from agents.writer import WriterAgent
from api.config import Settings
from llm.factory import create_llm_client


@pytest.mark.smoke
@pytest.mark.network
@pytest.mark.asyncio
async def test_deepseek_smoke_when_configured() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        pytest.skip("DEEPSEEK_API_KEY not configured for smoke test")

    settings = Settings.model_validate(
        {
            "llm_provider": "deepseek",
            "deepseek_api_key": api_key,
        }
    )
    llm = create_llm_client(settings)
    writer = WriterAgent()
    result = await writer.summarize("Dapr Workflow", task_id=uuid4(), llm=llm)
    assert result.markdown
    assert result.title


@pytest.mark.smoke
@pytest.mark.network
@pytest.mark.asyncio
async def test_ollama_smoke_when_available() -> None:
    if os.getenv("LLM_PROVIDER", "ollama") not in {"ollama"}:
        pytest.skip("Set LLM_PROVIDER=ollama to run Ollama smoke test")

    settings = Settings.model_validate({"llm_provider": "ollama"})
    llm = create_llm_client(settings)
    writer = WriterAgent()
    result = await writer.summarize("Dapr Workflow", task_id=uuid4(), llm=llm)
    assert result.markdown
    assert result.title
