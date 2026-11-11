"""
Automated Tests for Topic Search, Aliases, Focused 2-3 Hop Subgraphs, and Config (Task T16).
Validates:
  - Feature F13: Topic search (keyword + aliases) -> focused graph (2-3 hops) + Theory Card
  - Feature F15 & Risk R14: Centralized FPS threshold & node cap config
  - Rule 5: Central config values in backend/app/core/config.py
  - Rule 11: Multi-tenant user_id isolation
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.app.api.deps import CurrentUser
from backend.app.api.routes.graphs import get_graph_config, get_focused_topic_graph
from backend.app.api.routes.topics import search_topics
from backend.app.core.config import settings
from backend.app.services.graph_service import graph_service

USER_ALEX = CurrentUser(
    id="11111111-1111-4111-8111-111111111111",
    email="alex@university.edu",
    name="Alex Chen",
)


def test_graph_config_endpoint_matches_central_settings():
    """Config endpoint returns centralized FPS limit, streak count, and hop defaults."""
    cfg = get_graph_config()
    assert cfg["fps_fallback_threshold"] == settings.GRAPH_FPS_FALLBACK_THRESHOLD
    assert cfg["fps_low_streak_count"] == settings.GRAPH_FPS_LOW_STREAK_COUNT
    assert cfg["default_search_hops"] == settings.GRAPH_SEARCH_DEFAULT_HOPS
    assert cfg["min_search_hops"] == settings.GRAPH_SEARCH_MIN_HOPS
    assert cfg["max_search_hops"] == settings.GRAPH_SEARCH_MAX_HOPS
    assert cfg["max_visible_nodes"] == settings.GRAPH_MAX_VISIBLE_NODES
    assert cfg["weak_link_threshold"] == settings.GRAPH_WEAK_LINK_THRESHOLD


def test_search_topics_matches_alias_and_enforces_privacy():
    """Searching by merged alias returns the canonical topic with matched_alias and filters by user_id."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "id": "t-tcp-1",
            "subject_id": "subj-cn",
            "subject_name": "Computer Networks",
            "keyword": "TCP Handshake",
            "explanation": "Three-step SYN/SYN-ACK/ACK connection establishment.",
            "real_world_use": "Initializes reliable HTTP and TLS sessions.",
            "module_no": 4,
            "reviewed": True,
            "cluster_label": "Transport Layer",
            "aliases": ["3-way handshake", "SYN ACK handshake"],
        }
    ]

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.services.graph_service.get_db_cursor", mock_get_db):
        results = search_topics(
            q="3-way handshake", subject_id=None, limit=10, current_user=USER_ALEX
        )

    assert len(results) == 1
    assert results[0]["keyword"] == "TCP Handshake"
    assert results[0]["matched_alias"] == "3-way handshake"
    assert results[0]["module_no"] == 4
    assert "3-way handshake" in results[0]["aliases"]

    # Verify user isolation in SQL
    executed_sql, executed_params = mock_cursor.execute.call_args[0]
    assert "s.user_id = %s" in executed_sql
    assert executed_params[0] == USER_ALEX.id


def test_search_topics_empty_query_returns_empty():
    """Blank whitespace search queries return [] without querying database."""
    assert graph_service.search_topics(user_id=USER_ALEX.id, query="   ") == []


