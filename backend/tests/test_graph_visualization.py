"""
Automated Tests for Subject Graph Visualization (Task T14).
Validates:
  - Synthetic 500-topic graph generation, degree distribution, and link evidence
  - Node capping logic (prevents FPS drops per Risk R14)
  - Cluster sub-graph filtering (enables smooth camera zoom per Feature F11)
  - /api/graphs/synthetic/stress-test route handler
"""

import asyncio
import pytest

from backend.app.api.routes.graphs import get_synthetic_stress_test_graph
from backend.app.services.synthetic_graph_service import synthetic_graph_service


def test_synthetic_500_graph_generation():
    """
    Verifies that the synthetic generator produces exactly 500 nodes,
    well-formed links with strengths 1-5, valid clusters, and evidence snippets.
    """
    graph = synthetic_graph_service.generate_benchmark_graph(node_count=500, seed=42)

    nodes = graph["nodes"]
    links = graph["links"]
    clusters = graph["clusters"]
    stats = graph["stats"]

    # 1. Verify node count & stats
    assert len(nodes) == 500, f"Expected 500 nodes, got {len(nodes)}"
    assert stats["node_count"] == 500
    assert stats["is_synthetic"] is True

    # 2. Verify node fields
    for n in nodes[:20]:
        assert "id" in n
        assert "keyword" in n
        assert "explanation" in n
        assert "real_world_use" in n
        assert "module_no" in n
        assert 1 <= n["module_no"] <= 5
        assert "cluster_id" in n
        assert "cluster_label" in n
        assert "parent_cluster_label" in n

    # 3. Verify link structure and constraints
    assert len(links) > 0
    node_id_set = {n["id"] for n in nodes}
    for l in links[:30]:
        assert "id" in l
        assert l["source"] in node_id_set, f"Link source {l['source']} not in nodes"
        assert l["target"] in node_id_set, f"Link target {l['target']} not in nodes"
        assert 1 <= l["strength"] <= 5
        assert l["type"] in [
            "prerequisite_of",
            "applies_in",
            "part_of",
            "contrasts_with",
            "same_concept",
            "example_of",
        ]
        # Rule 13.1 evidence requirement
        assert "evidence" in l
        assert len(l["evidence"]) > 0

    # 4. Verify 8 cluster communities
    assert len(clusters) == 8
    for c in clusters:
        assert "id" in c
        assert "label" in c
        assert len(c["sub_clusters"]) > 0


def test_synthetic_graph_node_capping():
    """
    Verifies that requesting a node cap (e.g. 100) trims the visible nodes
    while preserving edge integrity (no orphan edges pointing to culled nodes).
    """
    graph = synthetic_graph_service.generate_benchmark_graph(
        node_count=500,
        max_visible_nodes=100,
        seed=42,
    )

    nodes = graph["nodes"]
    links = graph["links"]
    stats = graph["stats"]

    assert len(nodes) == 100
    assert stats["total_available_nodes"] == 500

    active_node_ids = {n["id"] for n in nodes}
    for l in links:
        assert l["source"] in active_node_ids
        assert l["target"] in active_node_ids


def test_synthetic_graph_cluster_subgraph_zoom():
    """
    Verifies that zooming/filtering into a specific cluster isolates
    only the nodes and internal links of that cluster sub-graph.
    """
    target_cluster = "syn-cluster-2"
    graph = synthetic_graph_service.generate_benchmark_graph(
        node_count=500,
        cluster_filter=target_cluster,
        seed=42,
    )

    nodes = graph["nodes"]
    links = graph["links"]

    assert len(nodes) > 0
    for n in nodes:
        assert n["parent_cluster_id"] == target_cluster

    node_ids = {n["id"] for n in nodes}
    for l in links:
        assert l["source"] in node_ids
        assert l["target"] in node_ids


def test_synthetic_stress_test_api_endpoint():
    """
    Verifies the endpoint handler responds with properly serialized graph JSON.
    """
    data = get_synthetic_stress_test_graph(node_count=100, cluster_id=None, max_nodes=50)

    assert data["subject_id"] == "synthetic-stress-test"
    assert len(data["nodes"]) == 50
    assert data["stats"]["total_available_nodes"] == 100
    assert len(data["clusters"]) == 8


def test_graph_config_defaults():
    """
    Verifies central configuration has correct defaults for graph visualization.
    """
    from backend.app.core.config import settings

    assert settings.GRAPH_MAX_VISIBLE_NODES >= 50
    assert settings.GRAPH_WEAK_LINK_THRESHOLD == 3
