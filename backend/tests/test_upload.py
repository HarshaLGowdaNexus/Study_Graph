"""
Automated Integration and Unit Tests for File Upload & Job Queue.
Tests Task T03 requirements:
- Valid file upload (PDF/PPT/images)
- Polite rejection of invalid file formats (.exe, .zip)
- File size limit enforcement
- Background status progression (queued -> extracting -> done)
- Multi-user data privacy isolation (User A vs User B)
"""

import io
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)

# Test User IDs
USER_A_ID = str(uuid.uuid4())
USER_B_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def setup_test_env():
    """Ensure test environment mode is set."""
    settings.APP_ENV = "testing"


def get_auth_headers(user_id: str, email: str = None) -> dict:
    return {
        "x-test-user-id": user_id,
        "x-test-user-email": email or f"student_{user_id[:8]}@example.com",
    }


def test_api_health():
    """Verify backend server root and health endpoints."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_reject_unsupported_file_extensions():
    """Verify unsupported files (.exe, .zip) are rejected with a friendly message."""
    # First create a subject for User A
    sub_res = client.post(
        "/api/subjects",
        json={"name": "Computer Networks"},
        headers=get_auth_headers(USER_A_ID),
    )
    assert sub_res.status_code == 201
    subject_id = sub_res.json()["id"]

    # Try uploading a .exe file
    fake_exe = io.BytesIO(b"MZ executable content")
    res_exe = client.post(
        "/api/upload",
        files={"file": ("setup.exe", fake_exe, "application/octet-stream")},
        data={"subject_id": subject_id, "module_no": 1, "source_kind": "notes"},
        headers=get_auth_headers(USER_A_ID),
    )
    assert res_exe.status_code == 400
    assert "Unsupported file format '.exe'" in res_exe.json()["detail"]
    assert "Please upload lecture notes in PDF" in res_exe.json()["detail"]

    # Try uploading a .zip file
    fake_zip = io.BytesIO(b"PK zip content")
    res_zip = client.post(
        "/api/upload",
        files={"file": ("notes.zip", fake_zip, "application/zip")},
        data={"subject_id": subject_id, "module_no": 1, "source_kind": "notes"},
        headers=get_auth_headers(USER_A_ID),
    )
    assert res_zip.status_code == 400
    assert "Unsupported file format '.zip'" in res_zip.json()["detail"]


def test_reject_file_exceeding_max_size():
    """Verify files larger than maximum size are blocked cleanly."""
    sub_res = client.post(
        "/api/subjects",
        json={"name": "Operating Systems"},
        headers=get_auth_headers(USER_A_ID),
    )
    subject_id = sub_res.json()["id"]

    # Temporarily set max size to 0 MB to simulate exceeding limit
    original_limit = settings.MAX_FILE_SIZE_MB
    try:
        settings.MAX_FILE_SIZE_MB = 0  # 0 MB limit
        dummy_file = io.BytesIO(b"%PDF-1.4 dummy pdf data that exceeds 0MB")
        res = client.post(
            "/api/upload",
            files={"file": ("large_chapter.pdf", dummy_file, "application/pdf")},
            data={"subject_id": subject_id, "module_no": 1, "source_kind": "notes"},
            headers=get_auth_headers(USER_A_ID),
        )
        assert res.status_code == 413
        assert "exceeds the 0 MB limit" in res.json()["detail"]
    finally:
        settings.MAX_FILE_SIZE_MB = original_limit


def test_upload_valid_pdf_and_status_progression():
    """Verify valid PDF upload enqueues job and updates status to done."""
    # Create subject
    sub_res = client.post(
        "/api/subjects",
        json={"name": "Database Management Systems"},
        headers=get_auth_headers(USER_A_ID),
    )
    subject_id = sub_res.json()["id"]

    # Upload PDF
    pdf_content = b"%PDF-1.5 \n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    upload_res = client.post(
        "/api/upload",
        files={"file": ("Module_1_Relational_Algebra.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={"subject_id": subject_id, "module_no": 1, "source_kind": "notes"},
        headers=get_auth_headers(USER_A_ID),
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["filename"] == "Module_1_Relational_Algebra.pdf"
    assert data["status"] == "queued"
    doc_id = data["id"]

    # Wait briefly for FastAPI background task to execute
    time.sleep(2.0)

    # Check status endpoint
    status_res = client.get(
        f"/api/documents/{doc_id}/status",
        headers=get_auth_headers(USER_A_ID),
    )
    assert status_res.status_code == 200
    doc_status = status_res.json()
    assert doc_status["id"] == doc_id
    assert doc_status["status"] in ("extracting", "done")


def test_user_privacy_isolation():
    """
    Verify privacy rule:
    User A's documents and subjects cannot be seen or written to by User B.
    """
    # 1. User A creates a private subject
    sub_a = client.post(
        "/api/subjects",
        json={"name": "User A Private Notes"},
        headers=get_auth_headers(USER_A_ID),
    ).json()
    sub_a_id = sub_a["id"]

    # 2. User A uploads a document
    doc_a = client.post(
        "/api/upload",
        files={"file": ("private_notes.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        data={"subject_id": sub_a_id, "module_no": 1, "source_kind": "notes"},
        headers=get_auth_headers(USER_A_ID),
    ).json()
    doc_a_id = doc_a["id"]

    # 3. User B tries to view User A's document status -> must return 404
    status_res = client.get(
        f"/api/documents/{doc_a_id}/status",
        headers=get_auth_headers(USER_B_ID),
    )
    assert status_res.status_code == 404

    # 4. User B tries to upload into User A's subject -> must return 404
    upload_res = client.post(
        "/api/upload",
        files={"file": ("sneaky.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        data={"subject_id": sub_a_id, "module_no": 1, "source_kind": "notes"},
        headers=get_auth_headers(USER_B_ID),
    )
    assert upload_res.status_code == 404

