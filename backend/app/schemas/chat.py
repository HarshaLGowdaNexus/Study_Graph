"""
Pydantic Schemas for StudyGraph Chatbot (Task T13).
Relies on:
  - Feature F14: Chatbot with citations + 'not in your notes' + labeled fallback.
  - Risk R10: Hallucination defense and honest answer grounding.
  - RULEBOOK 13.4: Chatbot honesty rules.
  - Data Model: chat_messages table (id, user_id, subject_id, role, text, citations_json, answered_from, created_at).
"""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class CitationItem(BaseModel):
    """
    Clickable citation reference pointing to an exact source document and page
    with verbatim supporting snippet.
    """
    document_id: str = Field(..., description="UUID of source document")
    filename: str = Field(..., description="File name of the uploaded lecture note or textbook")
    page: int = Field(..., description="1-based page number where the fact appears")
    snippet: str = Field(..., description="Verbatim text excerpt from the note supporting the answer")
    similarity: float = Field(0.0, description="Vector cosine similarity of retrieved chunk (0.0 to 1.0)")
    source_kind: Optional[str] = Field(None, description="Source kind used: 'notes' or 'textbook'")


class ChatAskRequest(BaseModel):
    """
    Student question payload.
    """
    question: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="The student's study question to ask the notes chatbot",
    )
    marks: Optional[Literal[2, 5, 10]] = Field(
        default=None,
        description="Optional exam mark target (2, 5, or 10) controlling answer length and structure (Feature F20)",
    )


class ChatAnswerResponse(BaseModel):
    """
    Assistant response containing honest answering mode, text, and citations.
    """
    id: str = Field(..., description="UUID of the persisted assistant chat message")
    subject_id: str = Field(..., description="UUID of the subject")
    role: Literal["assistant"] = "assistant"
    text: str = Field(..., description="The answer content")
    marks: Optional[Literal[2, 5, 10]] = Field(
        default=None,
        description="Exam mark format used (2, 5, or 10), if requested",
    )
    answered_from: Literal["notes", "general"] = Field(
        ...,
        description="'notes' if answered with confidence from notes; 'general' if flagged 'Not found in your notes'",
    )
    active_source_preference: Optional[Literal["notes", "textbook"]] = Field(
        default=None,
        description="Subject source preference ('notes' or 'textbook') active during retrieval",
    )
    confidence: float = Field(
        ...,
        description="Top retrieval cosine similarity score (0.0 to 1.0)",
    )
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="List of verified citations from the student's own notes",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when response was generated",
    )


class ChatMessageHistoryItem(BaseModel):
    """
    A single message in the conversation history.
    """
    id: str
    role: Literal["user", "assistant", "system"]
    text: str
    answered_from: Optional[Literal["notes", "general"]] = None
    citations: List[CitationItem] = Field(default_factory=list)
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """
    Complete chat history for a student's subject.
    """
    subject_id: str
    subject_name: str
    total_messages: int
    messages: List[ChatMessageHistoryItem]

