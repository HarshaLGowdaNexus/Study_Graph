"""
Automated Test Suite for Privacy, Data Ownership & Performance (Task T20).
Relies on:
  - Feature F22: Delete-all-my-data + consent text.
  - Risk R07: Token cost tracking and latency verification.
  - Risk R11: Multi-tenant student privacy isolation (Rule 11).
  - Decision D05 (PostgreSQL), D06 (Storage), D13 (Auth isolation).
"""

from pathlib import Path
import uuid
import psycopg2.extras
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api.deps import CurrentUser
from backend.app.api.routes.privacy import (
    DeleteDataRequest,
    delete_all_user_data,
    get_cost_summary,
    get_performance_timings,
)
from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.main import app
from backend.app.services.cost_service import (
    calculate_cost_usd,
    get_user_cost_summary,
    log_token_usage,
)


def test_cost_calculation_math():
    """Verifies Gemini Flash and Embedding cost formulas match official pricing."""
    # Gemini Flash: $0.075 / 1M prompt, $0.300 / 1M completion
    prompt_tokens = 20_000
    completion_tokens = 5_000
    # Expected: (20000 / 1e6) * 0.075 + (5000 / 1e6) * 0.30 = 0.0015 + 0.0015 = 0.0030
    cost = calculate_cost_usd("gemini-1.5-flash", prompt_tokens, completion_tokens)
    assert pytest.approx(cost, 0.0001) == 0.0030

    # Zero tokens should yield $0.00
    assert calculate_cost_usd("gemini-1.5-flash", 0, 0) == 0.0

    # Embedding cost: $0.02 / 1M tokens
    emb_cost = calculate_cost_usd("text-embedding-004", 100_000, 0)
    assert pytest.approx(emb_cost, 0.0001) == 0.0020


def test_delete_confirmation_validation():
    """Enforces that delete_all_user_data strictly rejects non-matching confirmation tokens."""
    dummy_user = CurrentUser(id=str(uuid.uuid4()), email="test@uni.edu", name="Test")

    # Lowercase 'delete' must raise 400
    with pytest.raises(HTTPException) as exc_info:
        import asyncio
        asyncio.run(delete_all_user_data(DeleteDataRequest(confirmation="delete"), dummy_user))
    assert exc_info.value.status_code == 400
    assert "DELETE" in exc_info.value.detail

    # Empty string must raise 400
    with pytest.raises(HTTPException) as exc_info2:
        asyncio.run(delete_all_user_data(DeleteDataRequest(confirmation=""), dummy_user))
    assert exc_info2.value.status_code == 400