def _build_chain_cursor(mock_cursor):
    """Configures a mock DB cursor with a 4-hop topic chain plus 1 weak 1-hop edge."""
    mock_cursor.fetchone.return_value = {"id": "t0", "subject_id": "s1"}

    subjects = [{"id": "s1", "name": "Computer Networks"}]
    edges = [
        {"id": "e01", "topic_a": "t0", "topic_b": "t1", "type": "prerequisite_of", "reason": "r1", "industry_example": "ex1", "strength": 5, "scope": "same_subject", "status": "auto", "locked": False, "graph_version": 1},
        {"id": "e12", "topic_a": "t1", "topic_b": "t2", "type": "applies_in", "reason": "r2", "industry_example": "ex2", "strength": 4, "scope": "same_subject", "status": "auto", "locked": False, "graph_version": 1},
        {"id": "e23", "topic_a": "t2", "topic_b": "t3", "type": "part_of", "reason": "r3", "industry_example": "ex3", "strength": 4, "scope": "same_subject", "status": "auto", "locked": False, "graph_version": 1},
        {"id": "e34", "topic_a": "t3", "topic_b": "t4", "type": "example_of", "reason": "r4", "industry_example": "ex4", "strength": 4, "scope": "same_subject", "status": "auto", "locked": False, "graph_version": 1},
        {"id": "e_weak", "topic_a": "t0", "topic_b": "t_weak", "type": "same_concept", "reason": "rw", "industry_example": "exw", "strength": 1, "scope": "same_subject", "status": "auto", "locked": False, "graph_version": 1},
    ]
    all_topics = {
        tid: {
            "id": tid,
            "subject_id": "s1",
            "keyword": f"Topic {tid.upper()}",
            "explanation": f"Explanation for {tid}",
            "real_world_use": f"Real use for {tid}",
            "module_no": 4 if tid == "t0" else 2,
            "reviewed": True,
            "cluster_id": None,
            "cluster_label": "Transport",
            "parent_cluster_label": "Transport",
            "aliases": ["3-way handshake"] if tid == "t0" else [],
        }
        for tid in ("t0", "t1", "t2", "t3", "t4", "t_weak")
    }

    def execute_side_effect(sql, params=None):
        sql_lower = sql.lower()
        if "from subjects" in sql_lower:
            mock_cursor._next_rows = subjects
        elif "from edges" in sql_lower:
            mock_cursor._next_rows = edges
        elif "from topics t" in sql_lower and "any(" in sql_lower:
            requested_ids = params[0]
            mock_cursor._next_rows = [all_topics[tid] for tid in requested_ids if tid in all_topics]
        elif "from edge_evidence" in sql_lower:
            requested_eids = params[0]
            mock_cursor._next_rows = [
                {"edge_id": eid, "chunk_id": f"c-{eid}", "snippet": f"Snippet for {eid}"}
                for eid in requested_eids
            ]

    mock_cursor.execute.side_effect = execute_side_effect
    mock_cursor.fetchall.side_effect = lambda: getattr(mock_cursor, "_next_rows", [])


def test_focused_subgraph_respects_two_and_three_hops_and_weak_links():
    """Verifies 2-hop vs 3-hop BFS extraction, Theory Card payload, and weak-link hiding."""
    mock_cursor = MagicMock()
    _build_chain_cursor(mock_cursor)

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.services.graph_service.get_db_cursor", mock_get_db):
        two_hop = graph_service.get_focused_subgraph("t0", USER_ALEX.id, hops=2, include_weak=False)
        three_hop = graph_service.get_focused_subgraph("t0", USER_ALEX.id, hops=3, include_weak=False)
        with_weak = graph_service.get_focused_subgraph("t0", USER_ALEX.id, hops=2, include_weak=True)

    two_hop_ids = {n["id"] for n in two_hop["nodes"]}
    assert two_hop_ids == {"t0", "t1", "t2"}
    assert two_hop["stats"]["hidden_weak_count"] == 1
    assert two_hop["focus_topic"]["keyword"] == "Topic T0"
    assert two_hop["focus_topic"]["module_no"] == 4
    assert two_hop["focus_topic"]["aliases"] == ["3-way handshake"]

    three_hop_ids = {n["id"] for n in three_hop["nodes"]}
    assert three_hop_ids == {"t0", "t1", "t2", "t3"}
    assert "t4" not in three_hop_ids

    weak_ids = {n["id"] for n in with_weak["nodes"]}
    assert "t_weak" in weak_ids


def test_focused_subgraph_missing_topic_returns_404():
    """Requesting a topic not owned by the student raises HTTP 404 (Rule 11)."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.services.graph_service.get_db_cursor", mock_get_db):
        with pytest.raises(HTTPException) as exc_info:
            get_focused_topic_graph(
                topic_id="missing-topic",
                hops=2,
                include_weak=False,
                max_nodes=150,
                current_user=USER_ALEX,
            )
    assert exc_info.value.status_code == 404
