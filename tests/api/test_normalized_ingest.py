from fastapi.testclient import TestClient

from services.api.app.main import app


def test_normalized_upload_rejects_schema_mismatch():
    client = TestClient(app)
    response = client.post("/api/v1/ingest/normalized", json={"bad": "payload"})
    assert response.status_code == 422
