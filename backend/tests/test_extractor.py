"""
Unit and Integration Tests for Document Text and Vision Extraction Engine (Task T04).
Relies on:
  - Decision D14: pytest (Backend test runner)
  - Decision D15: pdfplumber + pypdf + python-pptx
  - Decision D08: Google Gemini Flash Vision
"""

import io
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
from reportlab.pdfgen import canvas

from backend.app.services.extractor import (
    DocumentExtractor,
    chunk_text,
    extractor_service,
)


def create_sample_pdf(pages_content: list[list[str]]) -> bytes:
    """Helper to generate a test PDF in-memory using reportlab."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for lines in pages_content:
        y = 750
        for line in lines:
            c.drawString(72, y, line)
            y -= 25
        c.showPage()
    c.save()
    return buf.getvalue()


def create_sample_pptx(slides_content: list[list[str]]) -> bytes:
    """Helper to generate a test PPTX presentation in-memory."""
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]  # Blank slide
    for slide_lines in slides_content:
        slide = prs.slides.add_slide(blank_layout)
        tx_box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(4))
        tf = tx_box.text_frame
        for line in slide_lines:
            p = tf.add_paragraph()
            p.text = line
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def create_sample_image() -> bytes:
    """Helper to generate a simple test PNG in-memory."""
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------------------
# 1. Chunking Logic Tests
# ------------------------------------------------------------------------------
def test_chunk_text_empty_and_whitespace():
    """Empty or whitespace text returns an empty list without errors."""
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []
    assert chunk_text(None) == []


def test_chunk_text_paragraphs_and_headings():
    """Short headings are merged with the next paragraph to keep citations useful."""
    text = (
        "## Chapter 1: Introduction to Network Protocols\n\n"
        "Computer networks enable communication across distributed systems through standardized "
        "layered architectures like the OSI 7-layer reference model.\n\n"
        "The transmission medium connects physical interfaces together."
    )
    chunks = chunk_text(text, max_chars=1000, min_chars=80)
    assert len(chunks) == 2
    # The short heading must be prepended to the first paragraph
    assert "Chapter 1: Introduction to Network Protocols" in chunks[0]
    assert "OSI 7-layer reference model" in chunks[0]
    assert "transmission medium" in chunks[1]


def test_chunk_text_splits_oversized_blocks_at_sentences():
    """Oversized paragraphs (> max_chars) are split at sentence boundaries, not cut in half."""
    sent1 = "The Open Systems Interconnection model defines seven distinct abstraction layers. "
    sent2 = "Each layer performs a specific function and communicates with adjacent layers. "
    sent3 = "The physical layer conveys raw bits over physical transmission media. "
    sent4 = "The data link layer provides node-to-node data transfer across physical links. "

    long_paragraph = sent1 + sent2 + sent3 + sent4
    chunks = chunk_text(long_paragraph, max_chars=180, min_chars=50)

    assert len(chunks) >= 2
    for c in chunks:
        # Every chunk should be a full grammatical sentence
        assert c.endswith((".", "!", "?"))


# ------------------------------------------------------------------------------
# 2. Typed PDF Extraction Tests
# ------------------------------------------------------------------------------
def test_extract_typed_pdf_direct_method():
    """A typed lecture PDF extracts text directly and sets method='direct' with exact page numbers."""
    page1 = [
        "Operating Systems Lecture 1: Process Management Overview",
        "A process is a program in execution representing the fundamental unit of work.",
        "The operating system maintains a Process Control Block (PCB) for every active task.",
    ]
    page2 = [
        "Operating Systems Lecture 2: Thread Concurrency and Context Switching",
        "Threads share the process memory space while maintaining their own registers and stack.",
        "Context switching switches CPU execution from one process thread to another.",
    ]

    pdf_bytes = create_sample_pdf([page1, page2])
    result = extractor_service.extract_document(pdf_bytes, "os_notes.pdf")

    assert result.file_type == "pdf"
    assert result.pages_processed == 2
    assert result.direct_pages == 2
    assert result.vision_pages == 0
    assert len(result.chunks) >= 2

    # Verify 1-based page numbers
    page_numbers = {c.page for c in result.chunks}
    assert page_numbers == {1, 2}

    # Verify all chunks use direct extraction
    for c in result.chunks:
        assert c.method == "direct"
        assert c.token_usage is None


# ------------------------------------------------------------------------------
# 3. PowerPoint Slide Extraction Tests
# ------------------------------------------------------------------------------
def test_extract_powerpoint_presentation():
    """PowerPoint slides are extracted directly with slide numbers as page numbers."""
    slide1 = [
        "Computer Networks: Transport Layer",
        "TCP provides reliable, connection-oriented byte stream transmission.",
    ]
    slide2 = [
        "UDP Protocol Characteristics",
        "UDP is connectionless and lightweight without retransmissions or flow control.",
    ]

    pptx_bytes = create_sample_pptx([slide1, slide2])
    result = extractor_service.extract_document(pptx_bytes, "transport_layer.pptx")

    assert result.file_type == "presentation"
    assert result.pages_processed == 2
    assert result.direct_pages == 2
    assert len(result.chunks) >= 2

    # Slide 1 -> Page 1, Slide 2 -> Page 2
    p1_chunks = [c for c in result.chunks if c.page == 1]
    p2_chunks = [c for c in result.chunks if c.page == 2]

    assert len(p1_chunks) >= 1
    assert "connection-oriented" in p1_chunks[0].text
    assert len(p2_chunks) >= 1
    assert "connectionless" in p2_chunks[0].text


# ------------------------------------------------------------------------------
# 4. Scanned PDF & Vision Fallback Tests
# ------------------------------------------------------------------------------
def test_scanned_pdf_falls_back_to_vision():
    """
    A PDF page with very little text (< 50 chars) triggers Gemini Vision OCR fallback,
    capturing method='vision' and token counts.
    """
    # Page with minimal text (e.g. only a header watermark < 50 chars)
    page_scan = ["Page 1."]
    pdf_bytes = create_sample_pdf([page_scan])

    mock_transcription = (
        "Handwritten Notes:\n"
        "Token Ring topology connects nodes in a closed logical loop.\n"
        "Frame travels unidirectionally until destination acknowledges."
    )
    mock_tokens = {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165}

    with patch(
        "backend.app.services.extractor.gemini_vision_service.transcribe_page",
        return_value=(mock_transcription, mock_tokens),
    ) as mock_vision:
        result = extractor_service.extract_document(pdf_bytes, "scanned_notes.pdf")

        assert mock_vision.called
        assert result.pages_processed == 1
        assert result.vision_pages == 1
        assert result.direct_pages == 0
        assert result.total_tokens == 165

        assert len(result.chunks) >= 1
        assert result.chunks[0].method == "vision"
        assert result.chunks[0].page == 1
        assert "Token Ring topology" in result.chunks[0].text
        assert result.chunks[0].token_usage == mock_tokens


# ------------------------------------------------------------------------------
# 5. Standalone Image Notes Test
# ------------------------------------------------------------------------------
def test_image_notes_extraction():
    """A standalone phone photo or scan (.png, .jpg) routes to vision with page=1."""
    img_bytes = create_sample_image()
    mock_text = "Handwritten diagram: CPU Scheduling Queue -> Running State -> I/O Wait"
    mock_tokens = {"prompt_tokens": 150, "completion_tokens": 20, "total_tokens": 170}

    with patch(
        "backend.app.services.extractor.gemini_vision_service.transcribe_page",
        return_value=(mock_text, mock_tokens),
    ) as mock_vision:
        result = extractor_service.extract_document(img_bytes, "notes_photo.png")

        assert mock_vision.called
        assert result.file_type == "image"
        assert result.pages_processed == 1
        assert result.vision_pages == 1
        assert len(result.chunks) == 1
        assert result.chunks[0].page == 1
        assert result.chunks[0].method == "vision"
        assert "CPU Scheduling Queue" in result.chunks[0].text


# ------------------------------------------------------------------------------
# 6. Blank / Empty Page Safety Test
# ------------------------------------------------------------------------------
def test_blank_page_does_not_crash():
    """A completely blank page with 0 text returns 0 chunks safely without crashing."""
    blank_pdf = create_sample_pdf([[]])  # 0 text on page 1

    with patch(
        "backend.app.services.extractor.gemini_vision_service.transcribe_page",
        return_value=("", {"prompt_tokens": 50, "completion_tokens": 0, "total_tokens": 50}),
    ):
        result = extractor_service.extract_document(blank_pdf, "blank.pdf")
        assert result.pages_processed == 1
        assert result.chunks == []


# ------------------------------------------------------------------------------
# 7. Test Run Page Cap Test (Rule 7: Cost protection)
# ------------------------------------------------------------------------------
def test_max_test_pages_cap():
    """Documents exceeding max_test_pages are capped at max_test_pages during testing."""
    pages = [
        [f"Page {i+1}: Detailed lecture notes describing network protocol layer number {i+1}."]
        for i in range(12)
    ]
    pdf_bytes = create_sample_pdf(pages)

    custom_extractor = DocumentExtractor(max_test_pages=5)
    result = custom_extractor.extract_document(pdf_bytes, "huge_notes.pdf")

    assert result.pages_processed == 5
    assert max(c.page for c in result.chunks) == 5


# ------------------------------------------------------------------------------
# 8. End-to-End Worker and Database Integration Test
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_job_worker_stores_chunks_in_database(tmp_path):
    """
    Verifies that process_document_job downloads the document, extracts chunks,
    stores them in PostgreSQL with module_no and method, and marks status 'done'.
    """
    import uuid
    from backend.app.core.config import settings
    from backend.app.database import get_db_cursor
    from backend.app.services.job_worker import process_document_job
    from pathlib import Path

    # Generate test document with 2 pages of notes
    p1 = ["Database Systems: Module 2 Relational Algebra", "Selection and projection operations filter tuples."]
    p2 = ["Join Operations in SQL", "Inner and outer joins combine tuples from multiple relations."]
    pdf_bytes = create_sample_pdf([p1, p2])

    test_user_id = str(uuid.uuid4())
    test_doc_id = str(uuid.uuid4())
    test_subject_id = str(uuid.uuid4())
    relative_storage_path = f"{test_user_id}/{test_subject_id}/module_2/sample_notes.pdf"

    # Save to local cache so download_file locates it immediately
    local_target = Path(settings.ROOT_DIR) / ".storage_cache" / settings.SUPABASE_STORAGE_BUCKET / relative_storage_path
    local_target.parent.mkdir(parents=True, exist_ok=True)
    local_target.write_bytes(pdf_bytes)

    # Insert test user, subject, and document in DB
    with get_db_cursor() as cursor:
        cursor.execute("INSERT INTO users (id, email, name) VALUES (%s, %s, %s);", (test_user_id, f"test_{test_user_id[:8]}@example.com", "Test Student"))
        cursor.execute("INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, %s);", (test_subject_id, test_user_id, "Database Systems"))
        cursor.execute(
            """
            INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status, storage_path)
            VALUES (%s, %s, %s, %s, %s, %s, 'queued', %s);
            """,
            (test_doc_id, test_subject_id, 2, "sample_notes.pdf", "pdf", "notes", f"local://{settings.SUPABASE_STORAGE_BUCKET}/{relative_storage_path}"),
        )

    try:
        # Run the background job worker
        await process_document_job(test_doc_id, test_user_id)

        # Verify document status updated to 'done'
        with get_db_cursor() as cursor:
            cursor.execute("SELECT status, error_message FROM documents WHERE id = %s;", (test_doc_id,))
            status, err = cursor.fetchone()
            assert status == "done", f"Job failed with error: {err}"

            # Verify chunks were inserted
            cursor.execute(
                "SELECT page, text, module_no, method FROM chunks WHERE document_id = %s ORDER BY page;",
                (test_doc_id,),
            )
            rows = cursor.fetchall()

            assert len(rows) >= 2
            # Check page numbers
            pages = [r[0] for r in rows]
            assert 1 in pages
            assert 2 in pages

            # Check module_no
            assert all(r[2] == 2 for r in rows)

            # Check method
            assert all(r[3] == "direct" for r in rows)

    finally:
        # Clean up test rows
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM chunks WHERE document_id = %s;", (test_doc_id,))
            cursor.execute("DELETE FROM documents WHERE id = %s;", (test_doc_id,))
            cursor.execute("DELETE FROM subjects WHERE id = %s;", (test_subject_id,))
            cursor.execute("DELETE FROM users WHERE id = %s;", (test_user_id,))

