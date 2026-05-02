from app.tools.parse_pdf import parse_pdf_tool
from app.agents.extraction_agent import _extract_with_retry
from app.config import get_settings

raw_text = parse_pdf_tool.invoke({"path": "uploads/functionalsample.pdf"})
print("RAW TEXT:")
print(repr(raw_text))

settings = get_settings()
try:
    res = _extract_with_retry(
        raw_text,
        model="agenthire-extractor",
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    print("EXTRACTION RESULT:", res)
except Exception as e:
    print("ERROR:", e)

# Let's clean the markdown formatting and test again
import re
cleaned_text = re.sub(r'[*#]', '', raw_text)
print("CLEANED TEXT:")
print(repr(cleaned_text[:200]))

try:
    res = _extract_with_retry(
        cleaned_text,
        model="agenthire-extractor",
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    print("CLEANED EXTRACTION RESULT:", res)
except Exception as e:
    print("ERROR:", e)

