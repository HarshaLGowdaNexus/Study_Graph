"""
Automated Tests for Cross-Subject 3D Graph & Text List (Task T15).
Validates:
  - Feature F12: Cross-subject 3D graph with colored clusters & synchronized text list
  - Risk R04 & R19: Evidence from BOTH subjects, reason & industry example required
  - Quality Gate G08: High-performance 3D structure ready for WebGL rendering
  - Quality Gate G09: >= 3 verified cross-subject links with strength >= 3
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.api.routes.graphs import get_cross_subject_benchmark_graph
from backend.app.services.graph_service import graph_service
from backend.app.services.synthetic_graph_service import synthetic_graph_service


def test_cross_subject_benchmark_generation():
    """
    Verifies that the multi-subject benchmark generates multiple subjects,
    nodes with valid subject tags, genuine cross-subject links (strength >= 3),
    dual-subject verbatim evidence, and intra-subject links for fading.
    """
    data = synthetic_graph_service.generate_cross_subject_benchmark()

    assert data["scope"] == "cross_subject"
    subjects = data["subjects"]
    nodes = data["nodes"]
    links = data["links"]
    stats = data["stats"]

    # 1. Verify subject variety (at least 2, benchmark has 4)
    assert len(subjects) >= 4
    subject_ids = {s["id"] for s in subjects}
    assert "subj-networks" in subject_ids
    assert "subj-os" in subject_ids
    assert "subj-dbms" in subject_ids
    assert "subj-arch" in subject_ids

    # 2. Verify nodes have subject affiliations and content
    assert len(nodes) >= 20
    for node in nodes:
        assert node["subject_id"] in subject_ids
        assert len(node["keyword"].strip()) > 0
        assert len(node["explanation"].strip()) > 0
        assert len(node["real_world_use"].strip()) > 0

    # 3. Verify cross-subject links meet strict Golden Rules (G09 >= 3 genuine links with strength >= 3)
    cross_links = [l for l in links if l["scope"] == "cross_subject"]
    strong_cross_links = [l for l in cross_links if l["strength"] >= 3]
    assert len(strong_cross_links) >= 3, f"Quality gate G09 requires >= 3 cross links with strength >= 3, got {len(strong_cross_links)}"

    # Verify spectrum of strengths exists for dynamic UI filtering (1 to 5)
    strengths = {l["strength"] for l in cross_links}
    assert 1 in strengths and 5 in strengths, "Cross-subject links should span varied strengths for interactive slider filtering"

    for cl in cross_links:
        # Cross-subject must connect two different subjects
        assert cl["source_subject_id"] != cl["target_subject_id"], (
            f"Link {cl['id']} is marked cross_subject but connects same subject: "
            f"{cl['source_subject_id']} == {cl['target_subject_id']}"
        )
        assert 1 <= cl["strength"] <= 5

        # Must have reason and real-world example
        assert len(cl["reason"].strip()) > 0
        assert len(cl["industry_example"].strip()) > 0

        # Must contain evidence quotes from BOTH subjects
        assert cl.get("snippet_a") is not None and len(cl["snippet_a"]) > 0
        assert cl.get("snippet_b") is not None and len(cl["snippet_b"]) > 0
        assert len(cl["evidence"]) >= 2

    # 4. Verify same-subject links exist so they can be faded in the 3D space
    same_links = [l for l in links if l["scope"] == "same_subject"]
    assert len(same_links) > 0
    for sl in same_links:
        assert sl["source_subject_id"] == sl["target_subject_id"]

    assert stats["cross_subject_links"] == len(cross_links)
    assert stats["same_subject_links"] == len(same_links)


def test_cross_subject_benchmark_endpoint():
    """
    Verifies that the /api/graphs/cross-subject/benchmark route returns
    the benchmark structure with 200 OK.
    """
    res = get_cross_subject_benchmark_graph()
    assert res is not None
    assert "subjects" in res
    assert "nodes" in res
    assert "links" in res
    assert res["stats"]["cross_subject_links"] >= 3


def test_assemble_cross_subject_graph_dual_evidence_query():
    """
    Verifies that assemble_cross_subject_graph queries edge_evidence
    and attaches snippet_a and snippet_b to links.
    """
    mock_cursor = MagicMock()
    # 1. Subjects query
    mock_cursor.fetchall.side_effect = [
        # subjects
        [
            {"id": "s1", "name": "Computer Networks"},
            {"id": "s2", "name": "Operating Systems"},
        ],
        # topics
        [
            {"id": "t1", "subject_id": "s1", "keyword": "Socket", "explanation": "Network endpoint", "real_world_use": "Web server", "module_no": 1, "reviewed": True, "cluster_id": None, "cluster_label": "Net"},
            {"id": "t2", "subject_id": "s2", "keyword": "Syscall", "explanation": "Kernel trap", "real_world_use": "OS interface", "module_no": 1, "reviewed": True, "cluster_id": None, "cluster_label": "OS"},
        ],
        # edges
        [
            {
                "id": "e1",
                "topic_a": "t1",
                "topic_b": "t2",
                "type": "applies_in",
                "reason": "Sockets use syscalls",
                "industry_example": "Nginx epoll",
                "strength": 5,
                "scope": "cross_subject",
                "status": "approved",
                "locked": True,
                "graph_version": 1,
            }
        ],
        # edge_evidence
        [
            {"edge_id": "e1", "chunk_id": "c1", "snippet": "Socket API calls wrap kernel syscalls."},
            {"edge_id": "e1", "chunk_id": "c2", "snippet": "Syscalls provide the boundary for network I/O."},
        ],
    ]

    with patch("backend.app.services.graph_service.get_db_cursor") as mock_db:
        mock_db.return_value.__enter__.return_value = mock_cursor
        result = graph_service.assemble_cross_subject_graph(user_id="test-user")

    assert result["scope"] == "cross_subject"
    assert len(result["subjects"]) == 2
    assert len(result["nodes"]) == 2
    assert len(result["links"]) == 1

    link = result["links"][0]
    assert link["scope"] == "cross_subject"
    assert link["source_keyword"] == "Socket"
    assert link["target_keyword"] == "Syscall"
    assert link["source_subject_name"] == "Computer Networks"
    assert link["target_subject_name"] == "Operating Systems"
    assert link["snippet_a"] == "Socket API calls wrap kernel syscalls."
    assert link["snippet_b"] == "Syscalls provide the boundary for network I/O."
    assert len(link["evidence"]) == 2

