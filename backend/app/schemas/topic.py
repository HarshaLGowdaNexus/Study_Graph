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

