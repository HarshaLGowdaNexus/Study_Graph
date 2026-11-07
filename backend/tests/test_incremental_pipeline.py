"""
Unit and Integration Tests for Incremental Update Pipeline, Louvain Hierarchy, and Graph Caching (Task T11).
Relies on:
  - Decision D07: FastAPI BackgroundTasks.
  - Decision D11: NetworkX Louvain Community Detection.
  - Quality Gate G07: Fast incremental updates.
  - Risks R07 (Incremental vs Full), R09 (Cluster Hierarchy), R16 (Lock Protection), R17 (Offline Cache).
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import get_db_cursor
from backend.app.schemas.candidate import CandidateSearchParams
from backend.app.services.candidate_finder import CandidateFinderService
from backend.app.services.cluster_service import cluster_service
from backend.app.services.graph_service import graph_service
from backend.app.services.topic_extractor import topic_extractor_service, TopicExtractionItem

client = TestClient(app)

TEST_USER_ID = "00000000-0000-0000-0000-000000000011"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000099"


@pytest.fixture(scope="module")
def setup_incremental_environment():
    """
    Sets up a test user, subject folder, and two documents (Doc A and Doc B)
    to test incremental pipeline updates and caching.
    """
    subject_id = str(uuid.uuid4())
    doc_a_id = str(uuid.uuid4())
    doc_b_id = str(uuid.uuid4())

    with get_db_cursor() as cur:
        # Create test users
        cur.execute(
            """
            INSERT INTO users (id, email, name)
            VALUES (%s, 'incremental_test@studygraph.io', 'Pipeline Test Student')
            ON CONFLICT (id) DO NOTHING;
            """,
            (TEST_USER_ID,),
        )
        cur.execute(
            """
            INSERT INTO users (id, email, name)
            VALUES (%s, 'other_student@studygraph.io', 'Other Student')
            ON CONFLICT (id) DO NOTHING;
            """,
            (OTHER_USER_ID,),
        )

        # Create test subject
        cur.execute(
            """
            INSERT INTO subjects (id, user_id, name)
            VALUES (%s, %s, 'Operating Systems T11')
            ON CONFLICT (id) DO NOTHING;
            """,
            (subject_id, TEST_USER_ID),
        )

        # Create two document records
        chunk_a_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status, storage_path)
            VALUES 
                (%s, %s, 1, 'Unit1_Processes.pdf', 'pdf', 'notes', 'done', 'test/u1.pdf'),
                (%s, %s, 2, 'Unit2_Memory.pdf', 'pdf', 'notes', 'queued', 'test/u2.pdf')
            ON CONFLICT (id) DO NOTHING;
            """,
            (doc_a_id, subject_id, doc_b_id, subject_id),
        )
        cur.execute(
            """
            INSERT INTO chunks (id, document_id, page, text, module_no, method)
            VALUES (%s, %s, 1, 'The process control block (PCB) stores process execution registers and state.', 1, 'direct')
            ON CONFLICT (id) DO NOTHING;
            """,
            (chunk_a_id, doc_a_id),
        )

    yield {
        "user_id": TEST_USER_ID,
        "subject_id": subject_id,
        "doc_a_id": doc_a_id,
        "doc_b_id": doc_b_id,
        "chunk_a_id": chunk_a_id,
    }

    # Teardown
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM graph_cache WHERE user_id IN (%s, %s);", (TEST_USER_ID, OTHER_USER_ID))
        cur.execute("DELETE FROM graph_versions WHERE user_id IN (%s, %s);", (TEST_USER_ID, OTHER_USER_ID))
        cur.execute("DELETE FROM clusters WHERE subject_id = %s;", (subject_id,))
        cur.execute("DELETE FROM edges WHERE topic_a IN (SELECT id FROM topics WHERE subject_id = %s) OR topic_b IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id, subject_id))
        cur.execute("DELETE FROM link_candidates WHERE topic_a IN (SELECT id FROM topics WHERE subject_id = %s) OR topic_b IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id, subject_id))
        cur.execute("DELETE FROM topic_sources WHERE topic_id IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id,))
        cur.execute("DELETE FROM topics WHERE subject_id = %s;", (subject_id,))
        cur.execute("DELETE FROM chunks WHERE document_id IN (%s, %s);", (doc_a_id, doc_b_id))
        cur.execute("DELETE FROM documents WHERE id IN (%s, %s);", (doc_a_id, doc_b_id))
        cur.execute("DELETE FROM subjects WHERE id = %s;", (subject_id,))


def test_idempotency_no_duplicate_topics(setup_incremental_environment):
    """
    Verifies that re-running topic extraction on the same document
    does not create duplicate topic rows (pure idempotency).
    """
    env = setup_incremental_environment
    subject_id = env["subject_id"]

    topic_item = TopicExtractionItem(
        keyword="Process Control Block",
        explanation="Data structure containing process state, program counter, and registers.",
        real_world_use="Linux kernel task_struct manages execution contexts.",
        source_chunk_ids=[env["chunk_a_id"]],
    )

    # First save
    first_ids = topic_extractor_service.save_topics_to_database(
        topics=[topic_item],
        subject_id=subject_id,
        module_no=1,
    )
    assert len(first_ids) == 1
    original_id = first_ids[0]

    # Second save (identical keyword - simulates document re-run)
    second_ids = topic_extractor_service.save_topics_to_database(
        topics=[topic_item],
        subject_id=subject_id,
        module_no=1,
    )
    assert len(second_ids) == 1
    assert second_ids[0] == original_id, "Re-running extraction must reuse existing topic ID instead of creating a duplicate."

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM topics WHERE subject_id = %s AND LOWER(keyword) = 'process control block';",
            (subject_id,),
        )
        count = cur.fetchone()[0]
        assert count == 1, f"Expected exactly 1 topic row, found {count}"


def test_incremental_link_emergence(setup_incremental_environment):
    """
    Simulates uploading File A, then later uploading File B:
    - Verifies candidate finder discovers links between B and A.
    - Verifies old documents are not re-queried against themselves.
    """
    env = setup_incremental_environment
    subject_id = env["subject_id"]

    # Vector pointing roughly in same direction (cosine similarity > 0.8)
    vec_a = "[" + ",".join(["0.05"] * 768) + "]"
    vec_b = "[" + ",".join(["0.051"] * 768) + "]"

    topic_a_id = str(uuid.uuid4())
    topic_b_id = str(uuid.uuid4())

    with get_db_cursor() as cur:
        # Topic A from Document A (already existing)
        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'Virtual Memory', 'Memory management technique virtualizing physical RAM.', 'OS paging', %s::vector, TRUE);
            """,
            (topic_a_id, subject_id, vec_a),
        )

        # Topic B from Document B (newly uploaded)
        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'Paging Mechanism', 'Hardware mechanism dividing virtual memory into fixed pages.', 'MMU translation', %s::vector, FALSE);
            """,
            (topic_b_id, subject_id, vec_b),
        )

    # Run CandidateFinder incrementally: pass ONLY topic_b_id in topic_ids!
    finder = CandidateFinderService()
    cand_params = CandidateSearchParams(
        subject_id=subject_id,
        topic_ids=[topic_b_id],
        same_subject_threshold=0.50,
    )
    batch = finder.find_and_store_candidates(cand_params)

    assert batch.total_candidates_found >= 1, "Candidate finder must discover relationship between new topic B and existing topic A."

    # Verify candidate pair in DB
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM link_candidates 
            WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
            """,
            (topic_b_id, topic_a_id, topic_a_id, topic_b_id),
        )
        assert cur.fetchone()[0] >= 1


def test_louvain_cluster_hierarchy(setup_incremental_environment):
    """
    Tests NetworkX Louvain Community Detection (Decision D11):
    - Connects topics with verified edges.
    - Verifies that cluster_service builds a two-tier hierarchy (Cluster -> Sub-cluster).
    - Verifies topics are assigned cluster_ids.
    """
    env = setup_incremental_environment
    subject_id = env["subject_id"]

    # Create an edge between our two test topics to form a community
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO edges (topic_a, topic_b, type, reason, industry_example, strength, scope, status)
            SELECT t1.id, t2.id, 'builds_on', 'Paging implements virtual memory abstraction.', 'Linux page tables', 5, 'same_subject', 'auto'
            FROM topics t1, topics t2
            WHERE t1.subject_id = %s AND t2.subject_id = %s AND t1.id != t2.id
            LIMIT 1
            ON CONFLICT DO NOTHING;
            """,
            (subject_id, subject_id),
        )

    # Run clustering
    res = cluster_service.build_subject_clusters(subject_id)

    assert res["top_level_count"] >= 1, "Louvain clustering should form at least 1 top-level cluster."
    assert res["sub_cluster_count"] >= 1, "Sub-clusters must be formed in the hierarchy."

    # Check database records
    with get_db_cursor() as cur:
        # Check clusters table
        cur.execute("SELECT COUNT(*) FROM clusters WHERE subject_id = %s;", (subject_id,))
        cluster_rows = cur.fetchone()[0]
        assert cluster_rows >= 1

        # Check topics.cluster_id updated
        cur.execute("SELECT COUNT(*) FROM topics WHERE subject_id = %s AND cluster_id IS NOT NULL;", (subject_id,))
        clustered_topics = cur.fetchone()[0]
        assert clustered_topics >= 1, "Topics must be linked to a valid cluster_id."


