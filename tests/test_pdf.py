import pymupdf4llm
from pathlib import Path

path = "uploads/functionalsample.pdf"
if Path(path).exists():
    try:
        text = pymupdf4llm.to_markdown(path)
        print("EXTRACTION SUCCESS")
        print("Length:", len(text))
        print("Preview:", repr(text[:200]))
    except Exception as e:
        print("EXTRACTION FAILED:", str(e))
else:
    print("File not found:", path)
