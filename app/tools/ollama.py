"""Minimal Ollama API client utilities."""

from __future__ import annotations

import json

import httpx


class OllamaError(RuntimeError):
    """Raised when an Ollama request fails."""


def generate_json_response(*, base_url: str, model: str, prompt: str, temperature: float = 0.0) -> str:
    """Generate a completion from Ollama and return response text."""
    endpoint = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }

    try:
        response = httpx.post(endpoint, json=payload, timeout=60.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc

    data = response.json()
    text = data.get("response")
    if not isinstance(text, str):
        raise OllamaError(f"Invalid Ollama response: {json.dumps(data)}")
    return text
