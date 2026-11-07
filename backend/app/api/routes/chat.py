"""
Chat API Routes for StudyGraph (Task T13).
Relies on:
  - Feature F14: Chatbot with citations + 'not in your notes' + labeled fallback.
  - Risk R10: Anti-hallucination defense and honest answer grounding.
  - Risk R11: Multi-user privacy isolation (students only chat within their own subjects).
  - Decision D04: Python with FastAPI.
  - Decision D09: Google Gemini Flash.
  - Decision D10: Google text-embedding-004.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.schemas.chat import (
    ChatAnswerResponse,
    ChatAskRequest,
    ChatHistoryResponse,
)
from backend.app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects", tags=["Chat"])


@router.post(
    "/{subject_id}/chat",
    response_model=ChatAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a study question grounded in the student's notes with exact citations",
)
def ask_chat_question(
    subject_id: str,
    request: ChatAskRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Asks a question to the subject study assistant.
    The chatbot:
    1. Embeds the question.
    2. Searches the student's own lecture notes and textbooks using pgvector.
    3. Calculates retrieval confidence.
    4. If confidence is high and notes contain the answer:
       Answers strictly from notes with exact file and page citations.
    5. If confidence is low or notes do not contain the answer:
       Refuses to bluff, returns 'Not found in your notes', and provides a clearly labeled
       general-knowledge fallback.
    6. Stores the interaction in the chat_messages audit history.
    """
    logger.info(
        f"[Chat API] User {current_user.id} asking question in subject {subject_id}: '{request.question[:60]}...'"
    )
    service = ChatService()
    return service.ask_question(
        user_id=current_user.id,
        subject_id=subject_id,
        question=request.question,
    )


@router.get(
    "/{subject_id}/chat/history",
    response_model=ChatHistoryResponse,
    summary="Get conversation history for a student's subject",
)
def get_chat_history(
    subject_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieves past chat messages, answers, and clickable citations for a subject.
    Enforces Rule 11 (Privacy): Only the owning student can view their chat history.
    """
    service = ChatService()
    return service.get_history(
        user_id=current_user.id,
        subject_id=subject_id,
        limit=limit,
    )


@router.delete(
    "/{subject_id}/chat/history",
    status_code=status.HTTP_200_OK,
    summary="Clear conversation history for a student's subject (Start New Chat)",
)
def clear_chat_history(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Clears all saved conversation messages for a subject, starting a fresh chat session.
    Enforces Rule 11 (Privacy): Only deletes chat messages belonging to the authenticated student.
    """
    service = ChatService()
    deleted_count = service.clear_history(
        user_id=current_user.id,
        subject_id=subject_id,
    )
    return {
        "status": "cleared",
        "subject_id": subject_id,
        "deleted_messages": deleted_count,
        "message": "Chat history cleared successfully. Starting a fresh chat.",
    }

