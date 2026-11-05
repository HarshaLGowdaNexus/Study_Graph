"""
Automated Unit and Integration Tests for Topic Review Screen (Task T06).
Relies on:
  - Feature F03: Review extracted topics screen (skippable).
  - Risk R06: Catches OCR/transcription errors before graph creation.
  - Risk R03: Prevents nonsense topics from polluting knowledge graphs.
  - RULEBOOK Rule 11: Multi-user privacy & isolation.
  - RULEBOOK Section 13 Rule 3: Topic explanation at most 4 lines.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.schemas.topic import (
    TopicReviewItem,
    TopicUpdateRequest,
)

client = TestClient(app)

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
DOC_ID = "33333333-3333-3333-3333-333333333333"
TOPIC_ID = "44444444-4444-4444-4444-444444444444"
SUBJECT_ID = "55555555-5555-5555-5555-555555555555"


@pytest.fixture(autouse=True)
def override_auth():
    """Default authentication override to student A."""
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER_A,
        email="alex@university.edu",
        name="Alex Chen",
    )
    yield
    app.dependency_overrides.clear()


def test_schema_topic_update_4_lines_validation():
    """Verify that updating an explanation with > 4 lines raises ValidationError."""
    # Valid 4 lines
    valid = TopicUpdateRequest(
        explanation="Line 1: Virtual memory overview.\nLine 2: Pages map to frames.\nLine 3: MMU translates addresses.\nLine 4: Page fault triggers OS handler."
    )
    assert valid.explanation is not None

    # Invalid 5 lines
    with pytest.raises(Exception) as exc_info:
        TopicUpdateRequest(
            explanation="Line 1\nLine 2\nLine 3\nLine 4\nLine 5: Disallowed extra line"
        )
    assert "exceeds 4 lines" in str(exc_info.value)


def test_get_document_topics_success():
    """Verify GET /api/documents/{doc_id}/topics returns structured list of topics."""
    mock_cursor = MagicMock()
    # Step 1: doc check returns (id, filename, subject_id, subject_name)
    mock_cursor.fetchone.return_value = (DOC_ID, "Lecture1_OS.pdf", SUBJECT_ID, "Operating Systems")
    # Step 2: topics list
    mock_cursor.fetchall.return_value = [
        (
            TOPIC_ID,
            SUBJECT_ID,
            "Virtual Memory",
            "Paging and virtual address spaces.",
            "Linux process isolation",
            1,
            False,
            [1, 2],
            2,
        )
    ]

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.get(f"/api/documents/{DOC_ID}/topics")
        assert res.status_code == 200
        data = res.json()
        assert data["document_id"] == DOC_ID
        assert data["filename"] == "Lecture1_OS.pdf"
        assert data["total_count"] == 1
        assert data["unreviewed_count"] == 1
        assert data["reviewed_count"] == 0
        topic = data["topics"][0]
        assert topic["keyword"] == "Virtual Memory"
        assert topic["reviewed"] is False
        assert topic["source_pages"] == [1, 2]
        assert topic["chunk_count"] == 2


def test_get_document_topics_not_found_or_denied():
    """Verify GET /api/documents/{doc_id}/topics returns 404 when document is not owned."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # No document found for this user

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.get(f"/api/documents/{DOC_ID}/topics")
        assert res.status_code == 404
        assert "not found or access denied" in res.json()["detail"].lower()


def test_patch_topic_success():
    """Verify PATCH /api/topics/{topic_id} updates keyword, explanation, and reviewed state."""
    mock_cursor = MagicMock()
    # Topic exists check
    mock_cursor.fetchone.side_effect = [
        (TOPIC_ID, SUBJECT_ID, "Old Keyword", "Old Explanation", "Old Use", 1, False),
        (TOPIC_ID, SUBJECT_ID, "Demand Paging", "Loads pages only on demand.", "Swapping memory", 1, True),
        ([1, 3], 2),  # Citation pages and count
    ]

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.patch(
            f"/api/topics/{TOPIC_ID}",
            json={
                "keyword": "Demand Paging",
                "explanation": "Loads pages only on demand.",
                "reviewed": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["keyword"] == "Demand Paging"
        assert data["reviewed"] is True
        assert data["source_pages"] == [1, 3]


def test_patch_topic_rejects_exceeding_4_lines():
    """Verify PATCH /api/topics/{topic_id} returns 422 if explanation exceeds 4 lines."""
    res = client.patch(
        f"/api/topics/{TOPIC_ID}",
        json={
            "explanation": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5: Disallowed extra line",
        },
    )
    assert res.status_code == 422
    assert "exceeds 4 lines" in str(res.json())


def test_delete_topic_success():
    """Verify DELETE /api/topics/{topic_id} removes topic and returns success."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (TOPIC_ID,)

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.delete(f"/api/topics/{TOPIC_ID}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True
        assert res.json()["id"] == TOPIC_ID


def test_approve_all_topics():
    """Verify POST /api/documents/{doc_id}/topics/approve-all sets all topics to reviewed."""
    mock_cursor = MagicMock()
    # Doc check
    mock_cursor.fetchone.return_value = (DOC_ID,)
    mock_cursor.rowcount = 4

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.post(f"/api/documents/{DOC_ID}/topics/approve-all")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "approved"
        assert data["updated_count"] == 4
        assert "All 4 topics marked as reviewed" in data["message"]


def test_skip_topic_review():
    """Verify POST /api/documents/{doc_id}/topics/skip preserves unreviewed state."""
    mock_cursor = MagicMock()
    # Doc check
    mock_cursor.fetchone.side_effect = [
        (DOC_ID,),  # Doc ownership check
        (5,),       # Topic count
    ]

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.post(f"/api/documents/{DOC_ID}/topics/skip")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "skipped"
        assert data["updated_count"] == 5
        assert "remain marked as unreviewed" in data["message"]


def test_user_isolation_blocks_cross_user_access():
    """Rule 11: Verify student B cannot access student A's document topics."""
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER_B,
        email="jordan@university.edu",
        name="Jordan Taylor",
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # DB query filters by user_id, so returns None

    @contextmanager
    def mock_get_db():
        yield mock_cursor

    with patch("backend.app.api.routes.topics.get_db_cursor", mock_get_db):
        res = client.get(f"/api/documents/{DOC_ID}/topics")
        assert res.status_code == 404
        assert "not found or access denied" in res.json()["detail"].lower()
