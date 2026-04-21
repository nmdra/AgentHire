"""Extraction payload validation tool."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateExtraction(BaseModel):
    """Structured extraction output from extraction agent."""

    name: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    skills: list[str] = Field(default_factory=list)
    experience: str | None = Field(default=None)
    education: str | None = Field(default=None)
