"""
FastAPI Routes for Edges & Evidence (Tasks T09 & T10).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence, link_candidates)
  - Decision D09: Google Gemini Flash (for automated candidate evaluation)
  - RULEBOOK Section 13 Rule 2: User edits are sacred (locked and never overwritten).
  - Risk R16: New uploads overwrite corrected links (prevented by user locks and soft delete).
"""

import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status
from psycopg2.extras import RealDictCursor

from backend.app.database import get_db_cursor
from backend.app.schemas.edge import (
    EdgeEvidenceResponse,
    JudgeBatchResponse,
)
from backend.app.schemas.edge_edit import (
    EdgeActionResponse,
    EdgeDetailResponse,
    EdgeManualCreate,
    EdgeUpdate,
)
from backend.app.services.link_judge import LinkJudgeService

logger = logging.getLogger(__name__)

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
    Automatically respects user locks and soft-deletions.
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
    response_model=List[EdgeDetailResponse],
    summary="List edges with topic keywords, evidence snippets, and lock status",
)
def list_edges(
    subject_id: Optional[UUID] = Query(None, description="Filter edges connected to a subject"),
    scope: Optional[str] = Query(None, pattern="^(same_subject|cross_subject)$"),
    visible_only: bool = Query(True, description="Only return visible edges"),
    include_deleted: bool = Query(False, description="Include soft-deleted edges (for audit)"),
    locked_only: bool = Query(False, description="Only return user-locked edges"),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieves edges with joined topic keywords and verified evidence snippets."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT e.id, e.topic_a, e.topic_b, e.type, e.reason, e.industry_example,
                       e.strength, e.scope, e.status, e.locked, e.is_visible, e.graph_version,
                       ta.keyword AS topic_a_keyword, tb.keyword AS topic_b_keyword,
                       sa.name AS topic_a_subject_name, sb.name AS topic_b_subject_name
                FROM edges e
                JOIN topics ta ON ta.id = e.topic_a
                JOIN topics tb ON tb.id = e.topic_b
                LEFT JOIN subjects sa ON sa.id = ta.subject_id
                LEFT JOIN subjects sb ON sb.id = tb.subject_id
                WHERE 1=1
            """
            params = []
            if not include_deleted:
                query += " AND e.status != 'deleted'"
                if visible_only:
                    query += " AND e.is_visible = TRUE"
            if locked_only:
                query += " AND e.locked = TRUE"
            if scope:
                query += " AND e.scope = %s"
                params.append(scope)
            if subject_id:
                query += " AND (ta.subject_id = %s OR tb.subject_id = %s)"
                params.extend([str(subject_id), str(subject_id)])

            query += " ORDER BY e.locked DESC, e.strength DESC, e.id DESC LIMIT %s;"
            params.append(limit)

            cur.execute(query, tuple(params))
            edge_rows = cur.fetchall() or []

            results: List[EdgeDetailResponse] = []
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
                        chunk_id=ev.get("chunk_id"),
                        snippet=ev["snippet"],
                    )
                    for ev in evidence_rows
                ]

                results.append(
                    EdgeDetailResponse(
                        id=row["id"],
                        topic_a=row["topic_a"],
                        topic_b=row["topic_b"],
                        topic_a_keyword=row["topic_a_keyword"],
                        topic_b_keyword=row["topic_b_keyword"],
                        topic_a_subject_name=row.get("topic_a_subject_name"),
                        topic_b_subject_name=row.get("topic_b_subject_name"),
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
        logger.error(f"Error querying edges: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}",
        )


@router.get(
    "/{edge_id}",
    response_model=EdgeDetailResponse,
    summary="Get single edge by ID with details and evidence",
)
def get_edge_by_id(edge_id: UUID):
    """Retrieves a single edge along with its evidence snippets and topic keywords."""
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.id, e.topic_a, e.topic_b, e.type, e.reason, e.industry_example,
                       e.strength, e.scope, e.status, e.locked, e.is_visible, e.graph_version,
                       ta.keyword AS topic_a_keyword, tb.keyword AS topic_b_keyword,
                       sa.name AS topic_a_subject_name, sb.name AS topic_b_subject_name
                FROM edges e
                JOIN topics ta ON ta.id = e.topic_a
                JOIN topics tb ON tb.id = e.topic_b
                LEFT JOIN subjects sa ON sa.id = ta.subject_id
                LEFT JOIN subjects sb ON sb.id = tb.subject_id
                WHERE e.id = %s;
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
                    chunk_id=ev.get("chunk_id"),
                    snippet=ev["snippet"],
                )
                for ev in evidence_rows
            ]

            return EdgeDetailResponse(
                id=row["id"],
                topic_a=row["topic_a"],
                topic_b=row["topic_b"],
                topic_a_keyword=row["topic_a_keyword"],
                topic_b_keyword=row["topic_b_keyword"],
                topic_a_subject_name=row.get("topic_a_subject_name"),
                topic_b_subject_name=row.get("topic_b_subject_name"),
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
        logger.error(f"Error fetching edge {edge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query error: {str(e)}",
        )


@router.patch(
    "/{edge_id}",
    response_model=EdgeDetailResponse,
    summary="Edit an edge (marks status='edited' and locked=TRUE)",
)
def edit_edge(edge_id: UUID, payload: EdgeUpdate):
    """
    Edits an edge's type, reason, industry_example, strength, or visibility.
    Per RULEBOOK Section 13 Rule 2 and Risk R16:
    Any user modification locks the link (locked = True) and marks status = 'edited'.
    This prevents automated pipelines from ever overwriting the student's changes.
    """
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            # Check edge exists
            cur.execute("SELECT id, topic_a, topic_b FROM edges WHERE id = %s;", (str(edge_id),))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")

            # Build dynamic update statement
            updates = ["status = 'edited'", "locked = TRUE"]
            params = []

            if payload.type is not None:
                updates.append("type = %s")
                params.append(payload.type)
            if payload.reason is not None:
                updates.append("reason = %s")
                params.append(payload.reason.strip())
            if payload.industry_example is not None:
                updates.append("industry_example = %s")
                params.append(payload.industry_example.strip())
            if payload.strength is not None:
                updates.append("strength = %s")
                params.append(payload.strength)
            if payload.is_visible is not None:
                updates.append("is_visible = %s")
                params.append(payload.is_visible)

            params.append(str(edge_id))
            set_clause = ", ".join(updates)
            update_query = f"UPDATE edges SET {set_clause} WHERE id = %s RETURNING id;"
            cur.execute(update_query, tuple(params))

            # Dismiss any pending candidate pair so background worker does not re-evaluate
            topic_a_id = str(existing["topic_a"])
            topic_b_id = str(existing["topic_b"])
            cur.execute(
                """
                UPDATE link_candidates
                SET status = 'dismissed'
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
                """,
                (topic_a_id, topic_b_id, topic_b_id, topic_a_id),
            )

        logger.info(f"[Edge Edit] User edited edge {edge_id}: marked status='edited', locked=TRUE.")
        return get_edge_by_id(edge_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editing edge {edge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit edge: {str(e)}",
        )


@router.delete(
    "/{edge_id}",
    response_model=EdgeActionResponse,
    summary="Soft-delete an edge (marks status='deleted', locked=TRUE, is_visible=FALSE)",
)
def soft_delete_edge(edge_id: UUID):
    """
    Soft-deletes an edge per RULEBOOK Section 13 Rule 2 and Risk R16:
    Instead of permanently deleting the row from the database (hard delete),
    we set status = 'deleted', locked = TRUE, and is_visible = FALSE.
    This preserves the student's decision in the system's memory, ensuring that
    future incremental pipeline runs will NEVER recreate this rejected connection.
    """
    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, topic_a, topic_b FROM edges WHERE id = %s;", (str(edge_id),))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")

            # Perform soft delete with lock
            cur.execute(
                """
                UPDATE edges
                SET status = 'deleted', locked = TRUE, is_visible = FALSE
                WHERE id = %s
                RETURNING id, status, locked;
                """,
                (str(edge_id),),
            )
            deleted_edge = cur.fetchone()

            # Dismiss candidate pair so candidate finder/judge never surfaces it again
            topic_a_id = str(existing["topic_a"])
            topic_b_id = str(existing["topic_b"])
            cur.execute(
                """
                UPDATE link_candidates
                SET status = 'dismissed'
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
                """,
                (topic_a_id, topic_b_id, topic_b_id, topic_a_id),
            )

        logger.info(f"[Edge Soft Delete] Edge {edge_id} soft-deleted and locked. Pair will never return.")
        return EdgeActionResponse(
            success=True,
            message="Link soft-deleted and locked. The pipeline will never recreate this link.",
            edge_id=edge_id,
            status="deleted",
            locked=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error soft-deleting edge {edge_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to soft delete edge: {str(e)}",
        )


@router.post(
    "/manual",
    response_model=EdgeDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a student-defined link between two topics",
)
def create_manual_edge(payload: EdgeManualCreate):
    """
    Creates a student-defined link between two topics.
    - Requires: topic_a, topic_b, type, reason.
    - Automatically sets status = 'edited' and locked = TRUE.
    - Automatically determines scope: same_subject vs cross_subject.
    - Evidence snippets are optional, labeled '[manual]' if provided.
    - Dismisses any pending link_candidates for this pair.
    """
    if str(payload.topic_a) == str(payload.topic_b):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A topic cannot be linked to itself.",
        )

    try:
        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            # Verify topics exist and check their subjects
            cur.execute(
                "SELECT id, keyword, subject_id FROM topics WHERE id IN (%s, %s);",
                (str(payload.topic_a), str(payload.topic_b)),
            )
            found_topics = cur.fetchall() or []
            if len(found_topics) < 2:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="One or both topics could not be found.",
                )

            t_map = {str(t["id"]): t for t in found_topics}
            topic_a = t_map[str(payload.topic_a)]
            topic_b = t_map[str(payload.topic_b)]

            # Determine scope
            scope = "same_subject" if topic_a["subject_id"] == topic_b["subject_id"] else "cross_subject"

            # Check if an edge already exists on canonical pair
            canonical_check = """
                SELECT id, status, locked FROM edges
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
            """
            cur.execute(
                canonical_check,
                (str(payload.topic_a), str(payload.topic_b), str(payload.topic_b), str(payload.topic_a)),
            )
            existing_edge = cur.fetchone()

            if existing_edge:
                edge_id = existing_edge["id"]
                # Update existing edge to user's manual link
                update_query = """
                    UPDATE edges
                    SET type = %s, reason = %s, industry_example = %s, strength = %s,
                        scope = %s, status = 'edited', locked = TRUE, is_visible = %s, graph_version = 1
                    WHERE id = %s
                    RETURNING id;
                """
                cur.execute(
                    update_query,
                    (
                        payload.type,
                        payload.reason.strip(),
                        payload.industry_example.strip() if payload.industry_example else "Practical application",
                        payload.strength,
                        scope,
                        payload.is_visible,
                        edge_id,
                    ),
                )
                # Clear existing evidence before inserting manual evidence
                cur.execute("DELETE FROM edge_evidence WHERE edge_id = %s;", (edge_id,))
            else:
                insert_query = """
                    INSERT INTO edges (
                        topic_a, topic_b, type, reason, industry_example,
                        strength, scope, status, locked, is_visible, graph_version
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'edited', TRUE, %s, 1)
                    RETURNING id;
                """
                cur.execute(
                    insert_query,
                    (
                        str(payload.topic_a),
                        str(payload.topic_b),
                        payload.type,
                        payload.reason.strip(),
                        payload.industry_example.strip() if payload.industry_example else "Practical application",
                        payload.strength,
                        scope,
                        payload.is_visible,
                    ),
                )
                edge_id = cur.fetchone()["id"]

            # Insert optional evidence snippets labeled '[manual]'
            evidence_sql = "INSERT INTO edge_evidence (edge_id, chunk_id, snippet) VALUES (%s, %s, %s);"
            if payload.snippet_a and payload.snippet_a.strip():
                snip_a = payload.snippet_a.strip()
                if not snip_a.startswith("[manual]"):
                    snip_a = f"[manual] {snip_a}"
                cur.execute(evidence_sql, (str(edge_id), None, snip_a))

            if payload.snippet_b and payload.snippet_b.strip():
                snip_b = payload.snippet_b.strip()
                if not snip_b.startswith("[manual]"):
                    snip_b = f"[manual] {snip_b}"
                cur.execute(evidence_sql, (str(edge_id), None, snip_b))

            # If no snippets provided, record a default manual citation marker per user term requirement
            if not payload.snippet_a and not payload.snippet_b:
                cur.execute(
                    evidence_sql,
                    (str(edge_id), None, "[manual] User-defined conceptual link"),
                )

            # Dismiss candidate pair
            cur.execute(
                """
                UPDATE link_candidates
                SET status = 'dismissed'
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
                """,
                (str(payload.topic_a), str(payload.topic_b), str(payload.topic_b), str(payload.topic_a)),
            )

        logger.info(f"[Edge Manual Add] Created manual link {edge_id} between {topic_a['keyword']} and {topic_b['keyword']}.")
        return get_edge_by_id(edge_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating manual edge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create manual edge: {str(e)}",
        )
