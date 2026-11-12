"""
Pydantic Schemas for Theory View (Task T12).
Relies on:
  - Feature F10: Theory view per subject with cross-module link chips.
  - Risk R04: UX grounded in bite-sized cards and navigable links.
  - RULEBOOK Section 13 Rule 3: Topic cards are short (keyword + max 4-line explanation + real-world use).
  - RULEBOOK Section 13 Rule 8: Weak links hidden by default.
  - RULEBOOK Section 13 Rule 9: Visible 'unreviewed' markings.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class TheoryLinkChip(BaseModel):
    """Represents a navigable relationship chip connected to another topic."""
    edge_id: str
    target_topic_id: str
    target_keyword: str
    target_module_no: int = 1
    target_subject_name: Optional[str] = None
    type: str = Field(..., description="Link type: prerequisite_of, applies_in, example_of, etc.")
    reason: str = Field(..., description="One-line academic reason for the link")
    industry_example: Optional[str] = None
    strength: int = Field(..., ge=1, le=5, description="Link strength 1-5")
    is_cross_module: bool = Field(False, description="True if link crosses module boundaries")
    is_cross_subject: bool = Field(False, description="True if link crosses subject boundaries")
    is_weak: bool = Field(False, description="True if strength < 3 (hidden by default)")
    direction: str = Field("outgoing", description="outgoing or incoming relative to this topic")


class TheorySourceCitation(BaseModel):
    """Source document citation attached to a theory card (Feature F17)."""
    filename: str
    page: int = 1
    source_kind: str = "notes"


class TheoryTopicCard(BaseModel):
    """Bite-sized revision card for a single academic topic."""
    id: str
    subject_id: str
    keyword: str
    explanation: str
    real_world_use: Optional[str] = None
    module_no: int = 1
    reviewed: bool = False
    cluster_label: Optional[str] = None
    active_source_kind: Optional[str] = Field(None, description="Source kind used for this card: 'notes' or 'textbook'")
    has_multiple_sources: bool = Field(False, description="True if both notes and textbook cover this topic")
    source_citations: List[TheorySourceCitation] = Field(default_factory=list)
    syllabus_topic_id: Optional[str] = None
    syllabus_title: Optional[str] = None
    syllabus_match_locked: bool = False
    links: List[TheoryLinkChip] = Field(default_factory=list)


class TheoryModuleGroup(BaseModel):
    """Collection of topic cards belonging to a single syllabus module."""
    module_no: int
    module_title: str
    topic_count: int
    topics: List[TheoryTopicCard] = Field(default_factory=list)


class SubjectTheoryResponse(BaseModel):
    """Full hierarchical theory view response for a chosen subject."""
    subject_id: str
    subject_name: str
    source_preference: str = "notes"
    total_topics: int
    total_links: int
    unreviewed_count: int
    modules: List[TheoryModuleGroup] = Field(default_factory=list)

