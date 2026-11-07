"""
Topic Extraction Service for StudyGraph (T05).
Relies on:
  - Decision D09: Google Gemini Flash with low temperature (0.1) and structured JSON.
  - Decision D05: PostgreSQL on Supabase (topics and topic_sources).
  - RULEBOOK Section 13:
      - Rule 1: No evidence, no link/topic (source chunk IDs strictly required and verified).
      - Rule 3: Topic cards are short (keyword plus at most 4 lines, plus real-world use).
      - Rule 9: Mark uncertain data (topics saved with reviewed = false).
"""

import concurrent.futures
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from google import genai
from google.genai import types

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.prompts.topic_extraction_v1 import TOPIC_EXTRACTION_SYSTEM_PROMPT
from backend.app.schemas.topic import TopicExtractionItem, TopicExtractionResponse

logger = logging.getLogger(__name__)


@dataclass
class TopicExtractionBatchResult:
    topics_created: int = 0
    topics_rejected: int = 0
    batches_processed: int = 0
    batches_failed: int = 0
    failure_reasons: List[str] = field(default_factory=list)
    created_topic_ids: List[str] = field(default_factory=list)
    token_usage: Dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )


class TopicExtractorService:
    def __init__(self):
        self.model_name = settings.TOPIC_EXTRACTION_MODEL
        self.temperature = settings.TOPIC_EXTRACTION_TEMPERATURE
        self.max_topics_per_page = settings.MAX_TOPICS_PER_PAGE
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set in your .env file.\n"
                "Please add your Google AI Studio API key to .env: GEMINI_API_KEY=AIzaSy..."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _call_gemini_structured(
        self,
        prompt: str,
    ) -> Tuple[TopicExtractionResponse, Dict[str, int]]:
        """
        Calls Gemini Flash with structured JSON output and low temperature.
        Attempts 1 immediate retry on schema parsing error.
        """
        client = self._get_client()

        models_to_try = [self.model_name]
        for fallback in ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"):
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None

        # Attempt up to 2 tries (primary attempt + 1 retry on invalid output)
        for attempt in range(1, 3):
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(
                            temperature=self.temperature,
                            response_mime_type="application/json",
                            response_schema=TopicExtractionResponse,
                        ),
                    )
                    self.model_name = model

                    # Token usage extraction
                    tokens = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    }
                    if response.usage_metadata:
                        tokens["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
                        tokens["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
                        tokens["total_tokens"] = response.usage_metadata.total_token_count or 0

                    raw_text = response.text or "{}"
                    # Strict validation through Pydantic
                    parsed = TopicExtractionResponse.model_validate_json(raw_text)
                    return parsed, tokens

                except Exception as e:
                    logger.warning(
                        f"[Topic Extractor] Attempt {attempt} with model {model} failed: {e}. Backing off 1.5s..."
                    )
                    last_error = e
                    time.sleep(1.5)

            logger.info(f"[Topic Extractor] Retrying topic extraction after attempt {attempt} error: {last_error}")
            time.sleep(2.0)

        raise RuntimeError(f"Failed to generate structured topics after 2 attempts. Last error: {last_error}")

    def extract_topics_from_chunk_group(
        self,
        chunks: List[dict],
        subject_id: str,
        module_no: Optional[int] = None,
    ) -> Tuple[List[TopicExtractionItem], List[dict], Dict[str, int]]:
        """
        Extracts validated topics for a group of chunks (e.g. from one page).
        Validates:
          1. Cited chunk IDs strictly exist in the provided chunks.
          2. Explanation does not exceed 4 lines.
        Returns:
          (valid_topics, rejected_topics_info, token_usage)
        """
        if not chunks:
            return [], [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Format input chunks with IDs
        chunk_id_map: Dict[str, dict] = {str(c["id"]): c for c in chunks}
        valid_chunk_ids: Set[str] = set(chunk_id_map.keys())

        chunks_text_blocks = []
        for c in chunks:
            cid = str(c["id"])
            page = c.get("page", 1)
            text = c.get("text", "").strip()
            chunks_text_blocks.append(f"[Chunk ID: {cid}] (Page {page}):\n{text}")

        formatted_chunks = "\n\n".join(chunks_text_blocks)

        prompt = TOPIC_EXTRACTION_SYSTEM_PROMPT.format(
            chunks_formatted=formatted_chunks,
            max_topics=self.max_topics_per_page,
        )

        try:
            parsed_response, tokens = self._call_gemini_structured(prompt)
        except Exception as e:
            logger.error(f"[Topic Extractor] Group extraction failed: {e}")
            raise

        valid_topics: List[TopicExtractionItem] = []
        rejected_topics: List[dict] = []

        for item in parsed_response.topics:
            # Check 1: Explanation line count (max 4 lines)
            clean_explanation = item.explanation.strip()
            lines = [l.strip() for l in clean_explanation.splitlines() if l.strip()]
            if len(lines) > 4:
                logger.warning(
                    f"[Topic Extractor] Rejected topic '{item.keyword}': "
                    f"explanation has {len(lines)} lines (> 4 limit)."
                )
                rejected_topics.append({
                    "keyword": item.keyword,
                    "reason": f"Explanation exceeds 4 lines ({len(lines)} lines)",
                })
                continue

            # Check 2: Grounding verification — cited chunk IDs MUST exist
            cited_ids = set(item.source_chunk_ids)
            invalid_citations = cited_ids - valid_chunk_ids

            if invalid_citations:
                logger.warning(
                    f"[Topic Extractor] Rejected topic '{item.keyword}': "
                    f"cited non-existent chunk IDs {invalid_citations}. "
                    "Rulebook Rule 1 mandates strict evidence."
                )
                rejected_topics.append({
                    "keyword": item.keyword,
                    "reason": f"Cited non-existent chunk IDs: {invalid_citations}",
                })
                continue

            # If passed both checks, it is a valid topic
            valid_topics.append(item)

        return valid_topics, rejected_topics, tokens

    def save_topics_to_database(
        self,
        topics: List[TopicExtractionItem],
        subject_id: str,
        module_no: Optional[int],
    ) -> List[str]:
        """
        Saves approved topics to PostgreSQL 'topics' and 'topic_sources' tables.
        Sets reviewed = FALSE and assigns module_no from chunk metadata.
        """
        if not topics:
            return []

        created_topic_ids = []

        with get_db_cursor() as cursor:
            for topic in topics:
                # Check for existing topic in this subject to guarantee idempotency (Rule T11)
                cursor.execute(
                    """
                    SELECT id, reviewed 
                    FROM topics 
                    WHERE subject_id = %s AND LOWER(TRIM(keyword)) = LOWER(TRIM(%s))
                    LIMIT 1;
                    """,
                    (subject_id, topic.keyword),
                )
                existing = cursor.fetchone()

                if existing:
                    topic_id = str(existing[0])
                    is_reviewed = bool(existing[1])
                    # If not reviewed by student yet, update with latest extraction
                    if not is_reviewed:
                        cursor.execute(
                            """
                            UPDATE topics
                            SET explanation = %s,
                                real_world_use = %s,
                                module_no = COALESCE(module_no, %s)
                            WHERE id = %s;
                            """,
                            (topic.explanation, topic.real_world_use, module_no, topic_id),
                        )
                    created_topic_ids.append(topic_id)
                else:
                    # Insert new topic into topics table
                    cursor.execute(
                        """
                        INSERT INTO topics (
                            subject_id,
                            keyword,
                            explanation,
                            real_world_use,
                            reviewed,
                            module_no
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id;
                        """,
                        (
                            subject_id,
                            topic.keyword,
                            topic.explanation,
                            topic.real_world_use,
                            False,  # reviewed = false
                            module_no,
                        ),
                    )
                    row = cursor.fetchone()
                    if row:
                        topic_id = str(row[0])
                        created_topic_ids.append(topic_id)

                # Insert citations into topic_sources table
                if topic_id:
                    for chunk_id in topic.source_chunk_ids:
                        cursor.execute(
                            """
                            INSERT INTO topic_sources (topic_id, chunk_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING;
                            """,
                            (topic_id, chunk_id),
                        )

        return created_topic_ids

    def process_document_topics(
        self,
        document_id: str,
    ) -> TopicExtractionBatchResult:
        """
        Processes all chunks of a document, grouping them page by page,
        extracts topics with Gemini Flash, validates them, and stores them in PostgreSQL.
        """
        # Fetch document metadata
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, subject_id, module_no, filename
                FROM documents
                WHERE id = %s;
                """,
                (document_id,),
            )
            doc_row = cursor.fetchone()

        if not doc_row:
            raise ValueError(f"Document {document_id} not found.")

        doc_id, subject_id, doc_module_no, filename = doc_row

        # Fetch chunks for this document
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, page, text, module_no
                FROM chunks
                WHERE document_id = %s
                ORDER BY page ASC, id ASC;
                """,
                (document_id,),
            )
            chunk_rows = cursor.fetchall()

        if not chunk_rows:
            logger.info(f"[Topic Extractor] No chunks found for document {document_id}.")
            return TopicExtractionBatchResult()

        # Group chunks by page
        pages_dict: Dict[int, List[dict]] = {}
        for row in chunk_rows:
            cid, page, text, chunk_module = row
            c_dict = {
                "id": str(cid),
                "page": page,
                "text": text,
                "module_no": chunk_module if chunk_module is not None else doc_module_no,
            }
            pages_dict.setdefault(page, []).append(c_dict)

        result = TopicExtractionBatchResult()

        # Concurrent page processing for high throughput (Quality Gate G07: <= 90s for 20 pages)
        def _process_single_page(page_entry: Tuple[int, List[dict]]):
            p_num, chunks_on_p = page_entry
            total_text = "".join(c["text"] for c in chunks_on_p).strip()
            if not total_text:
                return p_num, [], [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, None

            m_no = chunks_on_p[0].get("module_no") or doc_module_no
            try:
                val_topics, rej, tok = self.extract_topics_from_chunk_group(
                    chunks=chunks_on_p,
                    subject_id=str(subject_id),
                    module_no=m_no,
                )
                return p_num, val_topics, rej, tok, None
            except Exception as exc:
                return p_num, [], [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, str(exc)

        page_items = sorted(pages_dict.items())
        max_workers = min(5, len(page_items)) if page_items else 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            page_outputs = list(executor.map(_process_single_page, page_items))

        # Sort outputs to preserve deterministic page ordering
        page_outputs.sort(key=lambda x: x[0])

        for page_num, valid_topics, rejected, tokens, err in page_outputs:
            result.batches_processed += 1
            if err:
                result.batches_failed += 1
                reason = f"Page {page_num} failed: {err}"
                result.failure_reasons.append(reason)
                logger.error(f"[Topic Extractor] {reason}")
                continue

            result.token_usage["prompt_tokens"] += tokens["prompt_tokens"]
            result.token_usage["completion_tokens"] += tokens["completion_tokens"]
            result.token_usage["total_tokens"] += tokens["total_tokens"]
            result.topics_rejected += len(rejected)

            if valid_topics:
                m_no = pages_dict[page_num][0].get("module_no") or doc_module_no
                saved_ids = self.save_topics_to_database(
                    topics=valid_topics,
                    subject_id=str(subject_id),
                    module_no=m_no,
                )
                result.topics_created += len(saved_ids)
                result.created_topic_ids.extend(saved_ids)

        logger.info(
            f"[Topic Extractor] Document {document_id} completed: "
            f"{result.topics_created} topics created, {result.topics_rejected} rejected, "
            f"{result.batches_failed} failed pages, total tokens: {result.token_usage['total_tokens']}"
        )
        return result


topic_extractor_service = TopicExtractorService()

