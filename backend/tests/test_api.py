"""Tests for the API routes in app.py.

These cover behavior that does not change as the pipeline is filled in. The
stubbed routes are deliberately not asserted on here, because their responses
change the moment analysis is implemented.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
from app import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A test client that returns error responses instead of raising."""
    return TestClient(app, raise_server_exceptions=False)


def upload(client: TestClient, path: Path) -> object:
    """Post one document to the analyze route."""
    return client.post("/api/analyze", files={"file": (path.name, path.read_bytes())})


def test_health_reports_configured_model(client: TestClient) -> None:
    """Health returns the configured model name and runtime availability."""
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["configured_model"] == config.MODEL_NAME
    assert isinstance(body["ollama_available"], bool)


def test_unsupported_file_type_rejected(client: TestClient, tmp_path: Path) -> None:
    """An extension the pipeline does not handle is refused before extraction."""
    path = tmp_path / "notes.rtf"
    path.write_bytes(b"some text")
    response = upload(client, path)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_oversized_upload_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upload past the size limit is refused."""
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 16)
    path = tmp_path / "big.txt"
    path.write_bytes(b"x" * 1024)
    response = upload(client, path)
    assert response.status_code == 413


@pytest.mark.parametrize(
    "name, expected",
    [
        ("scanned_pdf", "scan"),
        ("locked_pdf", "password"),
        ("fake_docx", "Word document"),
        ("empty_text", "empty"),
    ],
)
def test_extraction_failures_return_422(
    client: TestClient, documents: dict[str, Path], name: str, expected: str
) -> None:
    """A document that cannot be read gets a readable 422, not a 500."""
    response = upload(client, documents[name])
    assert response.status_code == 422
    assert expected in response.json()["detail"]


def test_question_for_unknown_document(client: TestClient) -> None:
    """Asking about a document the server does not hold returns 404."""
    response = client.post(
        "/api/question", json={"document_id": "missing", "question": "How much?"}
    )
    assert response.status_code == 404


def test_api_routes_are_not_swallowed_by_the_frontend(client: TestClient) -> None:
    """An unknown API path returns 404 rather than the frontend index page."""
    assert client.get("/api/does-not-exist").status_code == 404
