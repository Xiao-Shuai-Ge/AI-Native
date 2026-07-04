"""Development writer routes."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.schemas import WriterSummary
from agents.writer import WriterAgent
from api.config import Settings, get_settings
from llm.errors import LLMConfigurationError, LLMError, LLMParseError, LLMUnavailableError
from llm.factory import create_llm_client

router = APIRouter(prefix="/api/dev/writer", tags=["dev-writer"])


class WriterSummarizeRequest(BaseModel):
    topic: str = Field(min_length=1)
    task_id: UUID | None = None


class WriterSummarizeResponse(BaseModel):
    task_id: UUID
    result: WriterSummary


def get_writer_agent() -> WriterAgent:
    return WriterAgent()


@router.post("/summarize", response_model=WriterSummarizeResponse)
async def summarize_topic(
    body: WriterSummarizeRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    writer: Annotated[WriterAgent, Depends(get_writer_agent)],
) -> WriterSummarizeResponse:
    task_id = body.task_id or uuid4()
    try:
        llm = create_llm_client(settings)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = await writer.summarize(body.topic, task_id=task_id, llm=llm)
    except LLMParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return WriterSummarizeResponse(task_id=task_id, result=result)
