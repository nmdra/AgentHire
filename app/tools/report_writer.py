"""Markdown report writing tool."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool


@tool
def write_reports_tool(
    reports_dir: str, application_id: str, report_applicant: str, report_internal: str
) -> dict[str, str]:
    """Write applicant and internal reports to markdown files.

    Args:
        reports_dir: Directory where report files should be written.
        application_id: Unique application identifier used for file naming.
        report_applicant: Applicant-facing markdown report.
        report_internal: Internal markdown report.

    Returns:
        Mapping with generated report paths.

    Raises:
        ValueError: If application_id is empty.

    Example:
        write_reports_tool.invoke(
            {
                "reports_dir": "reports",
                "application_id": "app-1",
                "report_applicant": "# Applicant",
                "report_internal": "# Internal",
            }
        )
    """
    if not application_id:
        raise ValueError("application_id is required to write reports")

    output_dir = Path(reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    applicant_path = output_dir / f"{application_id}_applicant.md"
    internal_path = output_dir / f"{application_id}_internal.md"
    applicant_path.write_text(report_applicant, encoding="utf-8")
    internal_path.write_text(report_internal, encoding="utf-8")
    return {
        "applicant_path": str(applicant_path),
        "internal_path": str(internal_path),
    }
