"""
Pydantic schemas for Edge Editing, Soft Deletion, and Manual Creation (Task T10).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence)
  - RULEBOOK.md Section 13 Rule 2: User edits are sacred (locked and never overwritten).
  - Risk R16: New uploads overwrite corrected links (prevented by user locks).
"""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.edge import EdgeEvidenceResponse, EdgeScope, EdgeStatus, LinkType


class EdgeUpdate(BaseModel):
    """
    Schema for editing an existing edge.
    Modifying any property locks the edge (locked = True) and sets status = 'edited'.
    """
    type: Optional[LinkType] = Field(None, description="Updated relationship type")
    reason: Optional[str] = Field(None, min_length=3, description="Updated reason why topics connect")
    industry_example: Optional[str] = Field(None, min_length=3, description="Updated real-world example")
    strength: Optional[int] = Field(None, ge=1, le=5, description="Updated relationship strength (1-5)")
    is_visible: Optional[bool] = Field(None, description="Manual visibility override")


class EdgeManualCreate(BaseModel):
    """
    Schema for a student manually creating a link between two topics.
    Automatically marked locked = True and status = 'edited'.
    Evidence snippets are optional; if provided, they are labeled 'manual'.
    """
    topic_a: UUID = Field(description="First topic UUID")
    topic_b: UUID = Field(description="Second topic UUID")
    type: LinkType = Field(description="Relationship type")
    reason: str = Field(min_length=3, description="Explanation for why these two topics connect")
    industry_example: Optional[str] = Field(
        default="Practical application",
        description="Real-world engineering or practical application example"
    )
    strength: int = Field(default=3, ge=1, le=5, description="Link strength 1-5")
    is_visible: bool = Field(default=True, description="Whether this edge is visible in graph")
    snippet_a: Optional[str] = Field(
        default=None,
        description="Optional manual snippet or note supporting Topic A"
    )
    snippet_b: Optional[str] = Field(
        default=None,
        description="Optional manual snippet or note supporting Topic B"
    )


class EdgeDetailResponse(BaseModel):
    """
    Rich response for graph edges including topic keywords and lock details.
    """
    id: UUID
    topic_a: UUID
    topic_b: UUID
    topic_a_keyword: str
    topic_b_keyword: str
    topic_a_subject_name: Optional[str] = None
    topic_b_subject_name: Optional[str] = None
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


class EdgeActionResponse(BaseModel):
    """Simple confirmation response for edge mutations."""
    success: bool
    message: str
    edge_id: UUID
    status: EdgeStatus
    locked: bool

