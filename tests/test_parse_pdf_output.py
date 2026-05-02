from app.tools.parse_pdf import parse_pdf_tool
res = parse_pdf_tool.invoke({"path": "uploads/functionalsample.pdf"})
print(repr(res[:500]))
