"""
Unit and Integration Tests for Link Editing, Soft Deletion, and Pipeline Lock Protection (Task T10).
Relies on:
  - Feature F08: Edit / delete / lock links.
  - Risk R16: New uploads overwrite corrected links (prevented by user locks).
  - RULEBOOK Section 13 Rule 2: User edits are sacred.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db_cursor
from backend.app.services.link_judge import LinkJudgeService
from backend.app.services.candidate_finder import CandidateFinderService

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_test_topics():
    """
    Creates two test topics in the database to test link operations.
    Cleans up created test records upon completion.
    """
    topic_a_id = str(uuid.uuid4())
    topic_b_id = str(uuid.uuid4())
    subject_id = str(uuid.uuid4())
    user_id = "00000000-0000-0000-0000-000000000001"

    with get_db_cursor() as cur:
        # Ensure dummy user and subject exist
        cur.execute(
            """
            INSERT INTO users (id, email, name)
            VALUES (%s, 'test_lock@studygraph.io', 'Lock Test User')
            ON CONFLICT (id) DO NOTHING;
            """,
            (user_id,),
        )
        cur.execute(
            """
            INSERT INTO subjects (id, user_id, name)
            VALUES (%s, %s, 'Computer Networks')
            ON CONFLICT (id) DO NOTHING;
            """,
            (subject_id, user_id),
        )

        # Create two topics with dummy embeddings
        # A dummy 768-dim zero vector formatted for pgvector
        zero_vec = "[" + ",".join(["0.01"] * 768) + "]"

        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'TCP Protocol', 'Transmission Control Protocol handles reliable transmission.', 'Web browsing', %s::vector, TRUE)
            ON CONFLICT (id) DO NOTHING;
            """,
            (topic_a_id, subject_id, zero_vec),
        )
        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'HTTP Protocol', 'Hypertext Transfer Protocol transfers web resources.', 'REST APIs', %s::vector, TRUE)
            ON CONFLICT (id) DO NOTHING;
            """,
            (topic_b_id, subject_id, zero_vec),
        )

    yield {
        "topic_a_id": topic_a_id,
        "topic_b_id": topic_b_id,
        "subject_id": subject_id,
    }

    # Teardown
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM edges WHERE topic_a IN (%s, %s) OR topic_b IN (%s, %s);", (topic_a_id, topic_b_id, topic_a_id, topic_b_id))
        cur.execute("DELETE FROM link_candidates WHERE topic_a IN (%s, %s) OR topic_b IN (%s, %s);", (topic_a_id, topic_b_id, topic_a_id, topic_b_id))
        cur.execute("DELETE FROM topics WHERE id IN (%s, %s);", (topic_a_id, topic_b_id))
        cur.execute("DELETE FROM subjects WHERE id = %s;", (subject_id,))


def test_manual_link_creation(setup_test_topics):
    """
    Tests creating a manual link between two topics:
    - Verifies status = 'edited' and locked = True
    - Verifies evidence snippet is labeled '[manual]'
    """
    topic_a = setup_test_topics["topic_a_id"]
    topic_b = setup_test_topics["topic_b_id"]

    payload = {
        "topic_a": topic_a,
        "topic_b": topic_b,
        "type": "prerequisite_of",
        "reason": "TCP must establish a 3-way handshake before HTTP data exchange begins.",
        "industry_example": "Web servers listening on port 80/443 require TCP connections.",
        "strength": 4,
        "snippet_a": "TCP guarantees ordered, loss-free data delivery.",
        "snippet_b": "HTTP runs on top of TCP by default.",
    }

    response = client.post("/api/edges/manual", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["locked"] is True
    assert data["status"] == "edited"
    assert data["type"] == "prerequisite_of"
    assert data["strength"] == 4
    assert data["topic_a_keyword"] == "TCP Protocol"
    assert data["topic_b_keyword"] == "HTTP Protocol"

    # Verify manual snippets
    evidence = data["evidence"]
    assert len(evidence) >= 2
    assert all("[manual]" in ev["snippet"] for ev in evidence)


def test_edge_editing_locks_link(setup_test_topics):
    """
    Tests editing an existing edge:
    - Modifying reason/type/strength sets status = 'edited' and locked = True.
    """
    topic_a = setup_test_topics["topic_a_id"]
    topic_b = setup_test_topics["topic_b_id"]

    # Fetch edge ID
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id FROM edges WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);",
            (topic_a, topic_b, topic_b, topic_a),
        )
        row = cur.fetchone()
        assert row is not None
        edge_id = row[0]

    update_payload = {
        "type": "part_of",
        "reason": "Updated reason: HTTP is an application layer protocol using TCP transport layer.",
        "strength": 5,
    }

    response = client.patch(f"/api/edges/{edge_id}", json=update_payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == str(edge_id)
    assert data["type"] == "part_of"
    assert data["reason"] == update_payload["reason"]
    assert data["strength"] == 5
    assert data["locked"] is True
    assert data["status"] == "edited"


def test_soft_delete_preserves_decision(setup_test_topics):
    """
    Tests soft-deleting an edge:
    - Sets status = 'deleted', locked = True, is_visible = False.
    - Edge disappears from active list, but appears when include_deleted=True.
    """
    topic_a = setup_test_topics["topic_a_id"]
    topic_b = setup_test_topics["topic_b_id"]

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id FROM edges WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);",
            (topic_a, topic_b, topic_b, topic_a),
        )
        edge_id = cur.fetchone()[0]

    # Delete the edge
    response = client.delete(f"/api/edges/{edge_id}")
    assert response.status_code == 200, response.text
    action = response.json()
    assert action["success"] is True
    assert action["status"] == "deleted"
    assert action["locked"] is True

    # Active edges list should NOT contain this edge
    list_active = client.get("/api/edges?include_deleted=false")
    assert list_active.status_code == 200
    active_ids = [e["id"] for e in list_active.json()]
    assert str(edge_id) not in active_ids

    # Query with include_deleted=true MUST contain this edge
    list_all = client.get("/api/edges?include_deleted=true")
    assert list_all.status_code == 200
    deleted_edge = next((e for e in list_all.json() if e["id"] == str(edge_id)), None)
    assert deleted_edge is not None
    assert deleted_edge["status"] == "deleted"
    assert deleted_edge["locked"] is True
    assert deleted_edge["is_visible"] is False


def test_pipeline_respects_locks(setup_test_topics):
    """
    Tests that CandidateFinder and LinkJudge strictly respect user locks and deletions:
    1. Candidate finder does not return pairs that are locked or deleted.
    2. Link judge aborts without overwriting if a pair is locked or deleted.
    """
    topic_a = setup_test_topics["topic_a_id"]
    topic_b = setup_test_topics["topic_b_id"]

    # 1. Test CandidateFinderService neighbor query exclusion
    finder = CandidateFinderService()
    with get_db_cursor() as cur:
        neighbors = finder._query_neighbors(
            focal_topic_id=topic_a,
            focal_subject_id=setup_test_topics["subject_id"],
            same_subject=True,
            threshold=0.0,  # accept anything
            k=10,
            cursor=cur,
        )
        # Because edge between topic_a and topic_b is locked/deleted, it MUST NOT appear in neighbors
        matched = [c for c in neighbors if c.topic_b_id == topic_b or c.topic_a_id == topic_b]
        assert len(matched) == 0, "Candidate finder must not return locked or deleted edges!"

    # 2. Test LinkJudgeService evaluation rejection on locked/deleted edge
    judge = LinkJudgeService()
    with get_db_cursor() as cur:
        result, tokens = judge.judge_candidate(
            candidate_id=None,
            topic_a_id=topic_a,
            topic_b_id=topic_b,
            scope="same_subject",
            cursor=cur,
        )
        assert result.verdict == "reject"
        assert "locked or deleted" in result.rejection_reason.lower()
        assert result.edge_id is None
        assert result.snippets_verified is False

