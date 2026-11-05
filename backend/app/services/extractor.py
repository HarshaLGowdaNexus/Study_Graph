"""
Document Text and Vision Extraction Engine for StudyGraph.
Relies on:
  - Decision D08: Google Gemini Flash for handwritten scans & images.
  - Decision D15: pdfplumber + pypdf + python-pptx for typed document parsing.
Enforces:
  - Rule 1 (Scope): Text extraction only; no topic creation here.
  - Golden Rule 7: Cost protection; caps test runs at 10 pages and logs token usage.
"""

from dataclasses import dataclass, field
import io
import logging
from pathlib import Path
import re
from typing import List, Optional

import pdfplumber
import pypdf
from pptx import Presentation

from backend.app.core.config import settings
from backend.app.services.gemini_vision import gemini_vision_service

logger = logging.getLogger(__name__)


@dataclass
class ExtractedChunk:
    page: int
    text: str
    method: str  # 'direct' or 'vision'
    token_usage: Optional[dict] = None


@dataclass
class ExtractionResult:
    chunks: List[ExtractedChunk] = field(default_factory=list)
    pages_processed: int = 0
    direct_pages: int = 0
    vision_pages: int = 0
    total_tokens: int = 0
    file_type: str = "unknown"


def chunk_text(text: str, max_chars: int = 1000, min_chars: int = 80) -> List[str]:
    """
    Splits text into coherent paragraph chunks rather than blind character slicing.
    
    Chunking Rules:
    1. Splits on logical paragraph breaks (double newlines \n\n) or section breaks.
    2. Small fragments (under min_chars, like isolated headings) are merged into the
       next paragraph so citations maintain useful context.
    3. Extra-long paragraphs (exceeding max_chars) are split at natural sentence boundaries
       (., !, ?) to avoid severing words in half.
    """
    if not text or not text.strip():
        return []

    # Normalize line endings
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into raw paragraphs at double newlines
    raw_paras = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
    if not raw_paras:
        # Single block of text without double newlines
        raw_paras = [normalized.strip()]

    # Group short headings with following paragraph
    grouped_chunks: List[str] = []
    buffer = ""

    for para in raw_paras:
        if not buffer:
            buffer = para
        elif len(buffer) < min_chars:
            buffer = f"{buffer}\n\n{para}"
        else:
            grouped_chunks.append(buffer)
            buffer = para

    if buffer:
        grouped_chunks.append(buffer)

    # Split oversized paragraphs at sentence endings
    final_chunks: List[str] = []
    for chunk in grouped_chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            # Split sentences keeping the punctuation
            sentences = re.split(r"(?<=[.?!])\s+", chunk)
            sent_buf = ""
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if not sent_buf:
                    sent_buf = sentence
                elif len(sent_buf) + len(sentence) + 1 <= max_chars:
                    sent_buf = f"{sent_buf} {sentence}"
                else:
                    final_chunks.append(sent_buf)
                    sent_buf = sentence
            if sent_buf:
                final_chunks.append(sent_buf)

    return final_chunks


