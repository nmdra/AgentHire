"""Decision agent implementation."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from app.agents.personas import DECISION_PERSONA, build_structured_prompt
from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState, Decision
from app.tools.ollama import generate_json_response

PASS_THRESHOLD = 75.0
REVIEW_THRESHOLD = 60.0


class DecisionOutput(BaseModel):
    """Structured output expected from the decision reason model."""

    decision_reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


def _classify_score(score: float) -> Decision:
    """Apply deterministic threshold logic for pass/review/fail."""
    if score >= PASS_THRESHOLD:
        return "PASS"
    if score >= REVIEW_THRESHOLD:
        return "REVIEW"
    return "FAIL"


def _build_decision_prompt(state: ApplicationState, decision: Decision) -> str:
    task = (
        "Given the deterministic decision and evaluation context, provide concise human-readable reason and confidence."
    )
    context = json.dumps(
        {
            "evaluation_score": state.get("evaluation_score"),
            "evaluation_reasoning": state.get("evaluation_reasoning"),
            "decision": decision,
            "pass_threshold": PASS_THRESHOLD,
            "review_threshold": REVIEW_THRESHOLD,
        },
        ensure_ascii=False,
    )
    output = (
        "Return strict JSON only:\n"
        '{\n'
        '  "decision_reason": string,\n'
        '  "confidence": number (0.0 to 1.0)\n'
        '}'
    )
    return build_structured_prompt(
        persona=DECISION_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _run_decision_prompt(prompt: str, fallback_decision: Decision, score: float) -> DecisionOutput:
    settings = get_settings()
    response_text = generate_json_response(
        base_url=settings.ollama_base_url,
        model=settings.decision_model,
        prompt=prompt,
        temperature=0.0,
        top_p=0.1,
        stop=["```"],
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    try:
        payload = json.loads(response_text)
        return DecisionOutput.model_validate(payload)
    except (json.JSONDecodeError, ValidationError):
        return DecisionOutput(
            decision_reason=(
                f"Decision {fallback_decision} from score {score:.2f} using threshold rules."
            ),
            confidence=0.75,
        )


@traced("decision_agent")
def decision_agent(state: ApplicationState) -> dict[str, object]:
    """Classify applicant decision deterministically and generate reason metadata."""
    raw_score = state.get("evaluation_score")
    if raw_score is None:
        raise ValueError("evaluation_score is required for decision")

    score = float(raw_score)
    decision = _classify_score(score)
    prompt = _build_decision_prompt(state, decision)
    details = _run_decision_prompt(prompt, decision, score)

    return {
        "status": "decided",
        "decision": decision,
        "confidence": float(details.confidence),
        "decision_reason": details.decision_reason,
    }
