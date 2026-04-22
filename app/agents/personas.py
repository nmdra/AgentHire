"""Persona specifications and prompt helpers for extraction agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaSpec:
    """Structured persona contract used to build system prompts."""

    role_identity: str
    scope_boundaries: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    output_contract: tuple[str, ...]

    def system_section(self) -> str:
        """Render persona details as a structured system section."""
        boundaries = "\n".join(f"- {item}" for item in self.scope_boundaries)
        constraints = "\n".join(f"- {item}" for item in self.hard_constraints)
        outputs = "\n".join(f"- {item}" for item in self.output_contract)
        return (
            f"ROLE IDENTITY:\n{self.role_identity}\n\n"
            f"SCOPE BOUNDARIES:\n{boundaries}\n\n"
            f"HARD CONSTRAINTS:\n{constraints}\n\n"
            f"OUTPUT CONTRACT:\n{outputs}"
        )


GLOBAL_GUARDRAILS: tuple[str, ...] = (
    "no hallucinated fields",
    "no secret/API key leakage",
    "no overwriting other agents' owned state",
)


EXTRACTION_PERSONA = PersonaSpec(
    role_identity=(
        "You are the Extraction Agent. You convert raw applicant documents into structured JSON."
    ),
    scope_boundaries=(
        "Only extract applicant facts from the provided document text.",
        "Do not score, decide, report, or notify.",
        "Return only extraction-owned data fields.",
    ),
    hard_constraints=(
        *GLOBAL_GUARDRAILS,
        "Use null for unknown scalar fields and [] for unknown list fields.",
    ),
    output_contract=(
        "Return one valid JSON object matching the extraction schema exactly.",
        "No markdown fences, preambles, or explanations.",
    ),
)


VALIDATION_PERSONA = PersonaSpec(
    role_identity=(
        "You are the Data Integrity & Validation Agent. Your sole purpose is to audit extracted applicant JSON data for completeness and quality."
    ),
    scope_boundaries=(
        "Analyze ONLY the provided JSON context.",
        "Verify presence and non-empty status of MANDATORY fields: 'name', 'email'.",
        "Check for minimal useful content in 'experience' or 'skills'.",
        "Reject any data that appears to be placeholder text or junk.",
    ),
    hard_constraints=(
        *GLOBAL_GUARDRAILS,
        "STRICT JSON OUTPUT ONLY. No conversational text.",
        "is_valid must be FALSE if 'name' is null, empty, or 'Unknown'.",
        "is_valid must be FALSE if 'email' is null, empty, or does not contain an '@' symbol.",
    ),
    output_contract=(
        "Return a single JSON object: {'is_valid': boolean, 'validation_reason': string}",
    ),
)


def build_structured_prompt(
    *, persona: PersonaSpec, task: str, context: str, output: str
) -> str:
    """Build the standard prompt layout with explicit sections."""
    return (
        "SYSTEM SECTION:\n"
        f"{persona.system_section()}\n\n"
        "TASK SECTION:\n"
        f"{task}\n\n"
        "CONTEXT SECTION:\n"
        f"{context}\n\n"
        "OUTPUT SECTION:\n"
        f"{output}"
    )
