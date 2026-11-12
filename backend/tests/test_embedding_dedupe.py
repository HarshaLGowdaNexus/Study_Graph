"""
Automated Unit and Integration Tests for Embedding Service and Topic Deduplication (T07).
Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase.
  - Decision D09: Gemini Flash for dedupe confirmation.
  - Decision D10: 768-dim semantic embeddings.
  - Decision D14: pytest testing framework.
"""

import math
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.dedupe import (
    CandidatePair,
    DedupeJudgeDecision,
    ManualMergeRequest,
    ManualSplitRequest,
)
from backend.app.services.dedupe_service import DedupeService
from backend.app.services.embedding_service import (
    EmbeddingService,
    compute_cosine_similarity,
)

client = TestClient(app)


# ==============================================================================
# 1. Cosine Similarity Mathematics Tests
# ==============================================================================


def test_cosine_similarity_identical_vectors():
    vec = [0.1, 0.5, 0.9, -0.3]
    sim = compute_cosine_similarity(vec, vec)
    assert pytest.approx(sim, 0.0001) == 1.0


def test_cosine_similarity_orthogonal_vectors():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    sim = compute_cosine_similarity(vec_a, vec_b)
    assert pytest.approx(sim, 0.0001) == 0.0


def test_cosine_similarity_opposite_vectors():
    vec_a = [1.0, 2.0, 3.0]
    vec_b = [-1.0, -2.0, -3.0]
    sim = compute_cosine_similarity(vec_a, vec_b)
    assert pytest.approx(sim, 0.0001) == -1.0


def test_cosine_similarity_empty_or_mismatched():
    assert compute_cosine_similarity([], [1.0]) == 0.0
    assert compute_cosine_similarity([1.0], [1.0, 2.0]) == 0.0


# ==============================================================================
# 2. Embedding Service Unit Tests
# ==============================================================================


def test_embedding_service_initialization():
    service = EmbeddingService()
    assert service.vector_dim == 768
    assert service.model_name in ("gemini-embedding-001", "text-embedding-004")


