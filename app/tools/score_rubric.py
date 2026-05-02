"""Deterministic rubric scoring tool for the evaluation component."""

from __future__ import annotations

import re

from langchain.tools import tool
from pydantic import ValidationError

from app.tools.load_rubric import validate_rubric_payload
from app.tools.validate_extraction import CandidateExtraction


def _clamp_score(score: float) -> float:
    """Clamp a criterion score to the supported range."""
    return round(max(0.0, min(score, 100.0)), 2)


def _extract_duration_years(duration: str | None) -> float:
    """Convert a duration string to an approximate number of years."""
    if not duration:
        return 0.0

    total_years = 0.0
    for amount, unit in re.findall(
        r"(\d+(?:\.\d+)?)\s*(years?|yrs?|months?|mos?)", duration.lower()
    ):
        value = float(amount)
        if unit.startswith("month") or unit.startswith("mo"):
            total_years += value / 12.0
        else:
            total_years += value
    return total_years


def _candidate_completeness(candidate: CandidateExtraction) -> float:
    """Estimate how complete the extracted candidate profile is."""
    checks = [
        candidate.name is not None,
        candidate.email is not None,
        candidate.phone is not None,
        candidate.website is not None,
        bool(candidate.skills),
        bool(candidate.experience),
        bool(candidate.education),
        bool(candidate.other_details),
    ]
    return sum(checks) / len(checks)


def _score_skills(candidate: CandidateExtraction) -> tuple[float, list[str], str]:
    """Score the candidate's technical skills evidence."""
    unique_skills = sorted({skill.strip() for skill in candidate.skills if skill.strip()})
    score = 25.0 if not unique_skills else min(95.0, 40.0 + len(unique_skills) * 10.0)
    evidence = (
        [f"Listed skills: {', '.join(unique_skills[:6])}"]
        if unique_skills
        else ["No explicit technical skills were extracted."]
    )
    reasoning = (
        f"Detected {len(unique_skills)} distinct skills, which suggests the candidate has "
        "relevant technical breadth."
        if unique_skills
        else "The application does not provide enough explicit technical skill evidence."
    )
    return _clamp_score(score), evidence, reasoning


def _score_experience(candidate: CandidateExtraction) -> tuple[float, list[str], str]:
    """Score the candidate's work experience evidence."""
    experience_entries = candidate.experience
    total_years = sum(_extract_duration_years(entry.duration) for entry in experience_entries)
    role_count = len(experience_entries)
    score = 20.0
    if role_count:
        score += min(role_count, 4) * 8.0
        score += min(total_years, 8.0) * 6.0
        if any(entry.company for entry in experience_entries):
            score += 7.0
        if any(entry.title for entry in experience_entries):
            score += 7.0
    evidence = (
        [
            f"Experience entries: {role_count}",
            f"Estimated total duration: {round(total_years, 1)} years",
        ]
        if role_count
        else ["No structured work experience was extracted."]
    )
    reasoning = (
        "The candidate provides structured role history with measurable duration evidence."
        if role_count
        else "The application does not include enough structured work experience evidence."
    )
    return _clamp_score(score), evidence, reasoning


def _degree_rank(degree: str | None) -> int:
    """Map degree keywords to a rough academic level."""
    if not degree:
        return 0
    normalized = degree.lower()
    if "phd" in normalized or "doctor" in normalized:
        return 4
    if "master" in normalized or "msc" in normalized or "mba" in normalized:
        return 3
    if "bachelor" in normalized or "bsc" in normalized or "ba" in normalized:
        return 2
    if "diploma" in normalized or "associate" in normalized or "certificate" in normalized:
        return 1
    return 1


def _score_education(candidate: CandidateExtraction) -> tuple[float, list[str], str]:
    """Score the candidate's education evidence."""
    education_entries = candidate.education
    highest_rank = max((_degree_rank(entry.degree) for entry in education_entries), default=0)
    score = 20.0
    if education_entries:
        score += 18.0
        score += highest_rank * 12.0
        score += min(len(education_entries), 3) * 6.0
        if any(entry.year for entry in education_entries):
            score += 4.0
    evidence = (
        [
            f"Education entries: {len(education_entries)}",
            f"Highest detected degree rank: {highest_rank}",
        ]
        if education_entries
        else ["No education history was extracted."]
    )
    reasoning = (
        "The candidate includes identifiable academic background with useful detail."
        if education_entries
        else "The application provides limited or no structured education evidence."
    )
    return _clamp_score(score), evidence, reasoning