def test_graph_versions_and_cache(setup_incremental_environment):
    """
    Verifies that:
    1. A graph_version record is created with summary text.
    2. Compiled graph JSON is written to graph_cache.
    3. Retrieval hits the cache and invalidation works.
    """
    env = setup_incremental_environment
    user_id = env["user_id"]
    subject_id = env["subject_id"]

    summary_msg = "Added 2 topics, discovered 1 new link, organized into 1 cluster."

    # 1. Record graph version
    version_res = graph_service.record_graph_version(
        user_id=user_id,
        subject_id=subject_id,
        summary=summary_msg,
    )
    assert version_res["version_number"] >= 1
    assert version_res["summary"] == summary_msg

    # 2. Refresh and cache
    cached_graph = graph_service.refresh_and_cache_graph(
        user_id=user_id,
        subject_id=subject_id,
        graph_version_id=version_res["version_id"],
    )
    assert "nodes" in cached_graph
    assert "links" in cached_graph
    assert len(cached_graph["nodes"]) >= 2
    assert len(cached_graph["links"]) >= 1

    # 3. Retrieve from cache
    cache_key = f"subject:{subject_id}"
    read_cached = graph_service.get_cached_graph(cache_key, user_id=user_id, subject_id=subject_id)
    assert read_cached["subject_id"] == subject_id
    assert len(read_cached["nodes"]) == len(cached_graph["nodes"])

    # 4. Invalidate cache
    graph_service.invalidate_cache(user_id=user_id, subject_id=subject_id)
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM graph_cache WHERE cache_key = %s;", (cache_key,))
        assert cur.fetchone()[0] == 0, "Cache entry must be deleted after invalidation."


