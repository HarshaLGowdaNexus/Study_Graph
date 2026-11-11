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
from backend.app.database import get_db_cursor
from backend.app.services.cluster_service import cluster_service
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
async def get_cross_subject_graph(
    fresh: bool = Query(False, description="Force recompile instead of cache hit"),
    demo: bool = Query(False, description="Return multi-subject benchmark graph for demo/testing"),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns the holistic multi-subject graph linking concepts across all subjects
    belonging to the authenticated student.
    """
    if demo:
        return synthetic_graph_service.generate_cross_subject_benchmark()

    cache_key = f"cross_subject:{current_user.id}"
    if fresh:
        res = graph_service.refresh_and_cache_graph(user_id=current_user.id)
    else:
        res = graph_service.get_cached_graph(cache_key=cache_key, user_id=current_user.id)

    # If the student's database currently has fewer than 2 subjects or 0 cross-subject links,
    # seamlessly provide the rich multi-subject benchmark so the 3D playground is immediately interactive
    if not res.get("nodes") or not res.get("subjects") or len(res.get("subjects", [])) < 2 or res.get("stats", {}).get("cross_subject_links", 0) == 0:
        return synthetic_graph_service.generate_cross_subject_benchmark()

    return res


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

