"""
Deduplication and Embedding API Endpoints for StudyGraph (T07).
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.schemas.dedupe import (
    CandidatePair,
    DedupeRunResponse,
    ManualMergeRequest,
    ManualSplitRequest,
    MergeRecordResponse,
)
from backend.app.services.dedupe_service import DedupeService
from backend.app.services.embedding_service import EmbeddingService

router = APIRouter(prefix="/dedupe", tags=["dedupe"])


@router.post("/run/{subject_id}", response_model=DedupeRunResponse)
def run_deduplication(
    subject_id: UUID,
    threshold: Optional[float] = Query(
        None, ge=0.5, le=1.0, description="Optional override for similarity threshold (default 0.85)"
    ),
):
    """
    Runs automated deduplication for all topics in the given subject.
    1. Generates any missing embeddings.
    2. Finds same-subject topic pairs exceeding the similarity threshold.
    3. Confirms identity via Gemini Flash.
    4. Merges confirmed duplicates, records aliases, preserves evidence, and logs to topic_merges.
    """
    service = DedupeService()
    try:
        result = service.run_auto_deduplication(subject_id, custom_threshold=threshold)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deduplication run failed: {str(e)}",
        )


@router.get("/candidates/{subject_id}", response_model=List[CandidatePair])
def get_candidate_duplicates(
    subject_id: UUID,
    threshold: Optional[float] = Query(
        None, ge=0.5, le=1.0, description="Optional override for similarity threshold (default 0.85)"
    ),
):
    """
    Returns candidate duplicate pairs within a subject without executing merges.
    """
    service = DedupeService()
    try:
        # First ensure embeddings exist so search works
        service.embedding_service.embed_unembedded_topics(subject_id)
        candidates = service.find_candidate_pairs(subject_id, custom_threshold=threshold)
        return candidates
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find candidate duplicates: {str(e)}",
        )


@router.post("/merge")
def manual_merge_topics(payload: ManualMergeRequest):
    """
    Manually merges one topic into another.
    Transfers topic_sources, creates an alias, and records the action in topic_merges for undo.
    """
    service = DedupeService()
    try:
        surviving_id = UUID(payload.surviving_topic_id)
        merged_id = UUID(payload.merged_topic_id)
        result = service.merge_topics(
            surviving_topic_id=surviving_id,
            merged_topic_id=merged_id,
            merge_type="manual",
        )
        return {"status": "success", "result": result}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual merge failed: {str(e)}",
        )


@router.post("/split")
def manual_split_merge(payload: ManualSplitRequest):
    """
    Undoes a previous merge, restoring the merged topic, its sources, and removing its alias.
    """
    service = DedupeService()
    try:
        merge_id = UUID(payload.merge_id)
        result = service.split_merge(merge_id)
        return {"status": "success", "result": result}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Split failed: {str(e)}",
        )


@router.get("/history/{subject_id}", response_model=List[MergeRecordResponse])
def get_merge_history(subject_id: UUID):
    """
    Returns the complete merge history for a subject, including active and undone merges.
    """
    service = DedupeService()
    try:
        return service.list_merge_history(subject_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve merge history: {str(e)}",
        )


@router.post("/embed-chunks/{document_id}")
def embed_document_chunks(document_id: UUID):
    """
    Generates and stores embeddings for all chunks belonging to a document.
    """
    service = EmbeddingService()
    try:
        count = service.embed_unembedded_chunks(document_id)
        return {"status": "success", "chunks_embedded": count}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding chunks failed: {str(e)}",
        )

