"""
Topic Review API Routes for StudyGraph (Task T06).
Relies on:
  - Feature F03: Review extracted topics screen (skippable).
  - Risk R06: Catches OCR/transcription errors before graph creation.
  - Risk R03: Prevents nonsense topics from polluting knowledge graphs.
  - RULEBOOK Rule 11: Privacy / User Isolation (queries filtered by student user_id).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
import psycopg2.extras

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.database import get_db_cursor
from backend.app.schemas.topic import (
    BulkReviewActionResponse,
    TopicListResponse,
    TopicReviewItem,
    TopicUpdateRequest,
)

router = APIRouter(tags=["Topics"])


@router.get("/topics", summary="List all user topics for link creation")
def list_topics(
    subject_id: Optional[str] = None,
):
    """Lists available topics for dropdown selection in manual linking."""
    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = """
            SELECT t.id, t.keyword, t.subject_id, s.name as subject_name
            FROM topics t
            JOIN subjects s ON s.id = t.subject_id
            WHERE 1=1
        """
        params = []
        if subject_id:
            query += " AND t.subject_id = %s"
            params.append(subject_id)
        query += " ORDER BY t.keyword ASC LIMIT 300;"
        cur.execute(query, tuple(params))
        return cur.fetchall() or []


@router.get("/documents/{document_id}/topics", response_model=TopicListResponse)
async def get_document_topics(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieves all topics extracted from an uploaded document for student review.
    Enforces user isolation (Rule 11): Only returns topics for documents owned by the student.
    """
    with get_db_cursor() as cursor:
        # Step 1: Verify document ownership
        cursor.execute(
            """
            SELECT d.id, d.filename, d.subject_id, s.name as subject_name
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            WHERE d.id = %s AND s.user_id = %s;
            """,
            (document_id, current_user.id),
        )
        doc_row = cursor.fetchone()
        if not doc_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied.",
            )

        doc_id, filename, subject_id, subject_name = doc_row

        # Step 2: Query all topics associated with this document's chunks
        cursor.execute(
            """
            SELECT 
                t.id,
                t.subject_id,
                t.keyword,
                t.explanation,
                t.real_world_use,
                t.module_no,
                t.reviewed,
                ARRAY_AGG(DISTINCT c.page ORDER BY c.page) as pages,
                COUNT(DISTINCT ts.chunk_id) as chunk_count
            FROM topics t
            JOIN topic_sources ts ON t.id = ts.topic_id
            JOIN chunks c ON ts.chunk_id = c.id
            WHERE c.document_id = %s
            GROUP BY t.id, t.subject_id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed
            ORDER BY t.keyword ASC;
            """,
            (document_id,),
        )
        rows = cursor.fetchall()

        items: List[TopicReviewItem] = []
        reviewed_count = 0
        unreviewed_count = 0

        for row in rows:
            t_id, s_id, keyword, explanation, real_world_use, module_no, reviewed, pages, chunk_cnt = row
            is_reviewed = bool(reviewed)
            if is_reviewed:
                reviewed_count += 1
            else:
                unreviewed_count += 1

            # Filter out any None pages just in case
            clean_pages = [p for p in (pages or []) if p is not None]

            items.append(
                TopicReviewItem(
                    id=str(t_id),
                    subject_id=str(s_id),
                    keyword=keyword,
                    explanation=explanation,
                    real_world_use=real_world_use,
                    module_no=module_no,
                    reviewed=is_reviewed,
                    source_pages=clean_pages,
                    chunk_count=chunk_cnt or 0,
                )
            )

        return TopicListResponse(
            document_id=str(doc_id),
            filename=filename,
            subject_id=str(subject_id),
            subject_name=subject_name,
            topics=items,
            total_count=len(items),
            reviewed_count=reviewed_count,
            unreviewed_count=unreviewed_count,
        )


