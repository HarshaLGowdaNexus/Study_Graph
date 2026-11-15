"""
Topic Deduplication and Merge Service for StudyGraph (T07).
Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase (vector distance and transactional merges).
  - Decision D09: Google Gemini Flash for LLM confirmation step.
  - Decision D10: Google embeddings.
  - RULEBOOK Golden Rule 7 & Section 13:
      - Never auto-merge across different subjects.
      - User edits are sacred; all merges are logged and can be split (undone).
      - Maintain all source evidence links (topic_sources).
      - Maintain topic_aliases.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.prompts.topic_dedupe_v1 import TOPIC_DEDUPE_SYSTEM_PROMPT
from backend.app.schemas.dedupe import (
    CandidatePair,
    DedupeJudgeDecision,
    DedupeRunResponse,
    MergeRecordResponse,
)
from backend.app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


def _parse_uuid_array(val: Any) -> List[str]:
    """Safely parses a PostgreSQL uuid[] array whether returned as a Python list or '{id1,id2}' string."""
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(item).strip() for item in val if str(item).strip()]
    if isinstance(val, str):
        cleaned = val.strip("{}").strip()
        if not cleaned:
            return []
        return [item.strip() for item in cleaned.split(",") if item.strip()]
    return []


class DedupeService:
    def __init__(self):
        self.similarity_threshold = settings.DEDUPE_SIMILARITY_THRESHOLD
        self.model_name = settings.DEDUPE_CONFIRMATION_MODEL
        self.temperature = settings.DEDUPE_CONFIRMATION_TEMPERATURE
        self._client: Optional[genai.Client] = None
        self.embedding_service = EmbeddingService()

    def _get_client(self) -> genai.Client:
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set in your .env file.\n"
                "Please add your Google AI Studio API key to .env: GEMINI_API_KEY=AIzaSy..."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def find_candidate_pairs(
        self, subject_id: UUID, custom_threshold: Optional[float] = None
    ) -> List[CandidatePair]:
        """
        Finds pairs of topics WITHIN THE SAME SUBJECT whose cosine similarity is >= threshold.
        Rule: NEVER cross-merge across different subjects.
        In pgvector, cosine distance is `<=>`.
        cosine_similarity = 1 - cosine_distance.
        So: cosine_distance <= (1 - threshold).
        """
        threshold = custom_threshold if custom_threshold is not None else self.similarity_threshold
        max_distance = 1.0 - threshold

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # Query pairs of topics in the same subject with non-null embeddings
            # t1.id < t2.id prevents evaluating the same pair twice or self-pairing
            query = """
                SELECT 
                    t1.id AS t1_id, t1.keyword AS t1_keyword, t1.explanation AS t1_explanation,
                    t2.id AS t2_id, t2.keyword AS t2_keyword, t2.explanation AS t2_explanation,
                    (1 - (t1.embedding <=> t2.embedding)) AS similarity
                FROM topics t1
                JOIN topics t2 ON t1.subject_id = t2.subject_id AND t1.id < t2.id
                WHERE t1.subject_id = %s
                  AND t1.embedding IS NOT NULL
                  AND t2.embedding IS NOT NULL
                  AND (t1.embedding <=> t2.embedding) <= %s
                ORDER BY similarity DESC;
            """
            cursor.execute(query, (str(subject_id), max_distance))
            rows = cursor.fetchall()

        candidates: List[CandidatePair] = []
        for r in rows:
            candidates.append(
                CandidatePair(
                    topic_a_id=str(r["t1_id"]),
                    topic_a_keyword=r["t1_keyword"],
                    topic_a_explanation=r["t1_explanation"],
                    topic_b_id=str(r["t2_id"]),
                    topic_b_keyword=r["t2_keyword"],
                    topic_b_explanation=r["t2_explanation"],
                    similarity=float(r["similarity"]),
                )
            )

        logger.info(
            f"Found {len(candidates)} duplicate candidate pairs in subject {subject_id} (threshold={threshold})"
        )
        return candidates

    def confirm_duplicate_with_llm(
        self,
        topic_a_keyword: str,
        topic_a_explanation: str,
        topic_b_keyword: str,
        topic_b_explanation: str,
    ) -> DedupeJudgeDecision:
        """
        Calls Gemini Flash to verify whether two candidate topics represent
        the exact same concept or distinct concepts.
        """
        client = self._get_client()

        user_content = (
            f"Topic A: {topic_a_keyword}\n"
            f"Explanation A: {topic_a_explanation}\n\n"
            f"Topic B: {topic_b_keyword}\n"
            f"Explanation B: {topic_b_explanation}\n\n"
            f"Are these two topics referring to the exact same concept that should be merged?"
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=TOPIC_DEDUPE_SYSTEM_PROMPT,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=DedupeJudgeDecision,
                ),
            )

            response_text = response.text.strip()
            data = json.loads(response_text)
            return DedupeJudgeDecision(**data)

        except Exception as e:
            logger.error(f"Error in LLM duplicate confirmation with {self.model_name}: {e}")
            # Resilient fallback to alternative model if primary experiences rate limits or spikes
            fallback_models = ["gemini-3-flash-preview", "gemini-3.5-flash-lite"]
            for fb in fallback_models:
                if fb != self.model_name:
                    try:
                        logger.info(f"Retrying LLM duplicate confirmation with fallback model '{fb}'...")
                        response = client.models.generate_content(
                            model=fb,
                            contents=user_content,
                            config=types.GenerateContentConfig(
                                system_instruction=TOPIC_DEDUPE_SYSTEM_PROMPT,
                                temperature=self.temperature,
                                response_mime_type="application/json",
                                response_schema=DedupeJudgeDecision,
                            ),
                        )
                        return DedupeJudgeDecision(**json.loads(response.text.strip()))
                    except Exception as fb_err:
                        logger.warning(f"Fallback model '{fb}' also failed: {fb_err}")

            # Safe default on persistent error: do not merge
            return DedupeJudgeDecision(
                is_duplicate=False,
                confidence=0.0,
                reason=f"Verification failed due to error: {str(e)}",
            )

    def merge_topics(
        self,
        surviving_topic_id: UUID,
        merged_topic_id: UUID,
        similarity_score: Optional[float] = None,
        merge_type: str = "auto",
        canonical_keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Merges merged_topic_id into surviving_topic_id.
        Rules:
          1. Both topics must belong to the exact same subject.
          2. Preserves all topic_sources links.
          3. Adds merged_topic's keyword to topic_aliases of surviving_topic.
          4. Re-assigns any existing topic_aliases of merged_topic to surviving_topic.
          5. Logs full details to topic_merges for undo/split support.
          6. Deletes merged_topic from topics.
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Fetch both topics
            cursor.execute(
                """
                SELECT id, subject_id, keyword, explanation, real_world_use, module_no,
                       COALESCE(source_variants, '{}'::jsonb) AS source_variants
                FROM topics
                WHERE id IN (%s, %s)
                """,
                (str(surviving_topic_id), str(merged_topic_id)),
            )
            rows = {str(r["id"]): r for r in cursor.fetchall()}

            if str(surviving_topic_id) not in rows or str(merged_topic_id) not in rows:
                raise ValueError("One or both topics do not exist.")

            surviving = rows[str(surviving_topic_id)]
            merged = rows[str(merged_topic_id)]

            # Strict rule: Never merge across subjects
            if surviving["subject_id"] != merged["subject_id"]:
                raise ValueError("Cross-subject topic merging is strictly prohibited.")

            subject_id = surviving["subject_id"]

            # 2. Fetch all chunk_ids associated with the merged topic
            cursor.execute(
                "SELECT chunk_id FROM topic_sources WHERE topic_id = %s",
                (str(merged_topic_id),),
            )
            transferred_chunk_ids = [str(r["chunk_id"]) for r in cursor.fetchall()]

            # 3. Transfer topic_sources to surviving_topic (ON CONFLICT DO NOTHING avoids duplicate keys)
            for chunk_id in transferred_chunk_ids:
                cursor.execute(
                    """
                    INSERT INTO topic_sources (topic_id, chunk_id)
                    VALUES (%s, %s)
                    ON CONFLICT (topic_id, chunk_id) DO NOTHING
                    """,
                    (str(surviving_topic_id), chunk_id),
                )

            # 4. Add merged keyword to topic_aliases of surviving topic
            cursor.execute(
                """
                INSERT INTO topic_aliases (topic_id, alias)
                VALUES (%s, %s)
                ON CONFLICT (topic_id, alias) DO NOTHING
                """,
                (str(surviving_topic_id), merged["keyword"]),
            )

            # Also transfer any previous aliases from merged_topic
            cursor.execute(
                "SELECT alias FROM topic_aliases WHERE topic_id = %s",
                (str(merged_topic_id),),
            )
            for r in cursor.fetchall():
                cursor.execute(
                    """
                    INSERT INTO topic_aliases (topic_id, alias)
                    VALUES (%s, %s)
                    ON CONFLICT (topic_id, alias) DO NOTHING
                    """,
                    (str(surviving_topic_id), r["alias"]),
                )

            # 5. Record the merge in topic_merges audit table
            cursor.execute(
                """
                INSERT INTO topic_merges (
                    subject_id, surviving_topic_id, merged_topic_id,
                    merged_keyword, merged_explanation, merged_real_world_use,
                    merged_module_no, similarity_score, merge_type, transferred_chunk_ids
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid[])
                RETURNING id;
                """,
                (
                    str(subject_id),
                    str(surviving_topic_id),
                    str(merged_topic_id),
                    merged["keyword"],
                    merged["explanation"],
                    merged["real_world_use"],
                    merged["module_no"],
                    similarity_score,
                    merge_type,
                    transferred_chunk_ids,
                ),
            )
            merge_record_id = cursor.fetchone()["id"]

            # If LLM recommended a canonical keyword and it's the merged one, update surviving keyword
            if canonical_keyword and canonical_keyword.lower() == merged["keyword"].lower():
                old_surviving_kw = surviving["keyword"]
                cursor.execute(
                    "UPDATE topics SET keyword = %s WHERE id = %s",
                    (canonical_keyword, str(surviving_topic_id)),
                )
                # Keep old surviving keyword as an alias
                cursor.execute(
                    """
                    INSERT INTO topic_aliases (topic_id, alias)
                    VALUES (%s, %s)
                    ON CONFLICT (topic_id, alias) DO NOTHING
                    """,
                    (str(surviving_topic_id), old_surviving_kw),
                )

            # Preserve source_variants across merge
            surv_variants = surviving.get("source_variants") if isinstance(surviving.get("source_variants"), dict) else {}
            merg_variants = merged.get("source_variants") if isinstance(merged.get("source_variants"), dict) else {}
            combined_variants = {**merg_variants, **surv_variants}
            cursor.execute(
                """
                UPDATE topics
                SET source_variants = %s::jsonb
                WHERE id = %s;
                """,
                (json.dumps(combined_variants), str(surviving_topic_id)),
            )

            # 5b. Re-wire edges connected to merged_topic_id to prevent valid links from being lost by CASCADE
            cursor.execute(
                """
                DELETE FROM edges
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
                """,
                (str(surviving_topic_id), str(merged_topic_id), str(merged_topic_id), str(surviving_topic_id)),
            )

            cursor.execute(
                "SELECT id, topic_b FROM edges WHERE topic_a = %s",
                (str(merged_topic_id),),
            )
            for edge_row in cursor.fetchall():
                other_topic = str(edge_row["topic_b"])
                cursor.execute(
                    """
                    SELECT id FROM edges 
                    WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s)
                    """,
                    (str(surviving_topic_id), other_topic, other_topic, str(surviving_topic_id)),
                )
                if cursor.fetchone():
                    cursor.execute("DELETE FROM edges WHERE id = %s", (edge_row["id"],))
                else:
                    cursor.execute("UPDATE edges SET topic_a = %s WHERE id = %s", (str(surviving_topic_id), edge_row["id"]))

            cursor.execute(
                "SELECT id, topic_a FROM edges WHERE topic_b = %s",
                (str(merged_topic_id),),
            )
            for edge_row in cursor.fetchall():
                other_topic = str(edge_row["topic_a"])
                cursor.execute(
                    """
                    SELECT id FROM edges 
                    WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s)
                    """,
                    (str(surviving_topic_id), other_topic, other_topic, str(surviving_topic_id)),
                )
                if cursor.fetchone():
                    cursor.execute("DELETE FROM edges WHERE id = %s", (edge_row["id"],))
                else:
                    cursor.execute("UPDATE edges SET topic_b = %s WHERE id = %s", (str(surviving_topic_id), edge_row["id"]))

            # 6. Delete merged topic (CASCADE cleans up old topic_sources and topic_aliases for merged_topic_id)
            cursor.execute("DELETE FROM topics WHERE id = %s", (str(merged_topic_id),))

        logger.info(
            f"Merged topic '{merged['keyword']}' into '{surviving['keyword']}' (merge_id={merge_record_id})"
        )

        return {
            "merge_id": str(merge_record_id),
            "surviving_topic_id": str(surviving_topic_id),
            "merged_topic_id": str(merged_topic_id),
            "surviving_keyword": surviving["keyword"],
            "merged_keyword": merged["keyword"],
            "transferred_chunks_count": len(transferred_chunk_ids),
        }

    def split_merge(self, merge_id: UUID) -> Dict[str, Any]:
        """
        Splits (undoes) a previous merge.
        1. Retrieves the original topic details and transferred chunk IDs from topic_merges.
        2. Restores the merged topic row back into topics with its original UUID and fields.
        3. Restores topic_sources links for the transferred chunks.
        4. Removes the merged topic's keyword from topic_aliases of the surviving topic.
        5. Marks undone_at = NOW() in topic_merges.
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Fetch merge record
            cursor.execute(
                """
                SELECT id, subject_id, surviving_topic_id, merged_topic_id,
                       merged_keyword, merged_explanation, merged_real_world_use,
                       merged_module_no, transferred_chunk_ids, undone_at
                FROM topic_merges
                WHERE id = %s
                """,
                (str(merge_id),),
            )
            record = cursor.fetchone()
            if not record:
                raise ValueError(f"Merge record {merge_id} not found.")

            if record["undone_at"] is not None:
                raise ValueError("This merge has already been split (undone).")

            # 2. Check surviving topic still exists
            surviving_id = str(record["surviving_topic_id"])
            cursor.execute("SELECT id, keyword FROM topics WHERE id = %s", (surviving_id,))
            surviving = cursor.fetchone()

            # 3. Re-create the merged topic
            merged_id = str(record["merged_topic_id"])
            cursor.execute(
                """
                INSERT INTO topics (
                    id, subject_id, keyword, explanation, real_world_use, module_no, reviewed
                )
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                """,
                (
                    merged_id,
                    str(record["subject_id"]),
                    record["merged_keyword"],
                    record["merged_explanation"],
                    record["merged_real_world_use"],
                    record["merged_module_no"],
                ),
            )

            # Re-generate embedding for the restored topic
            embedding = self.embedding_service.generate_single_embedding(
                f"{record['merged_keyword']}: {record['merged_explanation']}"
            )
            if embedding:
                emb_str = f"[{','.join(f'{x:.6f}' for x in embedding)}]"
                cursor.execute(
                    "UPDATE topics SET embedding = %s::vector WHERE id = %s",
                    (emb_str, merged_id),
                )

            # 4. Restore topic_sources links
            transferred_chunk_ids = _parse_uuid_array(record["transferred_chunk_ids"])
            for chunk_id in transferred_chunk_ids:
                cursor.execute(
                    """
                    INSERT INTO topic_sources (topic_id, chunk_id)
                    VALUES (%s, %s)
                    ON CONFLICT (topic_id, chunk_id) DO NOTHING
                    """,
                    (merged_id, str(chunk_id)),
                )

            # 5. Remove alias from surviving topic if it exists
            if surviving:
                cursor.execute(
                    "DELETE FROM topic_aliases WHERE topic_id = %s AND alias = %s",
                    (surviving_id, record["merged_keyword"]),
                )

            # 6. Mark merge as undone
            cursor.execute(
                "UPDATE topic_merges SET undone_at = NOW() WHERE id = %s",
                (str(merge_id),),
            )

        logger.info(f"Successfully split merge {merge_id}: restored topic '{record['merged_keyword']}'")

        return {
            "merge_id": str(merge_id),
            "restored_topic_id": merged_id,
            "restored_keyword": record["merged_keyword"],
            "restored_chunks_count": len(transferred_chunk_ids),
            "surviving_topic_id": surviving_id,
        }

    def run_auto_deduplication(
        self, subject_id: UUID, custom_threshold: Optional[float] = None
    ) -> DedupeRunResponse:
        """
        Runs the full automated deduplication pipeline for a subject:
        1. Ensure all topics in subject have embeddings.
        2. Find candidate pairs exceeding similarity threshold.
        3. For each candidate pair:
           - Call LLM confirmation to verify if they are truly identical concepts.
           - If LLM confirms: merge them, record alias, preserve sources, log to topic_merges.
        """
        start_time = time.time()

        # Step 1: Ensure embeddings exist
        self.embedding_service.embed_unembedded_topics(subject_id)

        # Step 2: Find candidates
        candidates = self.find_candidate_pairs(subject_id, custom_threshold)

        merges_executed = 0
        merged_pairs = []
        already_merged_ids: Set[str] = set()

        # Step 3: Evaluate candidates with LLM
        for pair in candidates:
            # Skip if either topic in the pair was already merged away in this run
            if pair.topic_a_id in already_merged_ids or pair.topic_b_id in already_merged_ids:
                continue

            decision = self.confirm_duplicate_with_llm(
                topic_a_keyword=pair.topic_a_keyword,
                topic_a_explanation=pair.topic_a_explanation,
                topic_b_keyword=pair.topic_b_keyword,
                topic_b_explanation=pair.topic_b_explanation,
            )

            if decision.is_duplicate and decision.confidence >= 0.7:
                # Merge topic B into topic A (surviving)
                merge_info = self.merge_topics(
                    surviving_topic_id=UUID(pair.topic_a_id),
                    merged_topic_id=UUID(pair.topic_b_id),
                    similarity_score=pair.similarity,
                    merge_type="auto",
                    canonical_keyword=decision.canonical_keyword,
                )

                already_merged_ids.add(pair.topic_b_id)
                merges_executed += 1
                merged_pairs.append({
                    "surviving_keyword": pair.topic_a_keyword,
                    "merged_keyword": pair.topic_b_keyword,
                    "similarity": round(pair.similarity, 4),
                    "reason": decision.reason,
                    "canonical_keyword": decision.canonical_keyword,
                })
            else:
                logger.info(
                    f"LLM rejected merge for '{pair.topic_a_keyword}' and '{pair.topic_b_keyword}': {decision.reason}"
                )

        duration = time.time() - start_time

        return DedupeRunResponse(
            subject_id=str(subject_id),
            candidates_found=len(candidates),
            merges_executed=merges_executed,
            merged_pairs=merged_pairs,
            duration_seconds=round(duration, 2),
        )

    def list_merge_history(self, subject_id: UUID) -> List[MergeRecordResponse]:
        """Lists all merge operations for a subject (both active and undone)."""
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT 
                    m.id, m.subject_id, m.surviving_topic_id, t.keyword AS surviving_keyword,
                    m.merged_topic_id, m.merged_keyword, m.merged_explanation,
                    m.similarity_score, m.merge_type, m.transferred_chunk_ids,
                    m.created_at, m.undone_at
                FROM topic_merges m
                LEFT JOIN topics t ON m.surviving_topic_id = t.id
                WHERE m.subject_id = %s
                ORDER BY m.created_at DESC;
            """
            cursor.execute(query, (str(subject_id),))
            rows = cursor.fetchall()

        records = []
        for r in rows:
            records.append(
                MergeRecordResponse(
                    id=str(r["id"]),
                    subject_id=str(r["subject_id"]),
                    surviving_topic_id=str(r["surviving_topic_id"]),
                    surviving_keyword=r["surviving_keyword"],
                    merged_topic_id=str(r["merged_topic_id"]),
                    merged_keyword=r["merged_keyword"],
                    merged_explanation=r["merged_explanation"],
                    similarity_score=r["similarity_score"],
                    merge_type=r["merge_type"],
                    transferred_chunk_ids=_parse_uuid_array(r["transferred_chunk_ids"]),
                    created_at=r["created_at"].isoformat() if r["created_at"] else "",
                    undone_at=r["undone_at"].isoformat() if r["undone_at"] else None,
                )
            )
        return records
