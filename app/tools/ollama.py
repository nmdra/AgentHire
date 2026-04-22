"""Ollama LangChain integration utilities."""

from __future__ import annotations

from langchain_ollama import OllamaLLM


class OllamaError(RuntimeError):
    """Raised when an Ollama request fails."""


def extract_first_json(text: str) -> str:
    """Extract the first complete JSON object from a string.

    Scans the text for the first ``{...}`` block by tracking brace depth.
    This handles model output that includes trailing text or commentary
    after the closing brace.

    Args:
        text: Raw text that may contain a JSON object alongside other content.

    Returns:
        The first complete JSON object substring, or the original text if no
        balanced brace pair is found.

    Example:
        >>> extract_first_json('{"name": "Alice"} extra text')
        '{"name": "Alice"}'
    """
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : i + 1]
    return text


def generate_json_response(
    *,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float = 0.0,
    top_k: int = 10,
    top_p: float = 0.9,
    repeat_penalty: float = 1.1,
    seed: int = 42,
    num_ctx: int = 2048,
    num_predict: int = 600,
    stop: list[str] | None = None,
    timeout_seconds: float = 30.0,
) -> str:
    """Generate a JSON completion response from a local Ollama model via LangChain.

    Uses ``OllamaLLM`` from ``langchain-ollama`` so the call participates in
    LangChain tracing and is compatible with LCEL pipelines.

    Args:
        base_url: Ollama server base URL (e.g. ``http://localhost:11434``).
        model: Ollama model name to query.
        prompt: Prompt text sent to the model.
        temperature: Sampling temperature for generation.
        top_k: Top-k sampling parameter.
        top_p: Nucleus sampling parameter.
        repeat_penalty: Penalty for repeated tokens.
        seed: Random seed for generation.
        num_ctx: Context window size.
        num_predict: Maximum number of tokens to predict.
        stop: Optional list of stop tokens.
        timeout_seconds: Request timeout in seconds.

    Returns:
        The raw model response text.

    Raises:
        OllamaError: If the LangChain/Ollama call raises an exception.

    Example:
        >>> generate_json_response(
        ...     base_url="http://localhost:11434",
        ...     model="agenthire-extractor",
        ...     prompt="Alice Perera\\nEmail: alice@example.com",
        ...     timeout_seconds=30.0,
        ... )
        '{"name": "Alice Perera", ...}'
    """
    if stop is None:
        stop = ["<|end-output|>", "<|endoftext|>"]

    llm = OllamaLLM(
        model=model,
        base_url=base_url,
        temperature=temperature,
        top_k=top_k,
        top_p=top_p,
        repeat_penalty=repeat_penalty,
        seed=seed,
        num_ctx=num_ctx,
        num_predict=num_predict,
        stop=stop,
        format="json",
        client_kwargs={"timeout": timeout_seconds},
    )
    try:
        return str(llm.invoke(prompt))
    except Exception as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc
