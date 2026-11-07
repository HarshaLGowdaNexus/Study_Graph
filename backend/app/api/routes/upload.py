"""
Upload and Document Status API Routes for StudyGraph.
Handles file validation, Supabase cloud storage, database tracking, and background jobs.
Enforces Rule 11 (Privacy): All queries and storage paths strictly belong to the authenticated student.
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, BackgroundTasks
from pydantic import BaseModel
import psycopg2.extras

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.services.job_worker import process_document_job
from backend.app.services.storage import storage_service

router = APIRouter()


# ------------------------------------------------------------------------------
# Pydantic Response & Request Models
# ------------------------------------------------------------------------------
class SubjectCreate(BaseModel):
    name: str
    source_preference: Optional[str] = "notes"


class SubjectResponse(BaseModel):
    id: str
    name: str
    source_preference: str


class DocumentStatusResponse(BaseModel):
    id: str
    filename: str
    status: str
    module_no: Optional[int] = None
    error_message: Optional[str] = None
    storage_path: Optional[str] = None
    uploaded_at: Optional[str] = None
    summary: Optional[str] = None
    topic_count: int = 0
    unreviewed_count: int = 0


class UploadResponse(BaseModel):
    id: str
    filename: str
    status: str
    module_no: int
    storage_path: str
    message: str


# ------------------------------------------------------------------------------
# Subject Endpoints
# ------------------------------------------------------------------------------
@router.get("/subjects", response_model=List[SubjectResponse])
async def list_subjects(current_user: CurrentUser = Depends(get_current_user)):
    """
    Lists all subjects belonging to the authenticated student.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, name, source_preference 
            FROM subjects 
            WHERE user_id = %s 
            ORDER BY name ASC;
            """,
            (current_user.id,),
        )
        rows = cursor.fetchall()
        return [
            SubjectResponse(id=str(row[0]), name=row[1], source_preference=row[2])
            for row in rows
        ]


@router.post("/subjects", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    payload: SubjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Creates a new subject folder for the authenticated student.
    """
    pref = payload.source_preference if payload.source_preference in ("notes", "textbook") else "notes"
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO subjects (user_id, name, source_preference)
            VALUES (%s, %s, %s)
            RETURNING id, name, source_preference;
            """,
            (current_user.id, payload.name.strip(), pref),
        )
        row = cursor.fetchone()
        return SubjectResponse(id=str(row[0]), name=row[1], source_preference=row[2])


# ------------------------------------------------------------------------------
# Upload & Status Endpoints
# ------------------------------------------------------------------------------
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_200_OK)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    subject_id: str = Form(...),
    module_no: int = Form(1),
    source_kind: str = Form("notes"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Validates uploaded notes, saves file into cloud storage,
    records a queued document in PostgreSQL, and starts the background job.
    """
    # 1. Verify subject belongs to the current user (Privacy rule)
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;",
            (subject_id, current_user.id),
        )
        subject_row = cursor.fetchone()
        if not subject_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or you do not have permission to access it.",
            )

    # 2. Validate file extension (Friendly rejection rule)
    filename = file.filename or "uploaded_file"
    file_ext = Path(filename).suffix.lower()

    if file_ext not in settings.ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(settings.ALLOWED_EXTENSIONS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file format '{file_ext}'. "
                f"Please upload lecture notes in PDF, PowerPoint (.ppt, .pptx), or image (.png, .jpg) format."
            ),
        )

    # 3. Read and check file size (Max file size rule)
    file_bytes = await file.read()
    file_size_mb = len(file_bytes) / (1024 * 1024)

    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"The uploaded file is {file_size_mb:.1f} MB, which exceeds the {settings.MAX_FILE_SIZE_MB} MB limit. "
                "Please compress the file or choose a smaller chapter."
            ),
        )

    # 4. Upload file to Supabase Storage
    # Path isolated by user_id to enforce multi-tenant separation in cloud storage
    storage_subpath = f"{current_user.id}/{subject_id}/module_{module_no}/{filename}"
    saved_storage_path = await storage_service.upload_file(
        file_bytes=file_bytes,
        storage_path=storage_subpath,
        content_type=file.content_type or "application/octet-stream",
    )

    # 5. Insert document row into PostgreSQL
    file_type = file_ext.lstrip(".")
    valid_source_kind = source_kind if source_kind in ("notes", "textbook", "paper") else "notes"

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO documents (subject_id, module_no, filename, type, source_kind, status, storage_path)
            VALUES (%s, %s, %s, %s, %s, 'queued', %s)
            RETURNING id;
            """,
            (subject_id, module_no, filename, file_type, valid_source_kind, saved_storage_path),
        )
        doc_id = str(cursor.fetchone()[0])

    # 6. Queue background job (FastAPI BackgroundTasks)
    background_tasks.add_task(process_document_job, doc_id, current_user.id)

    return UploadResponse(
        id=doc_id,
        filename=filename,
        status="queued",
        module_no=module_no,
        storage_path=saved_storage_path,
        message="File uploaded successfully and queued for processing.",
    )


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Exposes document status for real-time frontend polling.
    Enforces privacy: Student can only view documents in subjects they own.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT 
                d.id, 
                d.filename, 
                d.status, 
                d.module_no, 
                d.error_message, 
                d.storage_path, 
                d.uploaded_at,
                d.summary,
                COUNT(DISTINCT ts.topic_id) as topic_count,
                COUNT(DISTINCT CASE WHEN t.reviewed = FALSE THEN t.id END) as unreviewed_count
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            LEFT JOIN chunks c ON c.document_id = d.id
            LEFT JOIN topic_sources ts ON ts.chunk_id = c.id
            LEFT JOIN topics t ON t.id = ts.topic_id
            WHERE d.id = %s AND s.user_id = %s
            GROUP BY d.id, d.filename, d.status, d.module_no, d.error_message, d.storage_path, d.uploaded_at, d.summary;
            """,
            (document_id, current_user.id),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or you do not have permission to view it.",
            )

        return DocumentStatusResponse(
            id=str(row[0]),
            filename=row[1],
            status=row[2],
            module_no=row[3],
            error_message=row[4],
            storage_path=row[5],
            uploaded_at=str(row[6]) if row[6] else None,
            summary=row[7],
            topic_count=row[8] or 0,
            unreviewed_count=row[9] or 0,
        )


@router.get("/subjects/{subject_id}/documents", response_model=List[DocumentStatusResponse])
async def list_subject_documents(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Lists all documents inside a specific subject folder owned by the student.
    Includes live topic and review counts.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT 
                d.id, 
                d.filename, 
                d.status, 
                d.module_no, 
                d.error_message, 
                d.storage_path, 
                d.uploaded_at,
                d.summary,
                COUNT(DISTINCT ts.topic_id) as topic_count,
                COUNT(DISTINCT CASE WHEN t.reviewed = FALSE THEN t.id END) as unreviewed_count
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            LEFT JOIN chunks c ON c.document_id = d.id
            LEFT JOIN topic_sources ts ON ts.chunk_id = c.id
            LEFT JOIN topics t ON t.id = ts.topic_id
            WHERE s.id = %s AND s.user_id = %s
            GROUP BY d.id, d.filename, d.status, d.module_no, d.error_message, d.storage_path, d.uploaded_at, d.summary
            ORDER BY d.uploaded_at DESC;
            """,
            (subject_id, current_user.id),
        )
        rows = cursor.fetchall()
        return [
            DocumentStatusResponse(
                id=str(row[0]),
                filename=row[1],
                status=row[2],
                module_no=row[3],
                error_message=row[4],
                storage_path=row[5],
                uploaded_at=str(row[6]) if row[6] else None,
                summary=row[7],
                topic_count=row[8] or 0,
                unreviewed_count=row[9] or 0,
            )
            for row in rows
        ]
