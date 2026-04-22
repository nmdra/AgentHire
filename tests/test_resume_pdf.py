from app.tools.parse_pdf import parse_pdf_tool
from app.agents.extraction_agent import _extract_with_retry
from app.config import get_settings

path = "uploads/resume.pdf"
raw_text = parse_pdf_tool.invoke({"path": path})

print("==== PYMUPDF OUTPUT (First 1000 chars) ====")
print(repr(raw_text[:1000]))
print("=" * 50)

settings = get_settings()
try:
    res = _extract_with_retry(
        raw_text,
        model=settings.extraction_model,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    print("EXTRACTION RESULT:")
    import json
    print(json.dumps(res, indent=2))
except Exception as e:
    print("ERROR:", e)
