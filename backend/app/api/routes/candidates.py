"""
FastAPI Routes for Link Candidates (Task T08).
Relies on Decisions D04, D05, D10.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.candidate import (
    CandidateBatchResponse,
    CandidatePair,
    CandidateSearchParams,
)
from backend.app.services.candidate_finder import CandidateFinderService

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
candidate_service = CandidateFinderService()


@router.post(
    "/find",
    response_model=CandidateBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Find link candidate pairs using vector nearest neighbors",
)
def find_candidates(params: CandidateSearchParams):
    """
    Finds and optionally stores candidate pairs for new topics.
    Applies separate same-subject and cross-subject thresholds,
    skips pairs with deleted or locked edges, and enforces per-topic caps.
    """
    try:
        response = candidate_service.find_and_store_candidates(params)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/by-topic/{topic_id}",
    response_model=List[CandidatePair],
    summary="Get stored candidates for a specific topic",
)
def get_candidates_for_topic(
    topic_id: str,
    status_filter: str = Query("pending", pattern="^(pending|judged|dismissed)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """Retrieves candidates associated with a specific topic."""
    try:
        return candidate_service.get_stored_candidates(
            topic_id=topic_id,
            status=status_filter,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/pending",
    response_model=List[CandidatePair],
    summary="List all pending candidates awaiting LLM judging",
)
def get_pending_candidates(
    scope: Optional[str] = Query(None, pattern="^(same_subject|cross_subject)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists pending candidate pairs ready for the LLM judge step (T09)."""
    try:
        return candidate_service.get_stored_candidates(
            scope=scope,
            status="pending",
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