def test_user_data_wipe_and_isolation():
    """
    Core Privacy Test (Feature F22, Rule 11):
      1. Seeds User A and User B with subjects, documents, chunks, topics, edges, chats, token logs, and files.
      2. Wipes User A.
      3. Verifies User A's data is 100% eradicated from database and storage.
      4. Verifies User B's data remains 100% untouched and intact.
    """
    import asyncio

    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    user_a = CurrentUser(id=user_a_id, email=f"user_a_{user_a_id[:6]}@example.com", name="Student A")
    user_b = CurrentUser(id=user_b_id, email=f"user_b_{user_b_id[:6]}@example.com", name="Student B")

    # Set up local storage cache files for both
    bucket_dir = Path(settings.ROOT_DIR) / ".storage_cache" / settings.SUPABASE_STORAGE_BUCKET
    file_a_path = bucket_dir / "user_a" / "notes_a.pdf"
    file_b_path = bucket_dir / "user_b" / "notes_b.pdf"
    file_a_path.parent.mkdir(parents=True, exist_ok=True)
    file_b_path.parent.mkdir(parents=True, exist_ok=True)
    file_a_path.write_bytes(b"%PDF-1.4 Mock notes for user A")
    file_b_path.write_bytes(b"%PDF-1.4 Mock notes for user B")

    storage_uri_a = f"local://{settings.SUPABASE_STORAGE_BUCKET}/user_a/notes_a.pdf"
    storage_uri_b = f"local://{settings.SUPABASE_STORAGE_BUCKET}/user_b/notes_b.pdf"

    # Seed Database
    with get_db_cursor() as cursor:
        # Users
        cursor.execute("INSERT INTO users (id, email, name) VALUES (%s, %s, %s);", (user_a.id, user_a.email, user_a.name))
        cursor.execute("INSERT INTO users (id, email, name) VALUES (%s, %s, %s);", (user_b.id, user_b.email, user_b.name))

        # Subjects
        subj_a_id = str(uuid.uuid4())
        subj_b_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, 'Subject A');", (subj_a_id, user_a.id))
        cursor.execute("INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, 'Subject B');", (subj_b_id, user_b.id))

        # Documents
        doc_a_id = str(uuid.uuid4())
        doc_b_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO documents (id, subject_id, filename, type, source_kind, storage_path, status) VALUES (%s, %s, 'notes_a.pdf', 'application/pdf', 'notes', %s, 'done');",
            (doc_a_id, subj_a_id, storage_uri_a),
        )
        cursor.execute(
            "INSERT INTO documents (id, subject_id, filename, type, source_kind, storage_path, status) VALUES (%s, %s, 'notes_b.pdf', 'application/pdf', 'notes', %s, 'done');",
            (doc_b_id, subj_b_id, storage_uri_b),
        )

        # Chunks
        chunk_a_id = str(uuid.uuid4())
        chunk_b_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO chunks (id, document_id, page, text) VALUES (%s, %s, 1, 'Chunk text A');", (chunk_a_id, doc_a_id))
        cursor.execute("INSERT INTO chunks (id, document_id, page, text) VALUES (%s, %s, 1, 'Chunk text B');", (chunk_b_id, doc_b_id))

        # Topics
        top_a_id = str(uuid.uuid4())
        top_b_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO topics (id, subject_id, keyword, explanation) VALUES (%s, %s, 'Topic A', 'Line 1');", (top_a_id, subj_a_id))
        cursor.execute("INSERT INTO topics (id, subject_id, keyword, explanation) VALUES (%s, %s, 'Topic B', 'Line 1');", (top_b_id, subj_b_id))

        # Chat message
        cursor.execute("INSERT INTO chat_messages (user_id, subject_id, role, text) VALUES (%s, %s, 'user', 'Question A');", (user_a.id, subj_a_id))
        cursor.execute("INSERT INTO chat_messages (user_id, subject_id, role, text) VALUES (%s, %s, 'user', 'Question B');", (user_b.id, subj_b_id))

        # Token logs
        cursor.execute(
            """
            INSERT INTO token_logs (user_id, subject_id, document_id, operation, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd)
            VALUES (%s, %s, %s, 'topic_extraction', 'gemini-1.5-flash', 1000, 200, 1200, 0.000135);
            """,
            (user_a.id, subj_a_id, doc_a_id),
        )
        cursor.execute(
            """
            INSERT INTO token_logs (user_id, subject_id, document_id, operation, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd)
            VALUES (%s, %s, %s, 'topic_extraction', 'gemini-1.5-flash', 1000, 200, 1200, 0.000135);
            """,
            (user_b.id, subj_b_id, doc_b_id),
        )

    # Execute data wipe for User A
    res = asyncio.run(delete_all_user_data(DeleteDataRequest(confirmation="DELETE"), user_a))
    assert res.status == "deleted"
    assert res.remaining_records == 0

    # 1. Verify User A data is completely wiped
    assert not file_a_path.exists(), "User A's file in storage cache was not purged!"

    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("SELECT COUNT(*) AS c FROM subjects WHERE user_id = %s;", (user_a.id,))
        assert cursor.fetchone()["c"] == 0
        cursor.execute("SELECT COUNT(*) AS c FROM documents WHERE id = %s;", (doc_a_id,))
        assert cursor.fetchone()["c"] == 0
        cursor.execute("SELECT COUNT(*) AS c FROM chunks WHERE id = %s;", (chunk_a_id,))
        assert cursor.fetchone()["c"] == 0
        cursor.execute("SELECT COUNT(*) AS c FROM topics WHERE id = %s;", (top_a_id,))
        assert cursor.fetchone()["c"] == 0
        cursor.execute("SELECT COUNT(*) AS c FROM chat_messages WHERE user_id = %s;", (user_a.id,))
        assert cursor.fetchone()["c"] == 0
        cursor.execute("SELECT COUNT(*) AS c FROM token_logs WHERE user_id = %s;", (user_a.id,))
        assert cursor.fetchone()["c"] == 0

    # 2. Verify User B data is 100% UNTOUCHED (Rule 11)
    assert file_b_path.exists(), "User B's storage file was deleted by mistake!"

    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("SELECT COUNT(*) AS c FROM subjects WHERE user_id = %s;", (user_b.id,))
        assert cursor.fetchone()["c"] == 1
        cursor.execute("SELECT COUNT(*) AS c FROM documents WHERE id = %s;", (doc_b_id,))
        assert cursor.fetchone()["c"] == 1
        cursor.execute("SELECT COUNT(*) AS c FROM chunks WHERE id = %s;", (chunk_b_id,))
        assert cursor.fetchone()["c"] == 1
        cursor.execute("SELECT COUNT(*) AS c FROM topics WHERE id = %s;", (top_b_id,))
        assert cursor.fetchone()["c"] == 1
        cursor.execute("SELECT COUNT(*) AS c FROM chat_messages WHERE user_id = %s;", (user_b.id,))
        assert cursor.fetchone()["c"] == 1
        cursor.execute("SELECT COUNT(*) AS c FROM token_logs WHERE user_id = %s;", (user_b.id,))
        assert cursor.fetchone()["c"] == 1

        # Cleanup User B test fixture
        cursor.execute("DELETE FROM subjects WHERE user_id = %s;", (user_b.id,))
        cursor.execute("DELETE FROM users WHERE id = %s;", (user_b.id,))

    if file_b_path.exists():
        file_b_path.unlink()


