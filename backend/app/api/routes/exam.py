"""
Exam Mode API Routes for StudyGraph (Task T17).
Relies on:
  - Feature F18: Important concepts list ('by graph importance').
  - Feature F19: Repeated questions from uploaded papers ('from your uploaded papers').
  - Risk R05: Honest empty state when no papers are uploaded.
  - Rule 11: Multi-user privacy isolation.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.schemas.exam import (
    ExamOverviewResponse,
    PaperDeleteResponse,
    PaperUploadResponse,
)
from backend.app.services.exam_service import exam_service
from backend.app.services.job_worker import process_document_job
from backend.app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects", tags=["Exam Mode"])


@router.get(
    "/{subject_id}/exam/overview",
    response_model=ExamOverviewResponse,
    summary="Get Exam Mode important concepts and repeated questions for a subject",
)
def get_exam_overview(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Returns:
      1. Important concepts ranked by graph connectivity & coverage ('by graph importance').
      2. Uploaded previous-year papers & repeated question clusters ('from your uploaded papers').
      3. An honest notice when no papers exist (Risk R05).
    """
    return exam_service.get_exam_overview(subject_id=subject_id, user_id=current_user.id)


@router.post(
    "/{subject_id}/exam/papers",
    response_model=PaperUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a previous-year question paper for repeated-question analysis",
)
async def upload_exam_paper(
    subject_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    year: Optional[int] = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Uploads a previous-year question paper (PDF, PPT/PPTX, or image), creates the
    documents (source_kind='paper') and exam_papers rows, and queues background extraction
    & question clustering.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;",
            (subject_id, current_user.id),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or you do not have permission to access it.",
            )

    filename = file.filename or "exam_paper.pdf"
    file_ext = Path(filename).suffix.lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file format '{file_ext}'. "
                "Please upload question papers in PDF, PowerPoint (.ppt, .pptx), or image (.png, .jpg) format."
            ),
        )

    file_bytes = await file.read()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size ({file_size_mb:.1f} MB) exceeds the {settings.MAX_FILE_SIZE_MB} MB limit.",
        )

    storage_subpath = f"{current_user.id}/{subject_id}/papers/{filename}"
    saved_storage_path = await storage_service.upload_file(
        file_bytes=file_bytes,
        storage_path=storage_subpath,
        content_type=file.content_type or "application/octet-stream",
    )

    file_type = file_ext.lstrip(".")
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO documents (subject_id, module_no, filename, type, source_kind, status, storage_path)
            VALUES (%s, NULL, %s, %s, 'paper', 'queued', %s)
            RETURNING id;
            """,
            (subject_id, filename, file_type, saved_storage_path),
        )
        doc_id = str(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO exam_papers (subject_id, year, document_id)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (subject_id, year, doc_id),
        )
        paper_id = str(cursor.fetchone()[0])

    background_tasks.add_task(process_document_job, doc_id, current_user.id)

    return PaperUploadResponse(
        paper_id=paper_id,
        document_id=doc_id,
        filename=filename,
        year=year,
        status="queued",
        questions_extracted=0,
        message="Previous-year paper uploaded and queued for question extraction.",
    )


@router.delete(
    "/{subject_id}/exam/papers/{paper_id}",
    response_model=PaperDeleteResponse,
    summary="Remove an uploaded previous-year paper and recalculate repeat counts",
)
async def delete_exam_paper(
    subject_id: str,
    paper_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Removes an uploaded paper, deletes its stored file and parsed questions,
    and updates repeat counts across remaining papers.
    """
    resp, storage_path = exam_service.delete_paper(
        subject_id=subject_id,
        paper_id=paper_id,
        user_id=current_user.id,
    )
    if storage_path:
        await storage_service.delete_file(storage_path)
    return resp

