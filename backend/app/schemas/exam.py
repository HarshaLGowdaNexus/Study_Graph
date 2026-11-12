"""
Pydantic Schemas for Exam Mode (Task T17).
Relies on:
  - Feature F18: Important concepts list ('by graph importance').
  - Feature F19: Repeated questions from uploaded papers ('from your uploaded papers').
  - Risk R05: Never fabricate repeated questions when no papers exist.
  - Data Model: exam_papers & exam_questions tables.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedQuestionItem(BaseModel):
    """Single question extracted by Gemini from an uploaded question paper."""
    text: str = Field(..., min_length=5, description="Cleaned text of the exam question")
    marks: Optional[int] = Field(None, ge=1, le=100, description="Marks weight if stated on the paper")


class PaperExtractionOutput(BaseModel):
    """Structured output schema for LLM exam-paper question parsing."""
    detected_year: Optional[int] = Field(None, ge=1990, le=2100)
    questions: List[ExtractedQuestionItem] = Field(default_factory=list)


class QuestionPairJudgement(BaseModel):
    """Structured output schema for LLM confirmation of similar exam questions."""
    is_same_question: bool
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    canonical_question: str = ""
    reason: str = ""


class ImportantConceptItem(BaseModel):
    """
    A topic ranked by graph connectivity (degree + weighted edge strength + centrality)
    and module/source coverage, honestly labeled 'by graph importance'.
    """
    topic_id: str
    keyword: str
    explanation: str
    real_world_use: Optional[str] = None
    module_no: Optional[int] = None
    reviewed: bool = False
    importance_score: float = Field(..., ge=0.0, le=1.0)
    degree: int = Field(0, ge=0)
    weighted_degree: int = Field(0, ge=0)
    modules_covered: int = Field(1, ge=0)
    source_count: int = Field(0, ge=0)
    cross_subject_links: int = Field(0, ge=0)
    label: str = "by graph importance"


class ExamPaperItem(BaseModel):
    """Metadata for an uploaded previous-year paper in a subject."""
    id: str
    document_id: str
    filename: str
    year: Optional[int] = None
    status: str
    question_count: int = 0
    uploaded_at: Optional[str] = None


class QuestionOccurrenceItem(BaseModel):
    """One concrete occurrence of a question inside a specific uploaded paper."""
    question_id: str
    paper_id: str
    filename: str
    year: Optional[int] = None
    text: str
    marks: Optional[int] = None


class RepeatedQuestionCluster(BaseModel):
    """
    A cluster of semantically matching questions across uploaded papers,
    counting how many distinct papers contain the question.
    """
    cluster_key: str
    canonical_question: str
    repeat_count: int = Field(..., ge=1, description="Number of distinct uploaded papers containing this question")
    total_papers: int = Field(..., ge=1)
    typical_marks: Optional[int] = None
    matched_topic_id: Optional[str] = None
    matched_topic_keyword: Optional[str] = None
    label: str = "from your uploaded papers"
    occurrences: List[QuestionOccurrenceItem] = Field(default_factory=list)


class ExamOverviewResponse(BaseModel):
    """Complete Exam Mode payload for a single subject."""
    subject_id: str
    subject_name: str
    important_concepts_label: str = "by graph importance"
    important_concepts: List[ImportantConceptItem] = Field(default_factory=list)
    repeated_questions_label: str = "from your uploaded papers"
    has_uploaded_papers: bool = False
    total_papers: int = 0
    total_questions: int = 0
    honest_notice: Optional[str] = None
    papers: List[ExamPaperItem] = Field(default_factory=list)
    repeated_questions: List[RepeatedQuestionCluster] = Field(default_factory=list)


class PaperUploadResponse(BaseModel):
    """Response returned after uploading a previous-year question paper."""
    paper_id: str
    document_id: str
    filename: str
    year: Optional[int] = None
    status: str
    questions_extracted: int = 0
    message: str


class PaperDeleteResponse(BaseModel):
    """Response returned after deleting an uploaded paper."""
    status: str
    paper_id: str
    document_id: str
    remaining_papers: int
    message: str

