import io

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _client(tmp_path, max_upload_size_bytes: int = 10 * 1024 * 1024):
    settings = Settings(
        db_path=str(tmp_path / "app.db"),
        uploads_dir=str(tmp_path / "uploads"),
        reports_dir=str(tmp_path / "reports"),
        max_upload_size_bytes=max_upload_size_bytes,
    )
    app = create_app(settings)
    return TestClient(app)


def test_upload_and_status(tmp_path):
    client = _client(tmp_path)
    file_content = b"Name: Jane Doe\nEmail: jane@example.com\nSkills: Python, FastAPI\n"
    response = client.post(
        "/applications/upload",
        files={"file": ("application.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    status = client.get(f"/applications/{body['application_id']}/status")
    assert status.status_code == 200
    assert status.json()["id"] == body["application_id"]
    assert "raw_file_path" not in status.json()
    assert "extracted_json" not in status.json()
    assert "report_applicant" not in status.json()
    assert "report_internal" not in status.json()


def test_process_endpoint(tmp_path):
    client = _client(tmp_path)
    file_content = b"Name: Jane Doe\nEmail: jane@example.com\nSkills: Python, FastAPI\n"
    response = client.post(
        "/applications/process",
        files={"file": ("application.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"


def test_process_rejects_oversized_rubric(tmp_path):
    client = _client(tmp_path, max_upload_size_bytes=128)
    file_content = b"Name: Jane Doe\nEmail: jane@example.com\nSkills: Python, FastAPI\n"
    response = client.post(
        "/applications/process",
        files={
            "file": ("application.txt", io.BytesIO(file_content), "text/plain"),
            "rubric": ("rubric.json", io.BytesIO(b'{"a":"' + (b"x" * 200) + b'"}'), "application/json"),
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Rubric file too large"
