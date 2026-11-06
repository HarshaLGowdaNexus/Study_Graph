"""
Pydantic Schemas for Duplicate Topic Detection, Merging, and Splitting (T07).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class DedupeJudgeDecision(BaseModel):
    """Structured response from the LLM duplicate confirmation step."""
    is_duplicate: bool = Field(description="Whether the two topics represent the exact same concept.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    reason: str = Field(description="Explanation of why they are identical or how they differ.")
    canonical_keyword: Optional[str] = Field(default=None, description="Preferred standard academic name.")


class CandidatePair(BaseModel):
    """A pair of same-subject topics flagged by vector similarity."""
    topic_a_id: str
    topic_a_keyword: str
    topic_a_explanation: str
    topic_b_id: str
    topic_b_keyword: str
    topic_b_explanation: str
    similarity: float


class ManualMergeRequest(BaseModel):
    """Request payload for manual student merge."""
    surviving_topic_id: str
    merged_topic_id: str
    reason: Optional[str] = "Manual student merge"


class ManualSplitRequest(BaseModel):
    """Request payload to split (undo) a previously executed merge."""
    merge_id: str


class MergeRecordResponse(BaseModel):
    """Audit record of a merge."""
    id: str
    subject_id: str
    surviving_topic_id: str
    surviving_keyword: Optional[str] = None
    merged_topic_id: str
    merged_keyword: str
    merged_explanation: str
    similarity_score: Optional[float] = None
    merge_type: str
    transferred_chunk_ids: List[str] = []
    created_at: str
    undone_at: Optional[str] = None


class DedupeRunResponse(BaseModel):
    """Summary of an automated deduplication run."""
    subject_id: str
    candidates_found: int
    merges_executed: int
    merged_pairs: List[Dict[str, Any]]
    duration_seconds: float

