"""
Syllabus Ghost Nodes, Coverage/Gap & Source Preference API Routes (Task T18).
Relies on:
  - Feature F16: Ghost nodes from syllabus (coverage and gaps).
  - Feature F17: Notes vs textbook preference per subject.
  - RULEBOOK Rule 11: Multi-user privacy isolation on all routes.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.core.config import settings
from backend.app.schemas.syllabus import (
    MatchRunResponse,
    SubjectPreferenceRequest,
    SubjectPreferenceResponse,
    SubjectSyllabusResponse,
    SyllabusReassignRequest,
    SyllabusTextParseRequest,
    SyllabusTopicCreateRequest,
    SyllabusTopicItem,
    SyllabusTopicUpdateRequest,
    TopicMatchCorrectionRequest,
)
from backend.app.services.syllabus_service import syllabus_service

router = APIRouter(prefix="/subjects", tags=["Syllabus & Source Preference"])


@router.get(
    "/{subject_id}/syllabus",
    response_model=SubjectSyllabusResponse,
    summary="Get syllabus ghost nodes, per-module coverage, and uncovered gaps",
)
def get_subject_syllabus(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.get_subject_syllabus(user_id=current_user.id, subject_id=subject_id)


@router.post(
    "/{subject_id}/syllabus/parse-text",
    response_model=SubjectSyllabusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Parse pasted syllabus text into syllabus_topics for review and ghost nodes",
)
def parse_syllabus_text(
    subject_id: str,
    payload: SyllabusTextParseRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.ingest_syllabus_text(
        user_id=current_user.id,
        subject_id=subject_id,
        syllabus_text=payload.syllabus_text,
        university_name=payload.university_name,
        scheme_name=payload.scheme_name,
        subject_code=payload.subject_code,
        semester=payload.semester,
        branch=payload.branch,
    )


@router.post(
    "/{subject_id}/syllabus/upload",
    response_model=SubjectSyllabusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a syllabus PDF/image/PPTX and parse it into syllabus_topics",
)
async def upload_syllabus_file(
    subject_id: str,
    file: UploadFile = File(...),
    university_name: str = Form("Default University"),
    scheme_name: str = Form("2022 Scheme"),
    subject_code: Optional[str] = Form(None),
    semester: Optional[int] = Form(None),
    branch: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    filename = file.filename or "syllabus.pdf"
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported syllabus file format '{ext}'. Please upload PDF, PPT/PPTX, or PNG/JPG.",
        )
    file_bytes = await file.read()
    return syllabus_service.ingest_syllabus_file(
        user_id=current_user.id,
        subject_id=subject_id,
        file_bytes=file_bytes,
        filename=filename,
        university_name=university_name,
        scheme_name=scheme_name,
        subject_code=subject_code,
        semester=semester,
        branch=branch,
    )


@router.patch(
    "/{subject_id}/syllabus/topics/{syllabus_topic_id}",
    response_model=SyllabusTopicItem,
    summary="Edit a parsed syllabus topic during review",
)
def update_syllabus_topic(
    subject_id: str,
    syllabus_topic_id: str,
    payload: SyllabusTopicUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.update_syllabus_topic(
        user_id=current_user.id,
        subject_id=subject_id,
        syllabus_topic_id=syllabus_topic_id,
        title=payload.title,
        module_no=payload.module_no,
    )


@router.post(
    "/{subject_id}/syllabus/topics",
    response_model=SyllabusTopicItem,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a syllabus topic during review",
)
def add_syllabus_topic(
    subject_id: str,
    payload: SyllabusTopicCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.add_syllabus_topic(
        user_id=current_user.id,
        subject_id=subject_id,
        title=payload.title,
        module_no=payload.module_no,
    )


@router.delete(
    "/{subject_id}/syllabus/topics/{syllabus_topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an unwanted syllabus topic during review",
)
def delete_syllabus_topic(
    subject_id: str,
    syllabus_topic_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    syllabus_service.delete_syllabus_topic(
        user_id=current_user.id,
        subject_id=subject_id,
        syllabus_topic_id=syllabus_topic_id,
    )


@router.post(
    "/{subject_id}/syllabus/approve-all",
    response_model=SubjectSyllabusResponse,
    summary="Approve all parsed syllabus topics",
)
def approve_all_syllabus(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.approve_all_syllabus_topics(user_id=current_user.id, subject_id=subject_id)


@router.post(
    "/{subject_id}/syllabus/skip",
    response_model=SubjectSyllabusResponse,
    summary="Skip syllabus review step without blocking workflow",
)
def skip_syllabus_review(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.get_subject_syllabus(user_id=current_user.id, subject_id=subject_id)


@router.post(
    "/{subject_id}/syllabus/match",
    response_model=MatchRunResponse,
    summary="Run embedding + LLM confirmation matching between note topics and syllabus ghost nodes",
)
def run_syllabus_matching(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.match_subject_topics(subject_id=subject_id, user_id=current_user.id)


@router.patch(
    "/{subject_id}/syllabus/matches/{topic_id}",
    response_model=SubjectSyllabusResponse,
    summary="Manually correct or unlink a topic's syllabus match (locks against auto-overwrite)",
)
def correct_topic_syllabus_match(
    subject_id: str,
    topic_id: str,
    payload: TopicMatchCorrectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.correct_topic_match(
        user_id=current_user.id,
        subject_id=subject_id,
        topic_id=topic_id,
        syllabus_topic_id=payload.syllabus_topic_id,
    )


@router.patch(
    "/{subject_id}/preference",
    response_model=SubjectPreferenceResponse,
    summary="Set per-subject source preference ('notes' or 'textbook')",
)
def update_subject_source_preference(
    subject_id: str,
    payload: SubjectPreferenceRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.update_source_preference(
        user_id=current_user.id,
        subject_id=subject_id,
        source_preference=payload.source_preference,
    )


@router.post(
    "/{subject_id}/syllabus/reassign",
    response_model=SubjectSyllabusResponse,
    summary="Move an uploaded syllabus from this subject to another subject owned by the student",
)
def reassign_subject_syllabus(
    subject_id: str,
    payload: SyllabusReassignRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.reassign_syllabus(
        user_id=current_user.id,
        from_subject_id=subject_id,
        target_subject_id=payload.target_subject_id,
    )


@router.delete(
    "/{subject_id}/syllabus",
    status_code=status.HTTP_200_OK,
    summary="Unlink and remove the syllabus from a subject",
)
def delete_subject_syllabus(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return syllabus_service.delete_syllabus(
        user_id=current_user.id,
        subject_id=subject_id,
    )

