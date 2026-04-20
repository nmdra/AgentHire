import io

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _client(tmp_path):
    settings = Settings(
        db_path=str(tmp_path / "app.db"),
        uploads_dir=str(tmp_path / "uploads"),
        reports_dir=str(tmp_path / "reports"),
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
