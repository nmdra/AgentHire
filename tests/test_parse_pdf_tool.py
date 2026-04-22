from app.tools.parse_pdf import parse_pdf_tool
try:
    res = parse_pdf_tool.invoke({"path": "uploads/functionalsample.pdf"})
    print("TOOL SUCCESS")
    print("Length:", len(res))
except Exception as e:
    print("TOOL FAILED:", type(e), e)
