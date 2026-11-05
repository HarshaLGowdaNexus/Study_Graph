"""
Background Job Processing for StudyGraph.
Relies on Decision D07: FastAPI BackgroundTasks.
Handles asynchronous document pipeline processing without blocking the HTTP upload response.
"""

import asyncio
import time
from backend.app.database import get_db_cursor


def update_document_status(document_id: str, status: str, error_message: str = None) -> None:
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
    In T04, this will trigger the real PDF parser / Vision OCR pipeline.
    """
    try:
        # Step 1: Mark status as 'extracting'
        update_document_status(document_id, "extracting")

        # Brief non-blocking wait to demonstrate pipeline progress in UI
        await asyncio.sleep(1.5)

        # Step 2: In T03, ingestion handoff is complete. Mark status as 'done'
        update_document_status(document_id, "done")

    except Exception as e:
        # Step 3: Record failure cleanly so student sees why it failed
        update_document_status(document_id, "failed", error_message=str(e))

