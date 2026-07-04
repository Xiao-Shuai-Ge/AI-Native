"""User preference API schemas."""

from pydantic import BaseModel, Field


class UserPreferencesResponse(BaseModel):
    user_id: str
    preferences: dict[str, object] = Field(default_factory=dict)


class UpdateUserPreferencesRequest(BaseModel):
    preferences: dict[str, object] = Field(default_factory=dict)
