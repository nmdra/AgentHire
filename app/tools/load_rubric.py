"""Rubric loading and validation tools for the evaluation component."""

from __future__ import annotations

import json
from pathlib import Path

from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class RubricCriterion(BaseModel):
    """Single weighted evaluation criterion."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    weight: float = Field(gt=0.0, le=1.0)
    description: str = Field(min_length=1)


class RubricDefinition(BaseModel):
    """Validated rubric definition used by the evaluation agent."""

    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterion] = Field(min_length=1)
    pass_threshold: float = Field(default=75.0, ge=0.0, le=100.0)
    review_threshold: float = Field(default=60.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_thresholds_and_weights(self) -> "RubricDefinition":
        """Ensure rubric thresholds and weights are internally consistent."""
        weight_sum = sum(criterion.weight for criterion in self.criteria)
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(
                f"Rubric criteria weights must sum to 1.0 +/- 0.01. Got {weight_sum:.4f}."
            )
        if self.pass_threshold < self.review_threshold:
            raise ValueError("pass_threshold must be greater than or equal to review_threshold")
        return self


def validate_rubric_payload(payload: dict[str, object]) -> RubricDefinition:
    """Validate a rubric payload and return the normalized model.

    Args:
        payload: Parsed rubric dictionary to validate.

    Returns:
        A validated rubric definition model.

    Raises:
        ValueError: If the rubric payload does not satisfy the required schema.

    Example:
        validate_rubric_payload({"criteria": [], "pass_threshold": 75, "review_threshold": 60})
    """
    try:
        return RubricDefinition.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid rubric payload: {exc}") from exc


@tool
def load_rubric_tool(path: str) -> dict[str, object]:
    """Load and validate a rubric definition from disk.

    Args:
        path: Path to the rubric JSON file.

    Returns:
        The validated rubric as a plain dictionary.

    Raises:
        FileNotFoundError: If the rubric file does not exist.
        ValueError: If the file is not valid JSON or does not match the rubric schema.

    Example:
        load_rubric_tool.invoke({"path": "data/default_rubric.json"})
    """
    rubric_path = Path(path)
    if not rubric_path.exists():
        raise FileNotFoundError(f"Rubric file does not exist: {path}")

    try:
        payload = json.loads(rubric_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Rubric file is not valid JSON") from exc

    rubric = validate_rubric_payload(payload)
    return rubric.model_dump()
