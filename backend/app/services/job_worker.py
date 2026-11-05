"""
Background Job Processing for StudyGraph.
Relies on:
  - Decision D07: FastAPI BackgroundTasks.
  - Decision D08: Google Gemini Flash for scans/handwriting.
  - Decision D15: pdfplumber + pypdf + python-pptx for typed text.
Handles asynchronous document pipeline processing without blocking the HTTP upload response.
"""

import logging
from typing import Optional

from backend.app.database import get_db_cursor
from backend.app.services.extractor import extractor_service
from backend.app.services.storage import storage_service

logger = logging.getLogger(__name__)


def update_document_status(document_id: str, status: str, error_message: Optional[str] = None) -> None:
    """
    Updates the status and optional error message of a document in PostgreSQL.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE documents 
            SET status = %s,
                error_message = %s
            WHERE id = %s;
            """,
            (status, error_message, document_id),
        )


async def process_document_job(document_id: str, user_id: str) -> None:
    """
    Background worker executed via FastAPI BackgroundTasks.
    Transitions status: queued -> extracting -> done (or failed on error).
    
    T04 Ingestion Pipeline:
    1. Fetches document record (filename, module_no, storage_path, source_kind).
    2. Downloads raw binary file from Supabase Storage / local cache.
    3. Runs DocumentExtractor (direct text vs. Gemini Flash vision).
    4. Stores resulting paragraph chunks in the 'chunks' table with page, module_no, and method.
    5. Marks document as 'done'.
    """
    try:
        # Step 1: Mark status as 'extracting'
        update_document_status(document_id, "extracting")
        logger.info(f"[Job Worker] Document {document_id} transitioned to 'extracting'")

        # Step 2: Fetch document metadata from DB
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT filename, module_no, storage_path, source_kind
                FROM documents
                WHERE id = %s;
                """,
                (document_id,),
            )
            doc_row = cursor.fetchone()

        if not doc_row:
            raise ValueError(f"Document with id {document_id} not found in database.")

        filename, module_no, storage_path, source_kind = doc_row
        if not storage_path:
            raise ValueError(f"Document {document_id} has no storage_path recorded.")

        # Step 3: Download file bytes from storage
        file_bytes = await storage_service.download_file(storage_path)
        logger.info(
            f"[Job Worker] Downloaded {len(file_bytes)} bytes for '{filename}' ({storage_path})"
        )

        # Step 4: Extract text and vision chunks page-by-page
        extraction_result = extractor_service.extract_document(
            file_bytes=file_bytes,
            filename=filename,
            source_kind=source_kind or "notes",
        )

        logger.info(
            f"[Job Worker] Extracted {len(extraction_result.chunks)} chunks from '{filename}' "
            f"({extraction_result.pages_processed} pages: {extraction_result.direct_pages} direct, "
            f"{extraction_result.vision_pages} vision, {extraction_result.total_tokens} tokens)"
        )

        # Step 5: Save chunks to PostgreSQL
        with get_db_cursor() as cursor:
            # Clear previous chunks if any exist for this document (idempotency rule)
            cursor.execute("DELETE FROM chunks WHERE document_id = %s;", (document_id,))

            for chunk in extraction_result.chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (document_id, page, text, module_no, method)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (document_id, chunk.page, chunk.text, module_no, chunk.method),
                )

        # Step 6: Mark status as 'done'
        update_document_status(document_id, "done")
        logger.info(f"[Job Worker] Document {document_id} processing complete: status -> 'done'")

    except Exception as e:
        logger.error(f"[Job Worker] Error processing document {document_id}: {e}", exc_info=True)
        update_document_status(document_id, "failed", error_message=str(e))
