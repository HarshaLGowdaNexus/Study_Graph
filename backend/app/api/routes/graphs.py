"""
Graph and Hierarchy API Routes for StudyGraph.
Relies on:
  - Decision D01 & D03: React and react-force-graph 2D/3D clients.
  - Decision D05: Supabase PostgreSQL cache retrieval.
  - Pipeline Step 12 & 14: Community cluster zoom and cached graph loading.
  - Rule 11 (Privacy): Multi-tenant isolation ensuring students only view their own graphs.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
import psycopg2.extras

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.services.cluster_service import cluster_service
from backend.app.services.demo_service import demo_service
from backend.app.services.graph_service import graph_service
from backend.app.services.synthetic_graph_service import synthetic_graph_service

router = APIRouter()


class GraphVersionResponse(BaseModel):
    id: str
    version_number: int
    summary: str
    created_at: str


@router.get("/graphs/synthetic/stress-test")
def get_synthetic_stress_test_graph(
    node_count: int = Query(500, ge=10, le=1000, description="Total benchmark nodes to generate"),
    cluster_id: Optional[str] = Query(None, description="Zoom/filter to specific cluster sub-graph"),
    max_nodes: Optional[int] = Query(None, ge=10, le=1000, description="Maximum visible nodes cap"),
) -> Dict[str, Any]:
    """
    Returns a deterministic synthetic benchmark graph with up to 500+ topics
    for stress-testing client-side canvas rendering, force simulation, and camera zoom (R09, R14).
    """
    return synthetic_graph_service.generate_benchmark_graph(
        node_count=node_count,
        cluster_filter=cluster_id,
        max_visible_nodes=max_nodes,
    )


@router.get("/graphs/cross-subject/benchmark")
def get_cross_subject_benchmark_graph() -> Dict[str, Any]:
    """
    Returns a deterministic multi-subject benchmark graph with 4 subjects and genuine
    cross-subject links with dual-subject evidence for 3D testing and demo (F12, R04, R19, G09).
    """
    return synthetic_graph_service.generate_cross_subject_benchmark()


@router.get("/graphs/cross-subject")
def get_cross_subject_graph(
    fresh: bool = Query(False, description="Force recompile instead of cache hit"),
    demo: bool = Query(False, description="Return multi-subject benchmark graph for demo/testing"),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns the holistic multi-subject graph linking concepts across all subjects
    belonging to the authenticated student.
    """
    if demo or demo_service.is_demo_mode():
        return demo_service.get_frozen_graph()

    cache_key = f"cross_subject:{current_user.id}"
    try:
        if fresh:
            res = graph_service.refresh_and_cache_graph(user_id=current_user.id)
        else:
            res = graph_service.get_cached_graph(cache_key=cache_key, user_id=current_user.id)
    except Exception as exc:
        # Fallback to frozen demo snapshot if database is offline (R17)
        return demo_service.get_frozen_graph()

    # If the student's database currently has fewer than 2 subjects or 0 cross-subject links,
    # seamlessly provide the rich multi-subject benchmark so the 3D playground is immediately interactive
    if not res.get("nodes") or not res.get("subjects") or len(res.get("subjects", [])) < 2 or res.get("stats", {}).get("cross_subject_links", 0) == 0:
        return demo_service.get_frozen_graph()

    return res


@router.get("/graphs/config")
def get_graph_config() -> Dict[str, Any]:
    """
    Returns central graph visualization and performance fallback configuration
    from backend/app/core/config.py (Rule 5).
    """
    return {
        "fps_fallback_threshold": settings.GRAPH_FPS_FALLBACK_THRESHOLD,
        "fps_low_streak_count": settings.GRAPH_FPS_LOW_STREAK_COUNT,
        "default_search_hops": settings.GRAPH_SEARCH_DEFAULT_HOPS,
        "min_search_hops": settings.GRAPH_SEARCH_MIN_HOPS,
        "max_search_hops": settings.GRAPH_SEARCH_MAX_HOPS,
        "max_visible_nodes": settings.GRAPH_MAX_VISIBLE_NODES,
        "weak_link_threshold": settings.GRAPH_WEAK_LINK_THRESHOLD,
        "offline_demo_mode": settings.OFFLINE_DEMO_MODE,
    }


@router.get("/graphs/focus/{topic_id}")
def get_focused_topic_graph(
    topic_id: str,
    hops: Optional[int] = Query(None, ge=1, le=5, description="Neighborhood hop radius (clamped to config 1-3)"),
    include_weak: bool = Query(False, description="Include weak links below strength threshold"),
    max_nodes: Optional[int] = Query(None, ge=10, le=500, description="Maximum visible nodes cap"),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns a focused 2-3 hop local subgraph centered on the searched topic
    along with its Theory Card details (Feature F13, Risk R09, Rule 11).
    """
    try:
        return graph_service.get_focused_subgraph(
            topic_id=topic_id,
            user_id=current_user.id,
            hops=hops,
            include_weak=include_weak,
            max_nodes=max_nodes,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found or access denied.",
        )


@router.get("/graphs/{subject_id}")
async def get_subject_graph(
    subject_id: str,
    fresh: bool = Query(False, description="Force recompile instead of cache hit"),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns the pre-compiled, cached graph (nodes, links, and Louvain clusters)
    for a specific subject folder.
    """
    # Verify subject ownership
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s;",
            (subject_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject folder not found or access denied.",
            )

    cache_key = f"subject:{subject_id}"
    if fresh:
        return graph_service.refresh_and_cache_graph(
            user_id=current_user.id, subject_id=subject_id
        )

    return graph_service.get_cached_graph(
        cache_key=cache_key, user_id=current_user.id, subject_id=subject_id
    )


@router.get("/graphs/{subject_id}/versions", response_model=List[GraphVersionResponse])
async def list_graph_versions(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> List[GraphVersionResponse]:
    """
    Returns the chronological evolution history (graph versions) for a subject.
    """
    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT id, version_number, summary, created_at
            FROM graph_versions
            WHERE user_id = %s AND (subject_id = %s OR subject_id IS NULL)
            ORDER BY created_at DESC;
            """,
            (current_user.id, subject_id),
        )
        rows = cursor.fetchall()

    return [
        GraphVersionResponse(
            id=str(r["id"]),
            version_number=r.get("version_number") or 1,
            summary=r.get("summary") or "Graph updated",
            created_at=r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        )
        for r in rows
    ]


@router.post("/graphs/{subject_id}/recluster")
async def recluster_subject(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Manually triggers NetworkX Louvain community detection and refreshes cached graph JSON.
    """
    # Verify subject ownership
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id FROM subjects WHERE id = %s AND user_id = %s;",
            (subject_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject folder not found or access denied.",
            )

    clustering_res = cluster_service.build_subject_clusters(subject_id)
    cached_graph = graph_service.refresh_and_cache_graph(
        user_id=current_user.id, subject_id=subject_id
    )

    return {
        "message": "Subject reclustered successfully.",
        "clusters": clustering_res,
        "graph_stats": cached_graph["stats"],
    }