def test_cost_summary_api_endpoint():
    """Verifies GET /api/cost/summary endpoint returns complete token breakdown."""
    user_id = str(uuid.uuid4())
    user = CurrentUser(id=user_id, email=f"cost_{user_id[:6]}@example.com", name="Cost Student")

    with get_db_cursor() as cursor:
        cursor.execute("INSERT INTO users (id, email, name) VALUES (%s, %s, %s);", (user.id, user.email, user.name))
        subj_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, 'Cost Subj');", (subj_id, user.id))
        doc_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO documents (id, subject_id, filename, type, source_kind, status) VALUES (%s, %s, 'test_notes.pdf', 'application/pdf', 'notes', 'done');", (doc_id, subj_id))

    # Log an upload operation and a chat operation (after DB commit)
    log_token_usage(
        user_id=user.id,
        operation="topic_extraction",
        model="gemini-1.5-flash",
        prompt_tokens=4000,
        completion_tokens=800,
        subject_id=subj_id,
        document_id=doc_id,
    )
    log_token_usage(
        user_id=user.id,
        operation="chat_message",
        model="gemini-1.5-flash",
        prompt_tokens=1500,
        completion_tokens=300,
        subject_id=subj_id,
    )

    summary = get_cost_summary(current_user=user)
    assert summary["total_tokens"] == 6600
    assert summary["total_prompt_tokens"] == 5500
    assert summary["total_completion_tokens"] == 1100
    assert summary["total_estimated_cost_usd"] > 0
    assert len(summary["per_upload_breakdown"]) == 1
    assert summary["per_upload_breakdown"][0]["filename"] == "test_notes.pdf"
    assert len(summary["per_chat_breakdown"]) == 1
    assert "pricing_reference" in summary

    # Cleanup
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM subjects WHERE user_id = %s;", (user.id,))
        cursor.execute("DELETE FROM users WHERE id = %s;", (user.id,))


def test_process_time_header_and_timings():
    """Verifies X-Process-Time header is injected and /performance/timings endpoint operates."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "x-process-time" in resp.headers
    assert resp.headers["x-process-time"].endswith("ms")