def _score_communication(candidate: CandidateExtraction) -> tuple[float, list[str], str]:
    """Score clarity and completeness of the candidate profile."""
    completeness = _candidate_completeness(candidate)
    contact_points = sum(
        value is not None for value in (candidate.email, candidate.phone, candidate.website)
    )
    score = 35.0 + completeness * 45.0 + contact_points * 5.0
    evidence = [
        f"Profile completeness: {round(completeness * 100, 1)}%",
        f"Contact points provided: {contact_points}",
    ]
    if candidate.other_details:
        evidence.append(f"Additional details captured: {len(candidate.other_details)}")
    reasoning = (
        "The application is reasonably complete and includes clear supporting details."
        if completeness >= 0.5
        else "The application is missing multiple useful profile details."
    )
    return _clamp_score(score), evidence, reasoning


def _score_generic(candidate: CandidateExtraction) -> tuple[float, list[str], str]:
    """Score a non-standard rubric criterion using overall profile completeness."""
    completeness = _candidate_completeness(candidate)
    score = 30.0 + completeness * 55.0
    evidence = [f"Profile completeness: {round(completeness * 100, 1)}%"]
    reasoning = (
        "The score is based on the overall completeness and consistency of the extracted profile."
    )
    return _clamp_score(score), evidence, reasoning


def _score_criterion(
    candidate: CandidateExtraction, criterion_name: str, description: str
) -> tuple[float, list[str], str]:
    """Choose a deterministic scoring strategy for a rubric criterion."""
    signature = f"{criterion_name} {description}".lower()
    if any(keyword in signature for keyword in ("skill", "technical", "technology")):
        return _score_skills(candidate)
    if any(keyword in signature for keyword in ("experience", "employment", "work history")):
        return _score_experience(candidate)
    if any(keyword in signature for keyword in ("education", "degree", "academic")):
        return _score_education(candidate)
    if any(
        keyword in signature
        for keyword in ("communication", "clarity", "writing", "presentation", "interpersonal")
    ):
        return _score_communication(candidate)
    return _score_generic(candidate)


@tool
def score_against_rubric_tool(
    extracted_json: dict[str, object], rubric: dict[str, object]
) -> dict[str, object]:
    """Score extracted candidate data against a weighted rubric.

    Args:
        extracted_json: Structured applicant data from the extraction agent.
        rubric: Rubric payload containing weighted criteria and decision thresholds.

    Returns:
        A dictionary containing the weighted total score and per-criterion breakdown.

    Raises:
        ValueError: If the extracted data or rubric payload is invalid.

    Example:
        score_against_rubric_tool.invoke(
            {"extracted_json": {"skills": ["Python"]}, "rubric": {"criteria": [...]}},
        )
    """
    try:
        candidate = CandidateExtraction.model_validate(extracted_json)
    except ValidationError as exc:
        raise ValueError(f"Invalid extracted_json payload: {exc}") from exc

    rubric_definition = validate_rubric_payload(rubric)
    weight_sum = sum(criterion.weight for criterion in rubric_definition.criteria)

    criterion_breakdown: list[dict[str, object]] = []
    total_score = 0.0
    for criterion in rubric_definition.criteria:
        normalized_weight = criterion.weight / weight_sum
        score, evidence, reasoning = _score_criterion(
            candidate, criterion.name, criterion.description
        )
        weighted_score = round(score * normalized_weight, 2)
        total_score += weighted_score
        criterion_breakdown.append(
            {
                "name": criterion.name,
                "description": criterion.description,
                "weight": round(normalized_weight, 4),
                "score": score,
                "weighted_score": weighted_score,
                "evidence": evidence,
                "reasoning": reasoning,
            }
        )

    return {
        "total_score": round(total_score, 2),
        "criterion_breakdown": criterion_breakdown,
        "pass_threshold": rubric_definition.pass_threshold,
        "review_threshold": rubric_definition.review_threshold,
    }