class DocumentExtractor:
    """
    Orchestrates page-by-page document extraction across PDF, PPTX, and Image files.
    Tries cheap direct text extraction first; falls back to Gemini Vision on scans.
    """

    def __init__(
        self,
        min_text_chars: int = settings.EXTRACTION_MIN_TEXT_CHARS,
        max_test_pages: int = settings.EXTRACTION_MAX_TEST_PAGES,
    ):
        self.min_text_chars = min_text_chars
        self.max_test_pages = max_test_pages

    def extract_document(
        self,
        file_bytes: bytes,
        filename: str,
        source_kind: str = "notes",
    ) -> ExtractionResult:
        """
        Main entry point for document extraction.
        Routes file based on extension and inspects page-by-page.
        """
        ext = Path(filename).suffix.lower()

        if ext == ".pdf":
            return self._extract_pdf(file_bytes)
        elif ext in (".pptx", ".ppt"):
            return self._extract_presentation(file_bytes, ext)
        elif ext in (".png", ".jpg", ".jpeg"):
            return self._extract_image(file_bytes, ext)
        else:
            raise ValueError(f"Unsupported file type for extraction: '{ext}'")

    def _extract_pdf(self, file_bytes: bytes) -> ExtractionResult:
        """
        Extracts PDF page by page.
        Tries pdfplumber direct text first; falls back to Gemini Flash vision
        if a page has fewer than min_text_chars (e.g. handwritten scans).
        """
        result = ExtractionResult(file_type="pdf")

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            total_pages = len(pdf.pages)
            if self.max_test_pages and self.max_test_pages > 0:
                pages_to_run = min(total_pages, self.max_test_pages)
                if total_pages > self.max_test_pages:
                    logger.warning(
                        f"PDF has {total_pages} pages. Capping at {self.max_test_pages} pages for test run."
                    )
            else:
                pages_to_run = total_pages

            # Prepare reader for single page extraction when vision fallback is needed
            pdf_reader = None

            for page_idx in range(pages_to_run):
                page_num = page_idx + 1
                result.pages_processed += 1
                page = pdf.pages[page_idx]

                direct_text = (page.extract_text() or "").strip()

                # Rule: Check if direct text is sufficient
                if len(direct_text) >= self.min_text_chars:
                    # Direct extraction route (Fast & Free)
                    result.direct_pages += 1
                    chunks = chunk_text(direct_text)
                    for c in chunks:
                        result.chunks.append(
                            ExtractedChunk(page=page_num, text=c, method="direct")
                        )
                else:
                    # Scanned / Handwritten page fallback -> Vision model
                    result.vision_pages += 1
                    logger.info(
                        f"Page {page_num} has only {len(direct_text)} characters. "
                        f"Falling back to Gemini Flash vision."
                    )

                    # Isolate this single page into an in-memory PDF
                    if pdf_reader is None:
                        pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))

                    pdf_writer = pypdf.PdfWriter()
                    pdf_writer.add_page(pdf_reader.pages[page_idx])
                    single_page_buf = io.BytesIO()
                    pdf_writer.write(single_page_buf)
                    single_page_bytes = single_page_buf.getvalue()

                    # Call Gemini Flash vision
                    vision_text, token_usage = gemini_vision_service.transcribe_page(
                        single_page_bytes,
                        mime_type="application/pdf",
                    )
                    result.total_tokens += token_usage.get("total_tokens", 0)

                    # If page was blank or empty, vision_text might be empty
                    if vision_text:
                        chunks = chunk_text(vision_text)
                        for c in chunks:
                            result.chunks.append(
                                ExtractedChunk(
                                    page=page_num,
                                    text=c,
                                    method="vision",
                                    token_usage=token_usage,
                                )
                            )

        return result

    def _extract_presentation(self, file_bytes: bytes, ext: str) -> ExtractionResult:
        """
        Extracts PowerPoint presentations.
        Treats each slide as a page (slide 1 = page 1).
        """
        result = ExtractionResult(file_type="presentation")

        if ext == ".ppt":
            raise ValueError(
                "Legacy .ppt binary files are not supported directly. "
                "Please save the presentation as .pptx before uploading."
            )

        prs = Presentation(io.BytesIO(file_bytes))
        total_slides = len(prs.slides)
        if self.max_test_pages and self.max_test_pages > 0:
            slides_to_run = min(total_slides, self.max_test_pages)
        else:
            slides_to_run = total_slides

        for slide_idx in range(slides_to_run):
            slide_num = slide_idx + 1
            result.pages_processed += 1
            slide = prs.slides[slide_idx]

            slide_texts: List[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        p_text = paragraph.text.strip()
                        if p_text:
                            slide_texts.append(p_text)

            combined_text = "\n\n".join(slide_texts).strip()

            if combined_text:
                result.direct_pages += 1
                chunks = chunk_text(combined_text)
                for c in chunks:
                    result.chunks.append(
                        ExtractedChunk(page=slide_num, text=c, method="direct")
                    )
            else:
                # Slide has no readable text (likely an image-only slide)
                result.direct_pages += 1

        return result

    def _extract_image(self, file_bytes: bytes, ext: str) -> ExtractionResult:
        """
        Extracts standalone phone photos or scans of notes.
        Images are treated as single-page documents (page = 1) and routed to vision.
        """
        result = ExtractionResult(file_type="image")
        result.pages_processed = 1
        result.vision_pages = 1

        mime_type = "image/png" if ext == ".png" else "image/jpeg"

        vision_text, token_usage = gemini_vision_service.transcribe_page(
            file_bytes,
            mime_type=mime_type,
        )
        result.total_tokens += token_usage.get("total_tokens", 0)

        if vision_text:
            chunks = chunk_text(vision_text)
            for c in chunks:
                result.chunks.append(
                    ExtractedChunk(
                        page=1,
                        text=c,
                        method="vision",
                        token_usage=token_usage,
                    )
                )

        return result


extractor_service = DocumentExtractor()