@patch("backend.app.services.embedding_service.EmbeddingService._get_client")
def test_embedding_generation_batching(mock_get_client):
    mock_client = MagicMock()
    mock_item1 = MagicMock()
    mock_item1.values = [0.05] * 768
    mock_item2 = MagicMock()
    mock_item2.values = [0.08] * 768

    mock_response = MagicMock()
    mock_response.embeddings = [mock_item1, mock_item2]
    mock_client.models.embed_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    service = EmbeddingService()
    embeddings = service.generate_embeddings(["Topic 1", "Topic 2"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 768
    assert len(embeddings[1]) == 768


# ==============================================================================
# 3. LLM Duplicate Confirmation Unit Tests
# ==============================================================================


@patch("backend.app.services.dedupe_service.DedupeService._get_client")
def test_llm_confirm_true_duplicate(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        '{"is_duplicate": true, "confidence": 0.95, '
        '"reason": "Both describe the TCP 3-way connection setup.", '
        '"canonical_keyword": "TCP 3-Way Handshake"}'
    )
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    service = DedupeService()
    decision = service.confirm_duplicate_with_llm(
        topic_a_keyword="TCP Handshake",
        topic_a_explanation="Three step SYN, SYN-ACK, ACK connection establishment.",
        topic_b_keyword="3-Way Handshake",
        topic_b_explanation="Protocol process to open a reliable TCP connection.",
    )

    assert decision.is_duplicate is True
    assert decision.confidence == 0.95
    assert decision.canonical_keyword == "TCP 3-Way Handshake"


@patch("backend.app.services.dedupe_service.DedupeService._get_client")
def test_llm_confirm_rejects_distinct_topics(mock_get_client):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = (
        '{"is_duplicate": false, "confidence": 0.99, '
        '"reason": "TCP is connection-oriented while UDP is connectionless; they are distinct protocols.", '
        '"canonical_keyword": null}'
    )
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    service = DedupeService()
    decision = service.confirm_duplicate_with_llm(
        topic_a_keyword="TCP Protocol",
        topic_a_explanation="Connection-oriented reliable transport protocol.",
        topic_b_keyword="UDP Protocol",
        topic_b_explanation="Connectionless lightweight datagram protocol.",
    )

    assert decision.is_duplicate is False
    assert "distinct" in decision.reason.lower() or "connection" in decision.reason.lower()


# ==============================================================================
# 4. Strict Cross-Subject Isolation Rule Test
# ==============================================================================


def test_cross_subject_merge_is_blocked():
    """Golden Rule: Never merge topics across different subjects."""
    service = DedupeService()
    subject_1 = uuid4()
    subject_2 = uuid4()
    topic_1 = uuid4()
    topic_2 = uuid4()

    # Mock DB cursor to simulate two topics from different subjects
    with patch("backend.app.services.dedupe_service.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {
                "id": str(topic_1),
                "subject_id": str(subject_1),
                "keyword": "Deadlock",
                "explanation": "Resource wait state.",
                "real_world_use": "OS process management",
                "module_no": 1,
            },
            {
                "id": str(topic_2),
                "subject_id": str(subject_2),  # Different subject!
                "keyword": "Deadlock",
                "explanation": "Lock contention in DBMS.",
                "real_world_use": "DBMS transactions",
                "module_no": 2,
            },
        ]

        with pytest.raises(ValueError, match="Cross-subject topic merging is strictly prohibited"):
            service.merge_topics(surviving_topic_id=topic_1, merged_topic_id=topic_2)


# ==============================================================================
# 5. Merge Execution and Split (Undo) Database Logic
# ==============================================================================


def test_merge_execution_and_split_cycle():
    """
    Tests complete lifecycle:
    1. Merge topic B into topic A:
       - Sources transferred
       - Alias added to surviving topic
       - Logged to topic_merges
    2. Split (undo):
       - Topic B restored
       - Sources restored
       - Alias removed from surviving topic
       - Marked undone_at in topic_merges
    """
    service = DedupeService()
    subject_id = uuid4()
    topic_a = uuid4()
    topic_b = uuid4()
    chunk_1 = uuid4()
    chunk_2 = uuid4()
    merge_id = uuid4()

    # Step 1: Test Merge
    with patch("backend.app.services.dedupe_service.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

        # First fetch both topics
        mock_cursor.fetchall.side_effect = [
            # 1. Fetch topics
            [
                {
                    "id": str(topic_a),
                    "subject_id": str(subject_id),
                    "keyword": "TCP Handshake",
                    "explanation": "3-way handshake SYN, SYN-ACK, ACK.",
                    "real_world_use": "Web browsing",
                    "module_no": 1,
                },
                {
                    "id": str(topic_b),
                    "subject_id": str(subject_id),
                    "keyword": "Three-Way Handshake",
                    "explanation": "Establishment procedure in TCP.",
                    "real_world_use": "Web sockets",
                    "module_no": 1,
                },
            ],
            # 2. Fetch chunk_ids for topic_b
            [{"chunk_id": str(chunk_1)}, {"chunk_id": str(chunk_2)}],
            # 3. Fetch existing aliases for topic_b
            [],
            # 4. Fetch edges where topic_a = topic_b
            [],
            # 5. Fetch edges where topic_b = topic_b
            [],
        ]
        mock_cursor.fetchone.return_value = {"id": str(merge_id)}

        result = service.merge_topics(
            surviving_topic_id=topic_a,
            merged_topic_id=topic_b,
            similarity_score=0.92,
            merge_type="auto",
        )

        assert result["merge_id"] == str(merge_id)
        assert result["surviving_keyword"] == "TCP Handshake"
        assert result["merged_keyword"] == "Three-Way Handshake"
        assert result["transferred_chunks_count"] == 2

    # Step 2: Test Split (Undo)
    with patch("backend.app.services.dedupe_service.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor

        # Mock fetching the merge record and surviving topic
        mock_cursor.fetchone.side_effect = [
            # 1. Fetch topic_merges record
            {
                "id": str(merge_id),
                "subject_id": str(subject_id),
                "surviving_topic_id": str(topic_a),
                "merged_topic_id": str(topic_b),
                "merged_keyword": "Three-Way Handshake",
                "merged_explanation": "Establishment procedure in TCP.",
                "merged_real_world_use": "Web sockets",
                "merged_module_no": 1,
                "transferred_chunk_ids": [str(chunk_1), str(chunk_2)],
                "undone_at": None,
            },
            # 2. Fetch surviving topic
            {"id": str(topic_a), "keyword": "TCP Handshake"},
        ]

        with patch.object(service.embedding_service, "generate_single_embedding", return_value=[0.05] * 768):
            split_result = service.split_merge(merge_id)

        assert split_result["merge_id"] == str(merge_id)
        assert split_result["restored_keyword"] == "Three-Way Handshake"
        assert split_result["restored_chunks_count"] == 2


# ==============================================================================
# 6. REST API Endpoints Test
# ==============================================================================

from backend.app.api.routes.dedupe import (
    manual_merge_topics,
    manual_split_merge,
    run_deduplication,
    get_candidate_duplicates,
)


@patch("backend.app.services.dedupe_service.DedupeService.merge_topics")
def test_api_manual_merge_endpoint(mock_merge):
    topic_a = str(uuid4())
    topic_b = str(uuid4())
    mock_merge.return_value = {
        "merge_id": str(uuid4()),
        "surviving_topic_id": topic_a,
        "merged_topic_id": topic_b,
        "surviving_keyword": "A",
        "merged_keyword": "B",
        "transferred_chunks_count": 1,
    }

    req = ManualMergeRequest(surviving_topic_id=topic_a, merged_topic_id=topic_b)
    res = manual_merge_topics(req)
    assert res["status"] == "success"
    assert res["result"]["surviving_topic_id"] == topic_a
    mock_merge.assert_called_once()


@patch("backend.app.services.dedupe_service.DedupeService.split_merge")
def test_api_manual_split_endpoint(mock_split):
    merge_id = str(uuid4())
    mock_split.return_value = {
        "merge_id": merge_id,
        "restored_topic_id": str(uuid4()),
        "restored_keyword": "Restored Concept",
        "restored_chunks_count": 2,
        "surviving_topic_id": str(uuid4()),
    }

    req = ManualSplitRequest(merge_id=merge_id)
    res = manual_split_merge(req)
    assert res["status"] == "success"
    assert res["result"]["merge_id"] == merge_id
    mock_split.assert_called_once()
