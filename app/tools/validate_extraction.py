"""Extraction payload validation tool."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _empty_to_none(v: Any) -> Any:
    """Convert empty strings to None so they serialize to JSON null."""
    if v == "":
        return None
    return v


class ExperienceEntry(BaseModel):
    """Structured experience entry extracted from a candidate profile."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None)
    company: str | None = Field(default=None)
    duration: str | None = Field(default=None)

    @field_validator("*", mode="before")
    @classmethod
    def validate_empty(cls, v: Any) -> Any:
        return _empty_to_none(v)


class EducationEntry(BaseModel):
    """Structured education entry extracted from a candidate profile."""

    model_config = ConfigDict(extra="ignore")

    degree: str | None = Field(default=None)
    institution: str | None = Field(default=None)
    year: str | None = Field(default=None)

    @field_validator("*", mode="before")
    @classmethod
    def validate_empty(cls, v: Any) -> Any:
        return _empty_to_none(v)


class CandidateExtraction(BaseModel):
    """Structured extraction output from extraction agent."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    website: str | None = Field(default=None)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    other_details: list[str] = Field(default_factory=list)

    @field_validator("name", "email", "phone", "website", mode="before")
    @classmethod
    def validate_empty(cls, v: Any) -> Any:
        return _empty_to_none(v)
