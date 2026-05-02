import re
from app.tools.parse_pdf import parse_pdf_tool
from app.agents.extraction_agent import _extract_with_retry
from app.config import get_settings

path = "uploads/resume.pdf"
raw_text = parse_pdf_tool.invoke({"path": path})

cleaned_text = re.sub(r'[*#_📱🖂]', '', raw_text)

print("==== CLEANED PYMUPDF OUTPUT (First 500 chars) ====")
print(repr(cleaned_text[:500]))

settings = get_settings()
try:
    res = _extract_with_retry(
        cleaned_text,
        model=settings.extraction_model,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    import json
    print("EXTRACTION RESULT:")
    print(json.dumps(res, indent=2))
except Exception as e:
    print("ERROR:", e)
