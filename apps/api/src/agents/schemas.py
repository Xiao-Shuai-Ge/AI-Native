"""Writer agent structured output schemas."""

from pydantic import BaseModel, Field


class WriterSummary(BaseModel):
    """Structured writer output for topic summaries."""

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
