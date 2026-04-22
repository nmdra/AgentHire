from app.agents.extraction_agent import _extract_with_retry
from app.config import get_settings
from app.tools.parse_pdf import parse_pdf_tool

settings = get_settings()
raw_text = parse_pdf_tool.invoke({"path": "uploads/functionalsample.pdf"})

try:
    res = _extract_with_retry(
        raw_text,
        model=settings.extraction_model,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    print("EXTRACTION RESULT:", res)
except Exception as e:
    print("ERROR:", e)
