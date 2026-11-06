"""
Pydantic schemas for Edges, Evidence, and LLM Link Judge (Task T09).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence)
  - docs/DATA_MODEL.md Table 13 (edges) & Table 14 (edge_evidence)
  - RULEBOOK.md Section 13.1 (No evidence, no link)
"""

from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

# Allowed Link Types per T09 specification
LinkType = Literal[
    "prerequisite_of",
    "same_concept",
    "example_of",
    "applies_in",
    "contrasts_with",
    "part_of",
]

EdgeScope = Literal["same_subject", "cross_subject"]
EdgeStatus = Literal["auto", "edited", "deleted"]
LLMVerdict = Literal["accept", "reject"]


class LLMJudgeRawOutput(BaseModel):
    """
    Schema for Gemini Flash structured response when evaluating a candidate pair.
    """
    verdict: LLMVerdict = Field(
        description="Whether to accept or reject this candidate link."
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Explanation if the candidate link is rejected."
    )
    type: Optional[LinkType] = Field(
        default=None,
        description="The specific academic relationship type."
    )
    reason: Optional[str] = Field(
        default=None,
        description="1-2 sentences explaining why these two topics connect."
    )
    industry_example: Optional[str] = Field(
        default=None,
        description="Real-world engineering or practical application example."
    )
    strength: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Relationship strength rated from 1 (incidental) to 5 (vital prerequisite)."
    )
    snippet_a: Optional[str] = Field(
        default=None,
        description="Verbatim text excerpt quoted directly from Topic A's notes."
    )
    chunk_id_a: Optional[str] = Field(
        default=None,
        description="UUID of the chunk containing snippet_a."
    )
    snippet_b: Optional[str] = Field(
        default=None,
        description="Verbatim text excerpt quoted directly from Topic B's notes."
    )
    chunk_id_b: Optional[str] = Field(
        default=None,
        description="UUID of the chunk containing snippet_b."
    )


class EdgeEvidenceCreate(BaseModel):
    """Schema for inserting a snippet proof into edge_evidence."""
    chunk_id: UUID
    snippet: str = Field(min_length=5, description="Verbatim quote from source chunk")


class EdgeEvidenceResponse(BaseModel):
    """Schema for returning evidence associated with an edge."""
    id: Optional[UUID] = None
    edge_id: UUID
    chunk_id: UUID
    snippet: str

    model_config = ConfigDict(from_attributes=True)


class EdgeCreate(BaseModel):
    """Schema for persisting an approved edge to the database."""
    topic_a: UUID
    topic_b: UUID
    type: LinkType
    reason: str
    industry_example: str
    strength: int = Field(ge=1, le=5)
    scope: EdgeScope
    status: EdgeStatus = "auto"
    locked: bool = False
    is_visible: bool = True
    graph_version: int = 1
    evidence: List[EdgeEvidenceCreate] = Field(
        min_length=2,
        max_length=2,
        description="Strictly two verified snippets (one for each topic side)"
    )


class EdgeResponse(BaseModel):
    """Schema for returning an edge with its evidence."""
    id: UUID
    topic_a: UUID
    topic_b: UUID
    type: LinkType
    reason: str
    industry_example: str
    strength: int
    scope: EdgeScope
    status: EdgeStatus
    locked: bool
    is_visible: bool
    graph_version: int
    evidence: List[EdgeEvidenceResponse] = []

    model_config = ConfigDict(from_attributes=True)


class JudgeCandidateResult(BaseModel):
    """Result of evaluating a single candidate pair."""
    candidate_id: Optional[UUID] = None
    topic_a_id: UUID
    topic_b_id: UUID
    topic_a_keyword: str
    topic_b_keyword: str
    verdict: LLMVerdict
    rejection_reason: Optional[str] = None
    edge_id: Optional[UUID] = None
    type: Optional[LinkType] = None
    strength: Optional[int] = None
    scope: EdgeScope
    is_visible: bool = True
    snippets_verified: bool = False
    verification_error: Optional[str] = None


class JudgeBatchResponse(BaseModel):
    """Response returned by batch candidate evaluation API."""
    total_evaluated: int
    edges_created: int
    candidates_rejected: int
    verification_failures: int
    results: List[JudgeCandidateResult]
    token_usage: dict
    estimated_cost_usd: float

