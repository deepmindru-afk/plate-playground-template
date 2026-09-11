"""Pydantic request/response models."""

from typing import Any

from pydantic import BaseModel, Field


class DocCreate(BaseModel):
    title: str = Field(default="Untitled")
    content: Any = Field(default_factory=list)


class DocUpdate(BaseModel):
    title: str | None = None
    content: Any = None


class DocMeta(BaseModel):
    id: str
    title: str
    createdAt: str
    updatedAt: str


class Doc(DocMeta):
    content: Any


class ChooseToolBody(BaseModel):
    instructions: str | None = None
    messages: list[Any] = Field(default_factory=list)


class CopilotBody(BaseModel):
    apiKey: str | None = None
    model: str | None = None
    instructions: str | None = None
    prompt: str = ""
    system: str | None = None