from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class ExtractedApplication(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)


class RubricCriterion(BaseModel):
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str


class Rubric(BaseModel):
    criteria: list[RubricCriterion]
    pass_threshold: float = Field(default=65.0, ge=0.0, le=100.0)
    review_threshold: float = Field(default=60.0, ge=0.0, le=100.0)

    @field_validator("criteria")
    @classmethod
    def validate_weights(cls, value: list[RubricCriterion]) -> list[RubricCriterion]:
        total = sum(c.weight for c in value)
        if not value:
            raise ValueError("Rubric must include at least one criterion")
        if not 0.99 <= total <= 1.01:
            raise ValueError("Rubric criteria weights must sum to 1.0")
        return value


class ScoreBreakdown(BaseModel):
    total_score: float = Field(ge=0.0, le=100.0)
    breakdown: dict[str, float]
    reasoning: str


class DecisionResult(BaseModel):
    status: Literal["PASS", "FAIL", "REVIEW"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class EmailResult(BaseModel):
    email_id: str
    status: Literal["sent", "queued", "failed"]
    timestamp: datetime


class ProcessResponse(BaseModel):
    application_id: str
    status: str


class HealthResponse(BaseModel):
    api: str
    db: str
    ollama: str


class ApplicationStatusResponse(BaseModel):
    id: str
    raw_file_path: str
    extracted_json: dict[str, Any] | None
    evaluation_score: float | None
    evaluation_reasoning: str | None
    decision: str | None
    confidence: float | None
    report_applicant: str | None
    report_internal: str | None
    notification_status: str | None
    errors: list[str]
    created_at: str


class AuditLogResponse(BaseModel):
    id: int
    application_id: str
    agent_name: str
    tool_name: str | None
    input_summary: str
    output_summary: str
    latency_ms: int
    created_at: str
