"""Extraction payload validation tool."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExperienceEntry(BaseModel):
    """Structured experience entry extracted from a candidate profile."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None)
    company: str | None = Field(default=None)
    duration: str | None = Field(default=None)


class EducationEntry(BaseModel):
    """Structured education entry extracted from a candidate profile."""

    model_config = ConfigDict(extra="forbid")

    degree: str | None = Field(default=None)
    institution: str | None = Field(default=None)
    year: str | None = Field(default=None)


class CandidateExtraction(BaseModel):
    """Structured extraction output from extraction agent."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    website: str | None = Field(default=None)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    other_details: list[str] = Field(default_factory=list)
