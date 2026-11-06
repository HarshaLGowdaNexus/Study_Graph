"""
Automated Unit and Integration Tests for Link Candidate Finder (Task T08).
Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase.
  - Decision D10: 768-dim embeddings.
  - Decision D14: pytest testing framework.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.api.routes.candidates import (
    find_candidates,
    get_candidates_for_topic,
    get_pending_candidates,
)
from backend.app.schemas.candidate import (
    CandidateBatchResponse,
    CandidateFindResult,
    CandidatePair,
    CandidateSearchParams,
)
from backend.app.services.candidate_finder import CandidateFinderService


# ==============================================================================
# 1. Unit Tests: Capping and Sorting Logic
# ==============================================================================


def test_candidate_capping_enforcement():
    """Verify that candidate lists are strictly capped at max_per_topic."""
    service = CandidateFinderService(max_per_topic=5)

    focal_id = str(uuid4())
    # Generate 10 mock candidates with varying similarities
    mock_same = [
        CandidatePair(
            topic_a_id=focal_id,
            topic_a_keyword="Focal",
            topic_a_explanation="Exp",
            topic_a_subject_id=str(uuid4()),
            topic_b_id=str(uuid4()),
            topic_b_keyword=f"Same {i}",
            topic_b_explanation="Exp",
            topic_b_subject_id=str(uuid4()),
            similarity=0.70 + (i * 0.02),
            scope="same_subject",
        )
        for i in range(6)
    ]
    mock_cross = [
        CandidatePair(
            topic_a_id=focal_id,
            topic_a_keyword="Focal",
            topic_a_explanation="Exp",
            topic_a_subject_id=str(uuid4()),
            topic_b_id=str(uuid4()),
            topic_b_keyword=f"Cross {i}",
            topic_b_explanation="Exp",
            topic_b_subject_id=str(uuid4()),
            similarity=0.83 + (i * 0.02),
            scope="cross_subject",
        )
        for i in range(4)
    ]

    with patch.object(service, "_query_neighbors") as mock_query:
        mock_query.side_effect = [mock_same, mock_cross]

        with patch("backend.app.services.candidate_finder.get_db_cursor") as mock_cursor_ctx:
            mock_cursor = MagicMock()
            mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {
                "id": focal_id,
                "keyword": "Focal",
                "explanation": "Exp",
                "subject_id": str(uuid4()),
                "subject_name": "Subject A",
                "has_embedding": True,
            }

            result = service.find_candidates_for_topic(focal_id, max_cap=5)

            # Cap of 5 must be respected
            assert result.total_candidates == 5
            # Top similarities must be chosen
            total_items = result.same_subject_candidates + result.cross_subject_candidates
            assert len(total_items) == 5
            for item in total_items:
                # Highest similarities should be in the top 5
                assert item.similarity >= 0.78


def test_cross_subject_stricter_threshold_applied():
    """Verify that different thresholds are passed to same-subject vs cross-subject queries."""
    service = CandidateFinderService(
        same_subject_threshold=0.70,
        cross_subject_threshold=0.85,
    )
    focal_id = str(uuid4())

    with patch.object(service, "_query_neighbors") as mock_query:
        mock_query.return_value = []

        with patch("backend.app.services.candidate_finder.get_db_cursor") as mock_cursor_ctx:
            mock_cursor = MagicMock()
            mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {
                "id": focal_id,
                "keyword": "Test Topic",
                "explanation": "Exp",
                "subject_id": str(uuid4()),
                "subject_name": "Subject 1",
                "has_embedding": True,
            }

            service.find_candidates_for_topic(focal_id)

            assert mock_query.call_count == 2
            # Call 1: same_subject=True, threshold=0.70
            call_same = mock_query.call_args_list[0]
            assert call_same.kwargs["same_subject"] is True
            assert call_same.kwargs["threshold"] == 0.70

            # Call 2: same_subject=False, threshold=0.85 (stricter)
            call_cross = mock_query.call_args_list[1]
            assert call_cross.kwargs["same_subject"] is False
            assert call_cross.kwargs["threshold"] == 0.85


def test_missing_embedding_skipped_gracefully():
    """Verify that topics without embeddings are safely skipped without crash."""
    service = CandidateFinderService()
    focal_id = str(uuid4())

    with patch("backend.app.services.candidate_finder.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "id": focal_id,
            "keyword": "Unembedded Topic",
            "explanation": "Exp",
            "subject_id": str(uuid4()),
            "subject_name": "Subject 1",
            "has_embedding": False,
        }

        result = service.find_candidates_for_topic(focal_id)
        assert result.total_candidates == 0
        assert len(result.same_subject_candidates) == 0
        assert len(result.cross_subject_candidates) == 0


# ==============================================================================
# 2. SQL Query Filtering Verification (Deleted and Locked Edge Exclusion)
# ==============================================================================


def test_query_neighbors_filters_out_deleted_and_locked_edges():
    """Verify that _query_neighbors includes NOT EXISTS filtering for deleted/locked edges."""
    service = CandidateFinderService()
    focal_id = str(uuid4())
    subject_id = str(uuid4())

    with patch("backend.app.services.candidate_finder.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        service._query_neighbors(
            focal_topic_id=focal_id,
            focal_subject_id=subject_id,
            same_subject=True,
            threshold=0.70,
            k=10,
        )

        # Inspect the SQL passed to execute
        executed_sql, params = mock_cursor.execute.call_args[0]
        # Must check for deleted edges
        assert "status = 'deleted'" in executed_sql
        # Must check for locked edges
        assert "locked = TRUE" in executed_sql
        # Must check for active edges
        assert "status IN ('auto', 'edited')" in executed_sql
        # Must exclude self-pairing
        assert "t2.id != t1.id" in executed_sql


# ==============================================================================
# 3. Canonical Pair Ordering and Symmetric Persistence
# ==============================================================================


def test_save_candidates_symmetric_deduplication():
    """Verify that save_candidates prevents saving duplicate (A, B) and (B, A) pairs."""
    service = CandidateFinderService()
    id_1 = "11111111-1111-1111-1111-111111111111"
    id_2 = "22222222-2222-2222-2222-222222222222"

    pair_1 = CandidatePair(
        topic_a_id=id_1,
        topic_a_keyword="Topic 1",
        topic_a_explanation="Exp",
        topic_a_subject_id=str(uuid4()),
        topic_b_id=id_2,
        topic_b_keyword="Topic 2",
        topic_b_explanation="Exp",
        topic_b_subject_id=str(uuid4()),
        similarity=0.88,
        scope="same_subject",
    )
    # Reverse order with lower similarity
    pair_2 = CandidatePair(
        topic_a_id=id_2,
        topic_a_keyword="Topic 2",
        topic_a_explanation="Exp",
        topic_a_subject_id=str(uuid4()),
        topic_b_id=id_1,
        topic_b_keyword="Topic 1",
        topic_b_explanation="Exp",
        topic_b_subject_id=str(uuid4()),
        similarity=0.85,
        scope="same_subject",
    )

    with patch("backend.app.services.candidate_finder.get_db_cursor") as mock_cursor_ctx:
        mock_cursor = MagicMock()
        mock_cursor_ctx.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"id": str(uuid4())}

        # Saving both should deduplicate in memory to 1 execution
        saved = service.save_candidates([pair_1, pair_2])

        assert saved == 1
        assert mock_cursor.execute.call_count == 1
        # The higher similarity pair (0.88) should be the one preserved
        executed_params = mock_cursor.execute.call_args[0][1]
        assert executed_params[2] == 0.88


# ==============================================================================
# 4. API Endpoints Tests
# ==============================================================================


def test_api_find_candidates_endpoint():
    """Test POST /api/candidates/find endpoint logic."""
    with patch(
        "backend.app.api.routes.candidates.candidate_service.find_and_store_candidates"
    ) as mock_find:
        mock_find.return_value = CandidateBatchResponse(
            total_topics_evaluated=2,
            total_candidates_found=3,
            total_candidates_stored=3,
            same_subject_count=2,
            cross_subject_count=1,
            results=[],
        )

        params = CandidateSearchParams(
            topic_ids=[str(uuid4()), str(uuid4())],
            same_subject_threshold=0.72,
            cross_subject_threshold=0.84,
            max_per_topic=6,
            persist=True,
        )
        response = find_candidates(params)

        assert response.total_topics_evaluated == 2
        assert response.total_candidates_found == 3
        assert response.same_subject_count == 2
        assert response.cross_subject_count == 1


def test_api_get_pending_candidates_endpoint():
    """Test GET /api/candidates/pending endpoint logic."""
    with patch(
        "backend.app.api.routes.candidates.candidate_service.get_stored_candidates"
    ) as mock_get:
        mock_get.return_value = [
            CandidatePair(
                id=str(uuid4()),
                topic_a_id=str(uuid4()),
                topic_a_keyword="Binary Search",
                topic_a_explanation="Divide and conquer search",
                topic_a_subject_id=str(uuid4()),
                topic_b_id=str(uuid4()),
                topic_b_keyword="B-Tree",
                topic_b_explanation="Self-balancing search tree",
                topic_b_subject_id=str(uuid4()),
                similarity=0.86,
                scope="same_subject",
                status="pending",
            )
        ]

        data = get_pending_candidates(scope="same_subject", limit=10)
        assert len(data) == 1
        assert data[0].topic_a_keyword == "Binary Search"
        assert data[0].similarity == 0.86


def test_api_get_candidates_for_topic_endpoint():
    """Test GET /api/candidates/by-topic/{topic_id} endpoint logic."""
    focal_id = str(uuid4())
    with patch(
        "backend.app.api.routes.candidates.candidate_service.get_stored_candidates"
    ) as mock_get:
        mock_get.return_value = [
            CandidatePair(
                id=str(uuid4()),
                topic_a_id=focal_id,
                topic_a_keyword="Topic A",
                topic_a_explanation="Exp A",
                topic_a_subject_id=str(uuid4()),
                topic_b_id=str(uuid4()),
                topic_b_keyword="Topic B",
                topic_b_explanation="Exp B",
                topic_b_subject_id=str(uuid4()),
                similarity=0.75,
                scope="same_subject",
                status="pending",
            )
        ]

        data = get_candidates_for_topic(topic_id=focal_id, status_filter="pending", limit=5)
        assert len(data) == 1
        assert data[0].topic_a_id == focal_id
