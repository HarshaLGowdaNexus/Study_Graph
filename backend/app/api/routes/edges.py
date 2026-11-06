"""
FastAPI Routes for Edges & Evidence (Task T09).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence)
  - Decision D09: Google Gemini Flash
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from psycopg2.extras import RealDictCursor

from backend.app.database import get_db_cursor
from backend.app.schemas.edge import (
    EdgeEvidenceResponse,
    EdgeResponse,
    JudgeBatchResponse,
)
from backend.app.services.link_judge import LinkJudgeService

router = APIRouter(prefix="/api/edges", tags=["edges"])
judge_service = LinkJudgeService()


@router.post(
    "/judge-candidates",
    response_model=JudgeBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate pending candidate pairs with LLM judge and code-level verification",
)
def judge_pending_candidates(
    limit: int = Query(10, ge=1, le=50, description="Max candidate pairs to judge"),
    scope: Optional[str] = Query(None, pattern="^(same_subject|cross_subject)$"),
):
    """
    Evaluates pending candidate topic pairs using Google Gemini Flash as an academic judge.
    Strictly verifies evidence snippets against source text before persisting any edge.
    """
    try:
        return judge_service.judge_pending_candidates(limit=limit, scope=scope)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error running link judge: {str(e)}",
        )


@router.get(
    "",
    response_model=List[EdgeResponse],
    summary="List edges with their evidence snippets",
)
def list_edges(
    subject_id: Optional[UUID] = Query(None, description="Filter edges connected to a subject"),
    scope: Optional[str] = Query(None, pattern="^(same_subject|cross_subject)$"),
    visible_only: bool = Query(True, description="Only return visible edges"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieves edges and joins their verified evidence snippets."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT e.id, e.topic_a, e.topic_b, e.type, e.reason, e.industry_example,
                       e.strength, e.scope, e.status, e.locked, e.is_visible, e.graph_version
                FROM edges e
                JOIN topics ta ON ta.id = e.topic_a
                JOIN topics tb ON tb.id = e.topic_b
                WHERE e.status != 'deleted'
            """
            params = []
            if visible_only:
                query += " AND e.is_visible = TRUE"
            if scope:
                query += " AND e.scope = %s"
                params.append(scope)
            if subject_id:
                query += " AND (ta.subject_id = %s OR tb.subject_id = %s)"
                params.extend([str(subject_id), str(subject_id)])

            query += " ORDER BY e.strength DESC, e.id DESC LIMIT %s;"
            params.append(limit)

            cur.execute(query, tuple(params))
            edge_rows = cur.fetchall() or []

            results: List[EdgeResponse] = []
            for row in edge_rows:
                edge_id = row["id"]
                evidence_query = """
                    SELECT id, edge_id, chunk_id, snippet
                    FROM edge_evidence
                    WHERE edge_id = %s;
                """
                cur.execute(evidence_query, (str(edge_id),))
                evidence_rows = cur.fetchall() or []

                evidence_list = [
                    EdgeEvidenceResponse(
                        id=ev.get("id"),
                        edge_id=ev["edge_id"],
                        chunk_id=ev["chunk_id"],
                        snippet=ev["snippet"],
                    )
                    for ev in evidence_rows
                ]

                results.append(
                    EdgeResponse(
                        id=row["id"],
                        topic_a=row["topic_a"],
                        topic_b=row["topic_b"],
                        type=row["type"],
                        reason=row["reason"],
                        industry_example=row["industry_example"],
                        strength=row["strength"],
                        scope=row["scope"],
                        status=row["status"],
                        locked=row["locked"],
                        is_visible=row["is_visible"],
                        graph_version=row["graph_version"],
                        evidence=evidence_list,
                    )
                )

            return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}",
        )


@router.get(
    "/{edge_id}",
    response_model=EdgeResponse,
    summary="Get single edge by ID with evidence",
)
def get_edge_by_id(edge_id: UUID):
    """Retrieves a single edge along with its evidence snippets."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, topic_a, topic_b, type, reason, industry_example,
                       strength, scope, status, locked, is_visible, graph_version
                FROM edges
                WHERE id = %s;
                """,
                (str(edge_id),),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")

            cur.execute(
                "SELECT id, edge_id, chunk_id, snippet FROM edge_evidence WHERE edge_id = %s;",
                (str(edge_id),),
            )
            evidence_rows = cur.fetchall() or []

            evidence_list = [
                EdgeEvidenceResponse(
                    id=ev.get("id"),
                    edge_id=ev["edge_id"],
                    chunk_id=ev["chunk_id"],
                    snippet=ev["snippet"],
                )
                for ev in evidence_rows
            ]

            return EdgeResponse(
                id=row["id"],
                topic_a=row["topic_a"],
                topic_b=row["topic_b"],
                type=row["type"],
                reason=row["reason"],
                industry_example=row["industry_example"],
                strength=row["strength"],
                scope=row["scope"],
                status=row["status"],
                locked=row["locked"],
                is_visible=row["is_visible"],
                graph_version=row["graph_version"],
                evidence=evidence_list,
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}",
        )

