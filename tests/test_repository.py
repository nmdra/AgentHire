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
