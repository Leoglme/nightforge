"""
Project machine path Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict, Field


class ProjectPathSet(BaseModel):
    """Schema for setting a project's local clone path on a machine."""

    machine_id: int = Field(...)
    local_path: str = Field(..., min_length=1, max_length=600)


class ProjectPathResponse(BaseModel):
    """Schema for a project machine path."""

    id: int
    project_id: int
    machine_id: int
    local_path: str

    model_config = ConfigDict(from_attributes=True)
