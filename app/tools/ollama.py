"""Minimal Ollama API client utilities."""

from __future__ import annotations

import json

import httpx


class OllamaError(RuntimeError):
    """Raised when an Ollama request fails."""


def generate_json_response(
    *,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float = 0.0,
    timeout_seconds: float = 30.0,
) -> str:
    """Generate a JSON completion response from an Ollama model.

    Args:
        base_url: Ollama server base URL.
        model: Model name to query.
        prompt: Prompt text sent to the model.
        temperature: Sampling temperature for generation.
        timeout_seconds: HTTP timeout in seconds.

    Returns:
        The raw model response text.

    Raises:
        OllamaError: If the HTTP request fails or response payload is invalid.

    Example:
        generate_json_response(
            base_url="http://localhost:11434",
            model="smollm:360m",
            prompt="Return JSON",
            timeout_seconds=30.0,
        )
    """
    endpoint = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }

    try:
        response = httpx.post(endpoint, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc

    data = response.json()
    text = data.get("response")
    if not isinstance(text, str):
        raise OllamaError(f"Invalid Ollama response: {json.dumps(data)}")
    return text
