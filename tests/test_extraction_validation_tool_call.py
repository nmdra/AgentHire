"""Integration test to verify Functional Orchestration with attachments in extraction_validation_agent."""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch
from app.agents.extraction_validation_agent import extraction_validation_agent
from app.state import ApplicationState

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_123")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "delivered@resend.dev")
    monkeypatch.setenv("REVIEWER_EMAIL", "nimendradilshan11@gmail.com")
    monkeypatch.setenv("VALIDATION_MODEL", "phi4-mini:3.8b-q4_K_M")

@patch("app.agents.extraction_validation_agent.update_application")
@patch("app.agents.extraction_validation_agent.generate_json_response")
@patch("resend.Emails.send")
@patch("os.path.exists")
def test_validation_with_attachment(mock_exists, mock_resend_send, mock_gen_json, mock_update_app, mock_env):
    """Test that tool is called with attachment_path when validation fails."""
    # Mock Resend
    mock_resend_send.return_value = {"id": "test-email-id"}
    mock_exists.return_value = True
    
    # Mock Model Response
    mock_gen_json.return_value = json.dumps({
        "is_valid": False,
        "reason": "Missing Name field",
        "email_subject": "Audit Alert: Missing Data",
        "email_body": "<p>The name is missing.</p>"
    })
    
    state: ApplicationState = {
        "application_id": "test-app-id",
        "file_path": "uploads/cv.pdf",
        "background_tasks": None,
        "extracted_json": {"name": None, "email": "test@example.com"},
        "errors": []
    }
    
    # Mock open and read bytes INSIDE the tool
    mock_file = MagicMock()
    mock_file.read.return_value = b"test content"
    # Important: Context manager support
    mock_file.__enter__.return_value = mock_file
    
    with patch("app.tools.email_tool.open", MagicMock(return_value=mock_file), create=True):
        result = extraction_validation_agent(state)
    
    # Verify results
    assert result["is_valid"] is False
    
    # Verify deterministic tool call
    assert mock_resend_send.called
    args, kwargs = mock_resend_send.call_args
    params = args[0]
    
    assert params["subject"] == "Audit Alert: Missing Data"
    assert "attachments" in params
    assert params["attachments"][0]["filename"] == "cv.pdf"
    # Verify it is a base64 string
    assert isinstance(params["attachments"][0]["content"], str)
    assert "Application ID: test-app-id" in params["html"]
    print("SUCCESS: Attachment (base64) and Metadata verified in tool call params.")

if __name__ == "__main__":
    pytest.main([__file__, "-s"])


@patch("app.agents.extraction_validation_agent.update_application")
@patch("app.agents.extraction_validation_agent.generate_json_response")
def test_validation_short_circuits_when_name_and_email_are_valid(
    mock_gen_json, mock_update_app
):
    """Valid extracted identity data should not be rejected by model output."""
    state: ApplicationState = {
        "application_id": "test-app-id",
        "file_path": "uploads/cv.txt",
        "background_tasks": None,
        "extracted_json": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+94 77 123 4567",
            "website": "https://janedoe.dev",
            "skills": ["Python"],
            "experience": [],
            "education": [],
            "other_details": [],
        },
        "errors": [],
    }

    result = extraction_validation_agent(state)

    assert result["status"] == "validated"
    assert result["is_valid"] is True
    assert result["errors"] == []
    assert mock_gen_json.called is False