@router.patch("/topics/{topic_id}", response_model=TopicReviewItem)
async def update_topic(
    topic_id: str,
    payload: TopicUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Updates a topic's keyword, explanation, real_world_use, or reviewed flag.
    Enforces user isolation (Rule 11) and 4-line limit (Rule 13.3).
    """
    with get_db_cursor() as cursor:
        # Step 1: Verify topic exists and belongs to a subject owned by current_user
        cursor.execute(
            """
            SELECT t.id, t.subject_id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed
            FROM topics t
            JOIN subjects s ON t.subject_id = s.id
            WHERE t.id = %s AND s.user_id = %s;
            """,
            (topic_id, current_user.id),
        )
        topic_row = cursor.fetchone()
        if not topic_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found or access denied.",
            )

        curr_id, curr_sub_id, curr_kw, curr_exp, curr_use, curr_mod, curr_rev = topic_row

        new_kw = payload.keyword if payload.keyword is not None else curr_kw
        new_exp = payload.explanation if payload.explanation is not None else curr_exp
        new_use = payload.real_world_use if payload.real_world_use is not None else curr_use
        new_rev = payload.reviewed if payload.reviewed is not None else curr_rev

        cursor.execute(
            """
            UPDATE topics
            SET keyword = %s,
                explanation = %s,
                real_world_use = %s,
                reviewed = %s
            WHERE id = %s
            RETURNING id, subject_id, keyword, explanation, real_world_use, module_no, reviewed;
            """,
            (new_kw, new_exp, new_use, new_rev, topic_id),
        )
        updated_row = cursor.fetchone()

        # Fetch source citations for complete TopicReviewItem response
        cursor.execute(
            """
            SELECT ARRAY_AGG(DISTINCT c.page ORDER BY c.page) as pages,
                   COUNT(DISTINCT ts.chunk_id) as chunk_count
            FROM topic_sources ts
            JOIN chunks c ON ts.chunk_id = c.id
            WHERE ts.topic_id = %s;
            """,
            (topic_id,),
        )
        cite_row = cursor.fetchone()
        pages = [p for p in (cite_row[0] or []) if p is not None] if cite_row else []
        chunk_count = cite_row[1] if cite_row else 0

        return TopicReviewItem(
            id=str(updated_row[0]),
            subject_id=str(updated_row[1]),
            keyword=updated_row[2],
            explanation=updated_row[3],
            real_world_use=updated_row[4],
            module_no=updated_row[5],
            reviewed=bool(updated_row[6]),
            source_pages=pages,
            chunk_count=chunk_count or 0,
        )


@router.delete("/topics/{topic_id}", status_code=status.HTTP_200_OK)
async def delete_topic(
    topic_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Deletes a topic from the knowledge base.
    Cascades to topic_sources and edges (Rule 11 user isolation enforced).
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM topics t
            USING subjects s
            WHERE t.subject_id = s.id
              AND t.id = %s
              AND s.user_id = %s
            RETURNING t.id;
            """,
            (topic_id, current_user.id),
        )
        deleted_row = cursor.fetchone()
        if not deleted_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found or access denied.",
            )

        return {"id": topic_id, "deleted": True, "message": "Topic successfully removed."}


@router.post("/documents/{document_id}/topics/approve-all", response_model=BulkReviewActionResponse)
async def approve_all_topics(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Marks all topics associated with the given document as reviewed (reviewed = TRUE).
    """
    with get_db_cursor() as cursor:
        # Check document ownership
        cursor.execute(
            """
            SELECT d.id
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            WHERE d.id = %s AND s.user_id = %s;
            """,
            (document_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied.",
            )

        # Update all linked topics
        cursor.execute(
            """
            UPDATE topics t
            SET reviewed = TRUE
            FROM topic_sources ts, chunks c
            WHERE t.id = ts.topic_id
              AND ts.chunk_id = c.id
              AND c.document_id = %s;
            """,
            (document_id,),
        )
        updated_count = cursor.rowcount

        return BulkReviewActionResponse(
            document_id=document_id,
            updated_count=updated_count,
            status="approved",
            message=f"All {updated_count} topics marked as reviewed.",
        )


@router.post("/documents/{document_id}/topics/skip", response_model=BulkReviewActionResponse)
async def skip_topic_review(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Skips the review step for this document.
    Topics remain with reviewed = FALSE and will carry an 'unreviewed' label.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            WHERE d.id = %s AND s.user_id = %s;
            """,
            (document_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied.",
            )

        # Count how many topics are in this document
        cursor.execute(
            """
            SELECT COUNT(DISTINCT t.id)
            FROM topics t
            JOIN topic_sources ts ON t.id = ts.topic_id
            JOIN chunks c ON ts.chunk_id = c.id
            WHERE c.document_id = %s;
            """,
            (document_id,),
        )
        count_row = cursor.fetchone()
        topic_count = count_row[0] if count_row else 0

        return BulkReviewActionResponse(
            document_id=document_id,
            updated_count=topic_count,
            status="skipped",
            message=f"Review skipped. {topic_count} topics remain marked as unreviewed.",
        )


@router.post("/documents/{document_id}/extract-topics")
async def trigger_document_topic_extraction(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    On-demand topic extraction for a document.
    Extracts academic topics from document chunks if not already extracted.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            WHERE d.id = %s AND s.user_id = %s;
            """,
            (document_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied.",
            )

    from backend.app.services.topic_extractor import topic_extractor_service
    batch_result = topic_extractor_service.process_document_topics(document_id)

    return {
        "document_id": document_id,
        "topics_created": batch_result.topics_created,
        "topics_rejected": batch_result.topics_rejected,
        "batches_processed": batch_result.batches_processed,
        "message": f"Extracted {batch_result.topics_created} topics successfully.",
    }

