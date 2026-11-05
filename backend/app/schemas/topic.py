"""
Pydantic schemas for Topic Extraction (T05).
Relies on:
  - Decision D09: Google Gemini Flash structured JSON output.
  - RULEBOOK Section 13:
      - Rule 1: No evidence, no link/topic (source chunk IDs strictly required).
      - Rule 3: Topic cards are short (keyword plus at most 4 lines, plus real-world use).
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class TopicExtractionItem(BaseModel):
    """
    Individual topic card extracted from lecture chunks.
    Strictly constrained by Rulebook Rule 3 (at most 4 lines explanation).
    """
    keyword: str = Field(
        ...,
        description="Concise academic title of the concept (1-5 words, e.g. 'Virtual Memory').",
    )
    explanation: str = Field(
        ...,
        description="At most 4 lines explaining what the concept is and how it works.",
    )
    real_world_use: Optional[str] = Field(
        default=None,
        description="One sentence describing an industry or practical real-world application.",
    )
    source_chunk_ids: List[str] = Field(
        ...,
        description="List of UUID strings of the source chunks providing evidence for this topic.",
    )

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Topic keyword cannot be empty.")
        return clean

    @field_validator("explanation")
    @classmethod
    def validate_explanation_lines(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Topic explanation cannot be empty.")

        # Count lines explicitly (separated by newlines)
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        if len(lines) > 4:
            raise ValueError(
                f"Topic explanation exceeds 4 lines (found {len(lines)} lines). "
                "Rulebook Section 13 Rule 3 mandates at most 4 lines."
            )
        return clean

    @field_validator("source_chunk_ids")
    @classmethod
    def validate_source_chunks(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Topic must cite at least one valid source chunk ID (Rulebook Rule 1).")
        # Ensure all items are non-empty strings
        clean_ids = [str(item).strip() for item in v if str(item).strip()]
        if not clean_ids:
            raise ValueError("source_chunk_ids contained only empty or invalid identifiers.")
        return clean_ids


class TopicExtractionResponse(BaseModel):
    """
    Root container for the LLM's structured JSON output.
    """
    topics: List[TopicExtractionItem] = Field(
        default_factory=list,
        description="List of extracted topic cards, or empty if no academic concepts were present.",
    )


# ------------------------------------------------------------------------------
# Schemas for T06: Topic Review Screen
# ------------------------------------------------------------------------------
class TopicUpdateRequest(BaseModel):
    """
    Payload for updating an individual topic's content or review state (T06).
    """
    keyword: Optional[str] = Field(
        default=None,
        description="Updated academic concept name.",
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Updated concept explanation (strictly at most 4 lines).",
    )
    real_world_use: Optional[str] = Field(
        default=None,
        description="Updated industry/practical application.",
    )
    reviewed: Optional[bool] = Field(
        default=None,
        description="Whether the topic has been reviewed and approved by the student.",
    )

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Keyword cannot be empty.")
            return clean
        return v

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("Explanation cannot be empty.")
            lines = [line.strip() for line in clean.splitlines() if line.strip()]
            if len(lines) > 4:
                raise ValueError(
                    f"Topic explanation exceeds 4 lines (found {len(lines)} lines). "
                    "Rulebook Section 13 Rule 3 mandates at most 4 lines."
                )
            if len(clean) > 1000:
                raise ValueError("Topic explanation exceeds maximum character length of 1000.")
            return clean
        return v


class TopicReviewItem(BaseModel):
    """
    Topic card representation formatted for the Student Review Screen (T06).
    """
    id: str
    subject_id: str
    keyword: str
    explanation: str
    real_world_use: Optional[str] = None
    module_no: Optional[int] = None
    reviewed: bool = False
    source_pages: List[int] = Field(default_factory=list)
    chunk_count: int = 0


class TopicListResponse(BaseModel):
    """
    List of topics associated with an uploaded document for student review.
    """
    document_id: str
    filename: str
    subject_id: str
    subject_name: str
    topics: List[TopicReviewItem]
    total_count: int
    reviewed_count: int
    unreviewed_count: int


class BulkReviewActionResponse(BaseModel):
    """
    Response returned after bulk approving or skipping review for a document.
    """
    document_id: str
    updated_count: int
    status: str  # "approved" | "skipped"
    message: str


