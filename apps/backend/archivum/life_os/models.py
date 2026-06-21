from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectInput(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = ""
    status: str = "active"


class TaskInput(BaseModel):
    title: str = Field(min_length=1)
    project_key: str | None = None
    page_slug: str | None = None
    due_date: str | None = None
    source: str = "manual"


class DecisionInput(BaseModel):
    title: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    rationale: str = ""
    project_key: str | None = None
    page_slug: str | None = None
