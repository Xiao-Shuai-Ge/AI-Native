"""Parses CrewAI Task raw text output into shared Pydantic schemas.

CrewAI Agents without tools return their final answer as plain text (see
`llm_bridge.py`); Tasks are instructed via their `description` to answer with
strict JSON matching a schema, mirroring the same "prompt + parse" technique
already used by `llm.openai_compatible.OpenAICompatibleClient.chat_structured`
so both engines get structurally comparable outputs.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from llm.errors import LLMParseError

_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def parse_structured_output[T: BaseModel](raw_text: str, schema: type[T]) -> T:
    """Parses `raw_text` (expected to contain a JSON object) into `schema`."""
    stripped = raw_text.strip()
    try:
        return schema.model_validate_json(stripped)
    except (ValidationError, ValueError):
        pass

    match = _JSON_OBJECT_PATTERN.search(stripped)
    if match is None:
        msg = f"no JSON object found in CrewAI task output for schema {schema.__name__}"
        raise LLMParseError(msg)

    try:
        data = json.loads(match.group())
        return schema.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        msg = f"CrewAI task output failed schema validation for {schema.__name__}: {exc}"
        raise LLMParseError(msg) from exc
