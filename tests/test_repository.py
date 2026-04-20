from app.agents.notification_agent import notification_agent_node
from app.db.database import init_db
from app.db.repository import ApplicationRepository


def test_repository_roundtrip(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    repo = ApplicationRepository(db_path)

    repo.create_application("id-1", "/tmp/file.txt")
    repo.update_fields("id-1", decision="PASS", confidence=0.9, errors=["warn"])
    app = repo.get_application("id-1")

    assert app is not None
    assert app["decision"] == "PASS"
    assert app["confidence"] == 0.9
    assert app["errors"] == ["warn"]

    repo.add_audit_log("id-1", "agent", "tool", "in", "out", 12)
    logs = repo.list_audit_logs("id-1")
    assert len(logs) == 1
    assert logs[0]["agent_name"] == "agent"


def test_notification_missing_recipient_is_failed(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    repo = ApplicationRepository(db_path)
    repo.create_application("id-2", str(tmp_path / "file.txt"))
    state = {
        "application_id": "id-2",
        "raw_file_path": str(tmp_path / "file.txt"),
        "extracted_json": {"name": "No Email"},
        "decision": "PASS",
        "errors": [],
        "audit_log": [],
    }
    result = notification_agent_node(
        state,
        repo,
        {"resend_api_key": "re_test", "resend_from_email": "noreply@example.com"},
    )
    assert result["notification_status"] == "failed"
    assert result["errors"] == ["Missing recipient email"]
    stored = repo.get_application("id-2")
    assert stored is not None
    assert stored["notification_status"] == "failed"
    assert stored["errors"] == ["Missing recipient email"]
    logs = repo.list_audit_logs("id-2")
    assert logs[-1]["tool_name"] == "validate_recipient"
