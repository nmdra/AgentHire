"""Observability utilities for agent execution tracing."""

from __future__ import annotations

import functools
import re
import time
from collections.abc import Callable
from typing import Any

from app.state import ApplicationState
from app.logger import setup_logger

logger = setup_logger("observability")


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _mask_pii(value: str) -> str:
    """Mask email local parts in logs."""
    return EMAIL_PATTERN.sub("****@\\2", value)


def traced(agent_name: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorate an agent node and append execution telemetry to state audit log."""

    def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(state: ApplicationState) -> dict[str, Any]:
            application_id = state.get("application_id", "unknown")
            logger.info(f"Agent '{agent_name}' started for application '{application_id}'")
            start = time.perf_counter()
            try:
                result = func(state)
                ok = True
                output_summary = _mask_pii(str(result)[:300])
                error_msg: str | None = None
                logger.info(f"Agent '{agent_name}' completed successfully for application '{application_id}'")
            except Exception as exc:  # pragma: no cover - defensive catch
                ok = False
                result = state.copy()
                output_summary = ""
                error_msg = str(exc)
                logger.exception(f"Agent '{agent_name}' failed for application '{application_id}': {exc}")

            latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
            extracted = state.get("extracted_json") if isinstance(state.get("extracted_json"), dict) else {}
            entry = {
                "agent_name": agent_name,
                "tool_name": func.__name__,
                "input_summary": _mask_pii(
                    str(
                        {
                            "application_id": state.get("application_id"),
                            "decision": state.get("decision"),
                            "recipient_email": extracted.get("email") if isinstance(extracted, dict) else None,
                        }
                    )[:300]
                ),
                "output_summary": output_summary,
                "latency_ms": latency_ms,
                "ok": ok,
            }

            response: dict[str, Any] = dict(result)
            response["audit_log"] = [entry]
            if error_msg is not None:
                response.setdefault("errors", [])
                response["errors"] = list(response["errors"]) + [f"{agent_name} failed: {error_msg}"]
                response["status"] = "failed"
            return response

        return wrapper

    return decorator
