"""Minimal writer role configuration for Day 2."""

from pydantic import BaseModel, Field


class WriterRoleConfig(BaseModel):
    role: str
    goal: str
    backstory: str
    instructions: str
    version: str = Field(default="v1")


WRITER_ROLE = WriterRoleConfig(
    role="Technical Writer",
    goal="Produce concise, accurate Markdown summaries for the given topic.",
    backstory=(
        "You specialize in turning complex technical topics into readable summaries "
        "for engineering teams."
    ),
    instructions=(
        "Write a short title, one-paragraph summary, and Markdown body with headings "
        "and bullet points when helpful. Stay factual and avoid speculation."
    ),
    version="v1",
)
