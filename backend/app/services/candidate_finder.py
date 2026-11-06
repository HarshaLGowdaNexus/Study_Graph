"""
Link Candidate Finder Service for StudyGraph (Task T08).
Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase (vector distance and transactional storage).
  - Decision D10: Google text-embedding-004 / 768-dim embeddings.
  - RULEBOOK Golden Rule 7 & Section 13:
      - Two-step linking: Find candidates via embeddings first, judge in T09.
      - User edits are sacred: Skip any pair where edge.status = 'deleted' or edge.locked = true.
      - Never create edges in this step; only link_candidates records.
      - Stricter threshold for cross-subject pairs (Risk R19).
      - Hard cap per topic to prevent cost explosion (Risk R07).
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.schemas.candidate import (
    CandidateBatchResponse,
    CandidateFindResult,
    CandidatePair,
    CandidateSearchParams,
)

logger = logging.getLogger(__name__)


class CandidateFinderService:
    """
    Finds nearest-neighbor topic candidate pairs for link discovery using pgvector
    cosine similarity, applying separate same-subject and cross-subject thresholds,
    strictly honoring user deletions and locks, and enforcing per-topic candidate caps.
    """

    def __init__(
        self,
        k_neighbors: Optional[int] = None,
        same_subject_threshold: Optional[float] = None,
        cross_subject_threshold: Optional[float] = None,
        max_per_topic: Optional[int] = None,
    ):
        self.k_neighbors = k_neighbors or settings.CANDIDATE_K_NEIGHBORS
        self.same_subject_threshold = (
            same_subject_threshold if same_subject_threshold is not None else settings.CANDIDATE_SAME_SUBJECT_THRESHOLD
        )
        self.cross_subject_threshold = (
            cross_subject_threshold if cross_subject_threshold is not None else settings.CANDIDATE_CROSS_SUBJECT_THRESHOLD
        )
        self.max_per_topic = max_per_topic or settings.CANDIDATE_MAX_PER_TOPIC

    def find_candidates_for_topic(
        self,
        topic_id: str,
        k: Optional[int] = None,
        same_thresh: Optional[float] = None,
        cross_thresh: Optional[float] = None,
        max_cap: Optional[int] = None,
        include_cross: bool = True,
        cursor: Optional[Any] = None,
    ) -> CandidateFindResult:
        """
        Finds candidate pairs for a single focal topic.
        Queries both same-subject and cross-subject neighbors, filters out existing/deleted edges,
        and caps total candidates returned.
        """
        k_val = k or self.k_neighbors
        same_t = same_thresh if same_thresh is not None else self.same_subject_threshold
        cross_t = cross_thresh if cross_thresh is not None else self.cross_subject_threshold
        cap_val = max_cap or self.max_per_topic

        # Fetch focal topic info and verify it has an embedding
        focal_query = """
            SELECT t.id, t.keyword, t.explanation, t.subject_id, s.name as subject_name,
                   (t.embedding IS NOT NULL) as has_embedding
            FROM topics t
            JOIN subjects s ON s.id = t.subject_id
            WHERE t.id = %s;
        """
        if cursor is not None:
            cursor.execute(focal_query, (str(topic_id),))
            focal = cursor.fetchone()
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(focal_query, (str(topic_id),))
                focal = cur.fetchone()

        if not focal:
            raise ValueError(f"Topic {topic_id} not found.")

        if not focal["has_embedding"]:
            logger.warning(f"Topic {topic_id} ({focal['keyword']}) has no embedding. Skipping candidate search.")
            return CandidateFindResult(
                topic_id=str(focal["id"]),
                topic_keyword=focal["keyword"],
                subject_id=str(focal["subject_id"]),
                same_subject_candidates=[],
                cross_subject_candidates=[],
                total_candidates=0,
            )

        # 1. Query same-subject candidates
        same_candidates = self._query_neighbors(
            focal_topic_id=str(focal["id"]),
            focal_subject_id=str(focal["subject_id"]),
            same_subject=True,
            threshold=same_t,
            k=k_val,
            cursor=cursor,
        )

        # 2. Query cross-subject candidates if requested
        cross_candidates = []
        if include_cross:
            cross_candidates = self._query_neighbors(
                focal_topic_id=str(focal["id"]),
                focal_subject_id=str(focal["subject_id"]),
                same_subject=False,
                threshold=cross_t,
                k=k_val,
                cursor=cursor,
            )

        # 3. Combine and apply hard cap per topic
        # Order by similarity descending so highest-confidence pairs are prioritized
        combined = same_candidates + cross_candidates
        combined.sort(key=lambda c: c.similarity, reverse=True)
        capped = combined[:cap_val]

        # Separate back into same vs cross for clarity in result
        final_same = [c for c in capped if c.scope == "same_subject"]
        final_cross = [c for c in capped if c.scope == "cross_subject"]

        return CandidateFindResult(
            topic_id=str(focal["id"]),
            topic_keyword=focal["keyword"],
            subject_id=str(focal["subject_id"]),
            same_subject_candidates=final_same,
            cross_subject_candidates=final_cross,
            total_candidates=len(capped),
        )

    def _query_neighbors(
        self,
        focal_topic_id: str,
        focal_subject_id: str,
        same_subject: bool,
        threshold: float,
        k: int,
        cursor: Optional[Any] = None,
    ) -> List[CandidatePair]:
        """
        Executes pgvector nearest-neighbor search for a focal topic against other topics.
        Filters out:
          - Self-matches (t2.id == focal_topic_id)
          - Topics without embeddings
          - Pairs below threshold
          - Pairs where an edge already exists with status='deleted' (Rule 13.2 / user edits)
          - Pairs where an edge already exists with locked=true (Rule 13.2)
          - Pairs where an active edge already exists (status='auto' or status='edited')
        """
        max_distance = 1.0 - threshold
        subject_operator = "=" if same_subject else "!="
        scope_str = "same_subject" if same_subject else "cross_subject"

        query = f"""
            SELECT 
                t1.id AS t1_id,
                t1.keyword AS t1_keyword,
                t1.explanation AS t1_explanation,
                t1.subject_id AS t1_subject_id,
                s1.name AS t1_subject_name,
                t2.id AS t2_id,
                t2.keyword AS t2_keyword,
                t2.explanation AS t2_explanation,
                t2.subject_id AS t2_subject_id,
                s2.name AS t2_subject_name,
                (1 - (t1.embedding <=> t2.embedding)) AS similarity
            FROM topics t1
            JOIN subjects s1 ON s1.id = t1.subject_id
            JOIN topics t2 ON t2.subject_id {subject_operator} t1.subject_id AND t2.id != t1.id
            JOIN subjects s2 ON s2.id = t2.subject_id AND s2.user_id = s1.user_id
            WHERE t1.id = %s
              AND t1.embedding IS NOT NULL
              AND t2.embedding IS NOT NULL
              AND (t1.embedding <=> t2.embedding) <= %s
              AND NOT EXISTS (
                  -- Exclude pairs with deleted, locked, or active edges
                  SELECT 1 FROM edges e
                  WHERE (
                      (e.topic_a = t1.id AND e.topic_b = t2.id)
                      OR
                      (e.topic_a = t2.id AND e.topic_b = t1.id)
                  )
                  AND (e.status = 'deleted' OR e.locked = TRUE OR e.status IN ('auto', 'edited'))
              )
            ORDER BY (t1.embedding <=> t2.embedding) ASC
            LIMIT %s;
        """

        if cursor is not None:
            cursor.execute(query, (focal_topic_id, max_distance, k))
            rows = cursor.fetchall()
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (focal_topic_id, max_distance, k))
                rows = cur.fetchall()

        candidates: List[CandidatePair] = []
        for r in rows:
            # Enforce canonical ordering for topic_a and topic_b (min UUID is topic_a)
            t1_id = str(r["t1_id"])
            t2_id = str(r["t2_id"])

            if t1_id < t2_id:
                cand = CandidatePair(
                    topic_a_id=t1_id,
                    topic_a_keyword=r["t1_keyword"],
                    topic_a_explanation=r["t1_explanation"],
                    topic_a_subject_id=str(r["t1_subject_id"]),
                    topic_a_subject_name=r["t1_subject_name"],
                    topic_b_id=t2_id,
                    topic_b_keyword=r["t2_keyword"],
                    topic_b_explanation=r["t2_explanation"],
                    topic_b_subject_id=str(r["t2_subject_id"]),
                    topic_b_subject_name=r["t2_subject_name"],
                    similarity=round(float(r["similarity"]), 4),
                    scope=scope_str,
                    status="pending",
                )
            else:
                cand = CandidatePair(
                    topic_a_id=t2_id,
                    topic_a_keyword=r["t2_keyword"],
                    topic_a_explanation=r["t2_explanation"],
                    topic_a_subject_id=str(r["t2_subject_id"]),
                    topic_a_subject_name=r["t2_subject_name"],
                    topic_b_id=t1_id,
                    topic_b_keyword=r["t1_keyword"],
                    topic_b_explanation=r["t1_explanation"],
                    topic_b_subject_id=str(r["t1_subject_id"]),
                    topic_b_subject_name=r["t1_subject_name"],
                    similarity=round(float(r["similarity"]), 4),
                    scope=scope_str,
                    status="pending",
                )
            candidates.append(cand)

        return candidates

    def save_candidates(
        self,
        candidates: List[CandidatePair],
        cursor: Optional[Any] = None,
    ) -> int:
        """
        Stores candidate pairs into the link_candidates table.
        Uses ON CONFLICT ON (LEAST(topic_a, topic_b), GREATEST(topic_a, topic_b))
        to ensure symmetric uniqueness and updates similarity if still pending.
        Returns the count of candidates successfully saved/updated.
        """
        if not candidates:
            return 0

        # Deduplicate candidates within the batch in memory first
        unique_map: Dict[Tuple[str, str], CandidatePair] = {}
        for c in candidates:
            key = (min(c.topic_a_id, c.topic_b_id), max(c.topic_a_id, c.topic_b_id))
            if key not in unique_map or c.similarity > unique_map[key].similarity:
                unique_map[key] = c

        insert_query = """
            INSERT INTO link_candidates (topic_a, topic_b, similarity, scope, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (LEAST(topic_a, topic_b), GREATEST(topic_a, topic_b))
            DO UPDATE SET
                similarity = EXCLUDED.similarity,
                scope = EXCLUDED.scope
            WHERE link_candidates.status = 'pending'
            RETURNING id;
        """

        saved_count = 0
        if cursor is not None:
            for pair in unique_map.values():
                cursor.execute(
                    insert_query,
                    (
                        pair.topic_a_id,
                        pair.topic_b_id,
                        pair.similarity,
                        pair.scope,
                        pair.status,
                    ),
                )
                if cursor.fetchone():
                    saved_count += 1
        else:
            with get_db_cursor() as cur:
                for pair in unique_map.values():
                    cur.execute(
                        insert_query,
                        (
                            pair.topic_a_id,
                            pair.topic_b_id,
                            pair.similarity,
                            pair.scope,
                            pair.status,
                        ),
                    )
                    if cur.fetchone():
                        saved_count += 1

        logger.info(f"Persisted {saved_count} unique candidate pairs to link_candidates.")
        return saved_count

    def find_and_store_candidates(
        self,
        params: CandidateSearchParams,
    ) -> CandidateBatchResponse:
        """
        Main entry point: Evaluates topics for candidates, caps the results,
        persists them to the database, and returns the structured summary.
        Reuses a single database connection across batch queries for optimal performance.
        """
        results: List[CandidateFindResult] = []
        all_candidates_to_save: List[CandidatePair] = []
        seen_pairs: Set[Tuple[str, str]] = set()
        same_subject_count = 0
        cross_subject_count = 0
        stored_count = 0

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # Determine topic IDs to evaluate
            topic_ids_to_process: List[str] = []
            if params.topic_ids:
                topic_ids_to_process = [str(tid) for tid in params.topic_ids]
            elif params.subject_id:
                cursor.execute(
                    "SELECT id FROM topics WHERE subject_id = %s AND embedding IS NOT NULL;",
                    (str(params.subject_id),),
                )
                rows = cursor.fetchall()
                topic_ids_to_process = [str(r["id"]) for r in rows]
            else:
                cursor.execute("SELECT id FROM topics WHERE embedding IS NOT NULL;")
                rows = cursor.fetchall()
                topic_ids_to_process = [str(r["id"]) for r in rows]

            for tid in topic_ids_to_process:
                res = self.find_candidates_for_topic(
                    topic_id=tid,
                    k=params.k_neighbors,
                    same_thresh=params.same_subject_threshold,
                    cross_thresh=params.cross_subject_threshold,
                    max_cap=params.max_per_topic,
                    include_cross=params.include_cross_subject,
                    cursor=cursor,
                )
                results.append(res)

                # Collect for persistence with symmetric deduplication
                for c in res.same_subject_candidates + res.cross_subject_candidates:
                    pair_key = (min(c.topic_a_id, c.topic_b_id), max(c.topic_a_id, c.topic_b_id))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        all_candidates_to_save.append(c)
                        if c.scope == "same_subject":
                            same_subject_count += 1
                        else:
                            cross_subject_count += 1

            if params.persist and all_candidates_to_save:
                stored_count = self.save_candidates(all_candidates_to_save, cursor=cursor)

        return CandidateBatchResponse(
            total_topics_evaluated=len(topic_ids_to_process),
            total_candidates_found=len(all_candidates_to_save),
            total_candidates_stored=stored_count if params.persist else 0,
            same_subject_count=same_subject_count,
            cross_subject_count=cross_subject_count,
            results=results,
        )

    def get_stored_candidates(
        self,
        topic_id: Optional[str] = None,
        scope: Optional[str] = None,
        status: str = "pending",
        limit: int = 50,
    ) -> List[CandidatePair]:
        """
        Retrieves stored candidate pairs from link_candidates with topic keywords and details.
        """
        conditions = ["lc.status = %s"]
        params: List[Any] = [status]

        if topic_id:
            conditions.append("(lc.topic_a = %s OR lc.topic_b = %s)")
            params.extend([str(topic_id), str(topic_id)])

        if scope:
            conditions.append("lc.scope = %s")
            params.append(scope)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT 
                lc.id,
                lc.topic_a,
                t1.keyword AS t1_keyword,
                t1.explanation AS t1_explanation,
                t1.subject_id AS t1_subject_id,
                s1.name AS t1_subject_name,
                lc.topic_b,
                t2.keyword AS t2_keyword,
                t2.explanation AS t2_explanation,
                t2.subject_id AS t2_subject_id,
                s2.name AS t2_subject_name,
                lc.similarity,
                lc.scope,
                lc.status,
                lc.created_at
            FROM link_candidates lc
            JOIN topics t1 ON t1.id = lc.topic_a
            JOIN subjects s1 ON s1.id = t1.subject_id
            JOIN topics t2 ON t2.id = lc.topic_b
            JOIN subjects s2 ON s2.id = t2.subject_id
            WHERE {where_clause}
            ORDER BY lc.similarity DESC
            LIMIT %s;
        """
        params.append(limit)

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        pairs: List[CandidatePair] = []
        for r in rows:
            pairs.append(
                CandidatePair(
                    id=str(r["id"]),
                    topic_a_id=str(r["topic_a"]),
                    topic_a_keyword=r["t1_keyword"],
                    topic_a_explanation=r["t1_explanation"],
                    topic_a_subject_id=str(r["t1_subject_id"]),
                    topic_a_subject_name=r["t1_subject_name"],
                    topic_b_id=str(r["topic_b"]),
                    topic_b_keyword=r["t2_keyword"],
                    topic_b_explanation=r["t2_explanation"],
                    topic_b_subject_id=str(r["t2_subject_id"]),
                    topic_b_subject_name=r["t2_subject_name"],
                    similarity=float(r["similarity"]),
                    scope=r["scope"],
                    status=r["status"],
                    created_at=r["created_at"],
                )
            )

        return pairs
