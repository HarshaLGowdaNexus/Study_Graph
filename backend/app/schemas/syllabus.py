"""
Pydantic Schemas for Syllabus Ghost Nodes, Coverage/Gaps, and Source Preference (Task T18).
Relies on:
  - Feature F16: Ghost nodes from syllabus (coverage and gaps).
  - Feature F17: Notes vs textbook preference per subject.
  - Data Model: universities, schemes, syllabus_subjects, syllabus_topics, subjects.source_preference.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ExtractedSyllabusItem(BaseModel):
    module_no: int = Field(1, ge=1, le=20, description="1-based syllabus module/unit number")
    title: str = Field(..., min_length=2, max_length=200, description="Concise syllabus topic title")


class SyllabusExtractionOutput(BaseModel):
    detected_subject_code: Optional[str] = Field(None, description="Optional university course code if detected")
    topics: List[ExtractedSyllabusItem] = Field(default_factory=list)


class SyllabusMatchDecision(BaseModel):
    is_match: bool = Field(..., description="True if the note topic covers the syllabus topic")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = Field("", description="Short justification")


class SyllabusTextParseRequest(BaseModel):
    syllabus_text: str = Field(..., min_length=10, description="Raw syllabus text pasted by the student")
    university_name: str = Field(default="Default University", max_length=150)
    scheme_name: str = Field(default="2022 Scheme", max_length=120)
    subject_code: Optional[str] = Field(default=None, max_length=40)
    semester: Optional[int] = Field(default=None, ge=1, le=12)
    branch: Optional[str] = Field(default=None, max_length=100)


class MatchedTopicSummary(BaseModel):
    topic_id: str
    keyword: str
    module_no: Optional[int] = None
    syllabus_match_locked: bool = False


class SyllabusTopicItem(BaseModel):
    id: str
    syllabus_subject_id: str
    module_no: int = 1
    title: str
    parent_id: Optional[str] = None
    reviewed: bool = False
    is_covered: bool = False
    matched_topics: List[MatchedTopicSummary] = Field(default_factory=list)


class ModuleCoverageItem(BaseModel):
    module_no: int
    total_topics: int
    covered_count: int
    gap_count: int
    coverage_percent: float
    covered_titles: List[str] = Field(default_factory=list)
    gap_topics: List[SyllabusTopicItem] = Field(default_factory=list)


class SyllabusMetadata(BaseModel):
    syllabus_subject_id: Optional[str] = None
    university_id: Optional[str] = None
    university_name: Optional[str] = None
    scheme_id: Optional[str] = None
    scheme_name: Optional[str] = None
    subject_code: Optional[str] = None
    semester: Optional[int] = None
    branch: Optional[str] = None


class SubjectSyllabusResponse(BaseModel):
    subject_id: str
    subject_name: str
    source_preference: Literal["notes", "textbook"] = "notes"
    has_syllabus: bool = False
    metadata: Optional[SyllabusMetadata] = None
    total_syllabus_topics: int = 0
    covered_count: int = 0
    gap_count: int = 0
    coverage_percent: float = 0.0
    unreviewed_count: int = 0
    syllabus_topics: List[SyllabusTopicItem] = Field(default_factory=list)
    modules: List[ModuleCoverageItem] = Field(default_factory=list)
    gaps: List[SyllabusTopicItem] = Field(default_factory=list)


class SyllabusTopicUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    module_no: Optional[int] = Field(None, ge=1, le=20)


class SyllabusTopicCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    module_no: int = Field(1, ge=1, le=20)


class TopicMatchCorrectionRequest(BaseModel):
    syllabus_topic_id: Optional[str] = Field(
        None,
        description="Target syllabus_topic UUID to link, or null to unlink this topic from any syllabus ghost node",
    )


class MatchRunResponse(BaseModel):
    subject_id: str
    topics_evaluated: int
    matches_created: int
    coverage_percent: float


class SubjectPreferenceRequest(BaseModel):
    source_preference: Literal["notes", "textbook"]


class SubjectPreferenceResponse(BaseModel):
    subject_id: str
    subject_name: str
    source_preference: Literal["notes", "textbook"]
    message: str


class SyllabusReassignRequest(BaseModel):
    target_subject_id: str = Field(..., description="Subject UUID to move this syllabus to")

