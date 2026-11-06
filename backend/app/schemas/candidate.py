"""
Pydantic Schemas for Link Candidate Finder (Task T08).
Relies on Decisions D05, D10.
"""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class CandidatePair(BaseModel):
    """Represents a candidate pair of topics identified by embedding similarity."""
    id: Optional[str] = Field(None, description="UUID in link_candidates table if persisted")
    topic_a_id: str
    topic_a_keyword: str
    topic_a_explanation: str
    topic_a_subject_id: str
    topic_a_subject_name: Optional[str] = None

    topic_b_id: str
    topic_b_keyword: str
    topic_b_explanation: str
    topic_b_subject_id: str
    topic_b_subject_name: Optional[str] = None

    similarity: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score (0.0 - 1.0)")
    scope: Literal["same_subject", "cross_subject"]
    status: Literal["pending", "judged", "dismissed"] = "pending"
    created_at: Optional[datetime] = None


class CandidateSearchParams(BaseModel):
    """Parameters for running the candidate finder."""
    topic_ids: Optional[List[str]] = Field(None, description="Specific topic IDs to find candidates for")
    subject_id: Optional[str] = Field(None, description="Subject ID to find candidates for all topics within it")
    k_neighbors: Optional[int] = Field(None, ge=1, le=50, description="Max nearest neighbors per scope query")
    same_subject_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Cosine similarity threshold for same subject")
    cross_subject_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Cosine similarity threshold for cross subject")
    max_per_topic: Optional[int] = Field(None, ge=1, le=50, description="Cap on total candidates kept per topic")
    include_cross_subject: bool = Field(True, description="Whether to include cross-subject candidate search")
    persist: bool = Field(True, description="Whether to save candidate pairs into link_candidates table")


class CandidateFindResult(BaseModel):
    """Result of candidate search for a single focal topic."""
    topic_id: str
    topic_keyword: str
    subject_id: str
    same_subject_candidates: List[CandidatePair] = []
    cross_subject_candidates: List[CandidatePair] = []
    total_candidates: int = 0


class CandidateBatchResponse(BaseModel):
    """Response returned when evaluating candidates in batch."""
    total_topics_evaluated: int
    total_candidates_found: int
    total_candidates_stored: int
    same_subject_count: int
    cross_subject_count: int
    results: List[CandidateFindResult]