def test_graph_api_endpoints_and_user_isolation(setup_incremental_environment):
    """
    Verifies FastAPI endpoints for:
    - GET /api/graphs/{subject_id}
    - GET /api/graphs/cross-subject
    - GET /api/graphs/{subject_id}/versions
    - Enforces Rule 11 (Privacy): Another user cannot access these graph data.
    """
    env = setup_incremental_environment
    user_id = env["user_id"]
    subject_id = env["subject_id"]

    headers = {
        "x-test-user-id": user_id,
        "x-test-user-email": "incremental_test@studygraph.io",
    }

    # 1. Test subject graph endpoint
    resp = client.get(f"/api/graphs/{subject_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject_id"] == subject_id
    assert "nodes" in data
    assert "links" in data
    assert "clusters" in data

    # 2. Test cross-subject graph endpoint
    cross_resp = client.get("/api/graphs/cross-subject", headers=headers)
    assert cross_resp.status_code == 200
    cross_data = cross_resp.json()
    assert cross_data["scope"] == "cross_subject"
    assert "nodes" in cross_data

    # 3. Test graph versions endpoint
    versions_resp = client.get(f"/api/graphs/{subject_id}/versions", headers=headers)
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) >= 1
    assert "summary" in versions[0]

    # 4. Privacy Rule 11: Other user cannot access this student's graph
    other_headers = {
        "x-test-user-id": OTHER_USER_ID,
        "x-test-user-email": "other_student@studygraph.io",
    }
    forbidden_resp = client.get(f"/api/graphs/{subject_id}", headers=other_headers)
    assert forbidden_resp.status_code == 404, "Access to other student's graph must be rejected with 404."

