"""
LLM Link Judge Service for StudyGraph (Task T09).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence, link_candidates)
  - Decision D09: Google Gemini Flash for structured JSON evaluation
  - docs/DATA_MODEL.md Table 13 (edges) & Table 14 (edge_evidence)
  - RULEBOOK.md Section 13:
      - Rule 1: No evidence, no link (exact verbatim snippets required).
      - Rule 2: User edits are sacred (never overwrite locked or deleted links).
      - Rule 8: Weak links hidden by default; cross-subject links need strength >= 3.
  - Risks:
      - R03: Wrong or nonsense links (two-step linking, snippets verified by code).
      - R19: Cross-subject links look forced (stricter strength threshold for visibility).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.prompts.link_judge_v1 import LINK_JUDGE_SYSTEM_PROMPT
from backend.app.schemas.edge import (
    EdgeCreate,
    EdgeEvidenceCreate,
    EdgeResponse,
    JudgeBatchResponse,
    JudgeCandidateResult,
    LinkType,
    LLMJudgeRawOutput,
)

logger = logging.getLogger(__name__)

# Allowed link types matching Pydantic schema
ALLOWED_LINK_TYPES: set[str] = {
    "prerequisite_of",
    "same_concept",
    "example_of",
    "applies_in",
    "contrasts_with",
    "part_of",
}


def normalize_for_verification(text: Optional[str]) -> str:
    """
    Normalizes text for robust verbatim matching:
    1. Replaces unicode quotes, curly apostrophes, and em/en dashes with ASCII equivalents.
    2. Strips surrounding quotes (single/double/curly) if the LLM wrapped the snippet.
    3. Collapses all consecutive whitespace into single spaces.
    4. Converts to lowercase for case-insensitive verification.
    """
    if not text:
        return ""
    # Normalize unicode punctuation
    t = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("—", "-")
        .replace("–", "-")
    )
    # Collapse whitespace
    t = " ".join(t.split())
    # Strip wrapping quotation marks
    t = t.strip("\"'")
    return t.lower()


class LinkJudgeService:
    """
    Evaluates candidate topic pairs using Gemini Flash as an evidence-based academic judge.
    Strictly verifies source text snippets with Python code before saving any edge.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        cross_subject_min_visible_strength: Optional[int] = None,
    ):
        self.model_name = model_name or settings.LINK_JUDGE_MODEL
        self.temperature = (
            temperature if temperature is not None else settings.LINK_JUDGE_TEMPERATURE
        )
        self.cross_subject_min_visible_strength = (
            cross_subject_min_visible_strength
            if cross_subject_min_visible_strength is not None
            else settings.CROSS_SUBJECT_MIN_VISIBLE_STRENGTH
        )
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Retrieves or creates a Google GenAI client."""
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set in your .env file.\n"
                "Please add your Google AI Studio API key to .env: GEMINI_API_KEY=AIzaSy..."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _get_topic_data_and_chunks(
        self, topic_id: str, cursor: Any
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Fetches topic metadata and all linked source text chunks for a given topic.
        """
        # Fetch topic metadata
        topic_query = """
            SELECT t.id, t.keyword, t.explanation, t.real_world_use, t.subject_id, s.name as subject_name
            FROM topics t
            JOIN subjects s ON s.id = t.subject_id
            WHERE t.id = %s;
        """
        cursor.execute(topic_query, (topic_id,))
        topic = cursor.fetchone()
        if not topic:
            return None, []

        # Fetch linked source chunks via topic_sources
        chunks_query = """
            SELECT c.id, c.text, c.page, d.filename
            FROM topic_sources ts
            JOIN chunks c ON c.id = ts.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE ts.topic_id = %s;
        """
        cursor.execute(chunks_query, (topic_id,))
        chunks = cursor.fetchall() or []

        # If topic_sources had no chunks, fall back to checking subject document chunks
        if not chunks:
            fallback_chunks_query = """
                SELECT c.id, c.text, c.page, d.filename
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.subject_id = %s
                LIMIT 5;
            """
            cursor.execute(fallback_chunks_query, (str(topic["subject_id"]),))
            chunks = cursor.fetchall() or []

        return dict(topic), [dict(c) for c in chunks]

    def verify_snippet_in_chunks(
        self,
        snippet: Optional[str],
        chunks: List[Dict[str, Any]],
        suggested_chunk_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Deterministic code-level verification that snippet exists word-for-word in chunks.
        Rule 13.1 & Risk R03: The snippet is verified by code, not by the AI.

        Returns:
            (is_verified, matched_chunk_id)
        """
        if not snippet or len(snippet.strip()) < 5:
            return False, None

        norm_snippet = normalize_for_verification(snippet)
        if not norm_snippet:
            return False, None

        # If the LLM suggested a specific chunk, check that chunk first
        if suggested_chunk_id:
            for c in chunks:
                if str(c["id"]) == str(suggested_chunk_id):
                    norm_chunk = normalize_for_verification(c.get("text", ""))
                    if norm_snippet in norm_chunk:
                        return True, str(c["id"])

        # Check all candidate source chunks
        for c in chunks:
            norm_chunk = normalize_for_verification(c.get("text", ""))
            if norm_snippet in norm_chunk:
                return True, str(c["id"])

        return False, None

    def _call_gemini_judge(
        self,
        topic_a: Dict[str, Any],
        chunks_a: List[Dict[str, Any]],
        topic_b: Dict[str, Any],
        chunks_b: List[Dict[str, Any]],
        scope: str,
    ) -> Tuple[LLMJudgeRawOutput, Dict[str, int]]:
        """
        Calls Gemini Flash with low temperature and structured JSON schema.
        Captures token usage for billing logging.
        """
        client = self._get_client()

        # Format source chunks for Topic A
        chunks_a_str = "\n".join(
            [f"[Chunk ID: {c['id']} | Page: {c.get('page', 1)} | File: {c.get('filename', 'doc')}]: {c.get('text', '').strip()}" for c in chunks_a]
        ) or "(No source chunks available)"

        # Format source chunks for Topic B
        chunks_b_str = "\n".join(
            [f"[Chunk ID: {c['id']} | Page: {c.get('page', 1)} | File: {c.get('filename', 'doc')}]: {c.get('text', '').strip()}" for c in chunks_b]
        ) or "(No source chunks available)"

        user_prompt = f"""EVALUATE THIS CANDIDATE TOPIC PAIR:

Candidate Scope: {scope}

=== TOPIC A ===
Keyword: {topic_a['keyword']}
Subject: {topic_a.get('subject_name', 'Unknown')}
Explanation: {topic_a.get('explanation', '')}
Real-World Use: {topic_a.get('real_world_use', '')}
Source Notes Chunks:
{chunks_a_str}

=== TOPIC B ===
Keyword: {topic_b['keyword']}
Subject: {topic_b.get('subject_name', 'Unknown')}
Explanation: {topic_b.get('explanation', '')}
Real-World Use: {topic_b.get('real_world_use', '')}
Source Notes Chunks:
{chunks_b_str}

TASK:
1. Decide whether to accept or reject an academic relationship between Topic A and Topic B.
2. If accepting:
   - Pick the most accurate link type from: prerequisite_of, same_concept, example_of, applies_in, contrasts_with, part_of.
   - Explain why in 1-2 clear sentences.
   - Give an industry/engineering application example.
   - Rate strength from 1 to 5.
   - Provide snippet_a and chunk_id_a from Topic A's chunks (EXACT VERBATIM QUOTE).
   - Provide snippet_b and chunk_id_b from Topic B's chunks (EXACT VERBATIM QUOTE).
3. If rejecting, provide a clear 1-sentence rejection_reason.
"""

        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Models to try in order of preference
        models_to_try = [self.model_name]
        for m in ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"):
            if m not in models_to_try:
                models_to_try.append(m)

        max_attempts = 4
        last_error = None

        for attempt in range(1, max_attempts + 1):
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=LINK_JUDGE_SYSTEM_PROMPT,
                            temperature=self.temperature,
                            response_mime_type="application/json",
                            response_schema=LLMJudgeRawOutput,
                        ),
                    )

                    if response.usage_metadata:
                        tokens["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
                        tokens["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
                        tokens["total_tokens"] = response.usage_metadata.total_token_count or 0

                    raw_text = response.text or "{}"
                    parsed = LLMJudgeRawOutput.model_validate_json(raw_text)
                    return parsed, tokens

                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    # If rate limited (429) or temporary server error (503), back off intelligently
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                        logger.warning(
                            f"[Link Judge] Rate limit (429) on model {model} (attempt {attempt}/{max_attempts}). Backing off 12s..."
                        )
                        print(f"       [Rate Limit] Backing off 12s for Gemini API quota refresh (attempt {attempt}/{max_attempts})...", flush=True)
                        time.sleep(12.0)
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        logger.warning(
                            f"[Link Judge] Model {model} temporarily unavailable (503). Backing off 4s..."
                        )
                        print(f"       [Service 503] Backing off 4s before trying alternative model...", flush=True)
                        time.sleep(4.0)
                    else:
                        logger.warning(f"[Link Judge] Call to {model} failed: {e}. Trying next model...")
                        time.sleep(1.5)

            # Extra pause between outer attempts
            time.sleep(3.0)

        raise RuntimeError(f"Failed to evaluate candidate pair after {max_attempts} attempts. Last error: {last_error}")

    def judge_candidate(
        self,
        candidate_id: Optional[UUID],
        topic_a_id: UUID,
        topic_b_id: UUID,
        scope: str,
        cursor: Any,
    ) -> Tuple[JudgeCandidateResult, Dict[str, int]]:
        """
        Evaluates a single candidate pair:
        1. Checks for existing locked or user-edited edges (Rule 13.2).
        2. Retrieves topic metadata and source chunks.
        3. Calls Gemini Flash with low temperature.
        4. Validates required fields and link types.
        5. Code-level verifies snippets against source chunks.
        6. Persists approved edge + evidence, or rejects.
        """
        # Step 1: Check existing edge locks / deletions
        check_query = """
            SELECT id, locked, status FROM edges
            WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s);
        """
        cursor.execute(check_query, (str(topic_a_id), str(topic_b_id), str(topic_b_id), str(topic_a_id)))
        existing_edge = cursor.fetchone()

        if existing_edge and (existing_edge.get("locked") or existing_edge.get("status") == "deleted"):
            logger.info(f"[Link Judge] Skipping pair ({topic_a_id}, {topic_b_id}) because edge is locked or deleted by user.")
            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))
            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword="Locked Topic",
                topic_b_keyword="Locked Topic",
                verdict="reject",
                rejection_reason="Edge is locked or deleted by user (Rule 13.2).",
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
            ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Step 2: Fetch topic metadata and source chunks
        topic_a, chunks_a = self._get_topic_data_and_chunks(str(topic_a_id), cursor)
        topic_b, chunks_b = self._get_topic_data_and_chunks(str(topic_b_id), cursor)

        if not topic_a or not topic_b:
            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))
            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword=topic_a["keyword"] if topic_a else "Unknown",
                topic_b_keyword=topic_b["keyword"] if topic_b else "Unknown",
                verdict="reject",
                rejection_reason="One or both topics not found in database.",
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
            ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # If either topic has zero source chunks, auto-reject per Rule 13.1 ("No evidence, no link")
        if not chunks_a or not chunks_b:
            logger.warning(f"[Link Judge] Auto-rejecting pair {topic_a['keyword']} <-> {topic_b['keyword']}: missing source chunks.")
            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))
            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword=topic_a["keyword"],
                topic_b_keyword=topic_b["keyword"],
                verdict="reject",
                rejection_reason="Missing source text chunks; cannot provide evidence (Rule 13.1).",
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
            ), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Step 3: Call Gemini Flash judge
        raw_decision, token_usage = self._call_gemini_judge(
            topic_a, chunks_a, topic_b, chunks_b, scope
        )

        # Step 4: Handle rejection by LLM
        if raw_decision.verdict == "reject":
            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))
            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword=topic_a["keyword"],
                topic_b_keyword=topic_b["keyword"],
                verdict="reject",
                rejection_reason=raw_decision.rejection_reason or "LLM judge found no authentic conceptual relationship.",
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
            ), token_usage

        # Step 5: Validate required fields on acceptance
        validation_error = None
        if not raw_decision.type or raw_decision.type not in ALLOWED_LINK_TYPES:
            validation_error = f"Invalid or missing link type: {raw_decision.type}"
        elif not raw_decision.reason or not raw_decision.reason.strip():
            validation_error = "Missing required explanation reason."
        elif not raw_decision.industry_example or not raw_decision.industry_example.strip():
            validation_error = "Missing required industry/practical application example."
        elif raw_decision.strength is None or not (1 <= raw_decision.strength <= 5):
            validation_error = f"Strength must be an integer between 1 and 5 (got {raw_decision.strength})."
        elif not raw_decision.snippet_a or not raw_decision.snippet_b:
            validation_error = "Missing required source snippet evidence."

        if validation_error:
            logger.warning(f"[Link Judge] Auto-rejecting pair ({topic_a['keyword']}, {topic_b['keyword']}) due to validation error: {validation_error}")
            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))
            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword=topic_a["keyword"],
                topic_b_keyword=topic_b["keyword"],
                verdict="reject",
                rejection_reason=validation_error,
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
                verification_error=validation_error,
            ), token_usage

        # Step 6: Code-level verification of snippets in chunks (Rule 13.1 & Risk R03)
        verified_a, matched_chunk_a = self.verify_snippet_in_chunks(
            raw_decision.snippet_a, chunks_a, raw_decision.chunk_id_a
        )
        verified_b, matched_chunk_b = self.verify_snippet_in_chunks(
            raw_decision.snippet_b, chunks_b, raw_decision.chunk_id_b
        )

        if not verified_a or not verified_b:
            err_msg = []
            if not verified_a:
                err_msg.append(f"Snippet A not found in Topic A chunks: '{raw_decision.snippet_a[:60]}...'")
            if not verified_b:
                err_msg.append(f"Snippet B not found in Topic B chunks: '{raw_decision.snippet_b[:60]}...'")
            full_err = "; ".join(err_msg)
            logger.warning(f"[Link Judge] Snippet verification failed for ({topic_a['keyword']}, {topic_b['keyword']}): {full_err}")

            if candidate_id:
                cursor.execute("UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;", (str(candidate_id),))

            return JudgeCandidateResult(
                candidate_id=candidate_id,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                topic_a_keyword=topic_a["keyword"],
                topic_b_keyword=topic_b["keyword"],
                verdict="reject",
                rejection_reason=f"Snippet verification failed: {full_err}",
                scope=scope,  # type: ignore[arg-type]
                is_visible=False,
                snippets_verified=False,
                verification_error=full_err,
            ), token_usage

        # Step 7: Calculate visibility
        # Cross-subject links need strength >= 3 to be visible by default (Risk R19, Rule 13.8)
        if scope == "cross_subject":
            is_visible = (raw_decision.strength >= self.cross_subject_min_visible_strength)
        else:
            is_visible = True

        # Step 8: Persist approved edge & evidence in database
        # Avoid duplicate edge creation if one already exists
        if existing_edge:
            edge_id = existing_edge["id"]
            update_edge_query = """
                UPDATE edges
                SET type = %s, reason = %s, industry_example = %s, strength = %s,
                    scope = %s, status = 'auto', locked = FALSE, is_visible = %s, graph_version = 1
                WHERE id = %s;
            """
            cursor.execute(
                update_edge_query,
                (
                    raw_decision.type,
                    raw_decision.reason,
                    raw_decision.industry_example,
                    raw_decision.strength,
                    scope,
                    is_visible,
                    edge_id,
                ),
            )
            # Remove old evidence to replace with fresh verified snippets
            cursor.execute("DELETE FROM edge_evidence WHERE edge_id = %s;", (edge_id,))
        else:
            insert_edge_query = """
                INSERT INTO edges (
                    topic_a, topic_b, type, reason, industry_example,
                    strength, scope, status, locked, is_visible, graph_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'auto', FALSE, %s, 1)
                RETURNING id;
            """
            cursor.execute(
                insert_edge_query,
                (
                    str(topic_a_id),
                    str(topic_b_id),
                    raw_decision.type,
                    raw_decision.reason,
                    raw_decision.industry_example,
                    raw_decision.strength,
                    scope,
                    is_visible,
                ),
            )
            edge_id = cursor.fetchone()["id"]

        # Insert verified snippets into edge_evidence
        insert_evidence_query = """
            INSERT INTO edge_evidence (edge_id, chunk_id, snippet)
            VALUES (%s, %s, %s);
        """
        cursor.execute(insert_evidence_query, (str(edge_id), matched_chunk_a, raw_decision.snippet_a.strip()))
        cursor.execute(insert_evidence_query, (str(edge_id), matched_chunk_b, raw_decision.snippet_b.strip()))

        # Mark candidate as judged
        if candidate_id:
            cursor.execute("UPDATE link_candidates SET status = 'judged' WHERE id = %s;", (str(candidate_id),))

        return JudgeCandidateResult(
            candidate_id=candidate_id,
            topic_a_id=topic_a_id,
            topic_b_id=topic_b_id,
            topic_a_keyword=topic_a["keyword"],
            topic_b_keyword=topic_b["keyword"],
            verdict="accept",
            edge_id=edge_id,
            type=raw_decision.type,
            strength=raw_decision.strength,
            scope=scope,  # type: ignore[arg-type]
            is_visible=is_visible,
            snippets_verified=True,
        ), token_usage

    def judge_pending_candidates(
        self,
        limit: int = 10,
        scope: Optional[str] = None,
        cursor: Optional[Any] = None,
    ) -> JudgeBatchResponse:
        """
        Processes pending candidate pairs from link_candidates table in batches.
        """
        def _execute(cur: Any) -> JudgeBatchResponse:
            query = """
                SELECT id, topic_a, topic_b, scope, similarity
                FROM link_candidates
                WHERE status = 'pending'
            """
            params: List[Any] = []
            if scope:
                query += " AND scope = %s"
                params.append(scope)

            query += " ORDER BY similarity DESC LIMIT %s;"
            params.append(limit)

            cur.execute(query, tuple(params))
            candidates = cur.fetchall() or []

            results: List[JudgeCandidateResult] = []
            total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            edges_created = 0
            candidates_rejected = 0
            verification_failures = 0

            for idx, c in enumerate(candidates, start=1):
                logger.info(f"[Link Judge] ({idx}/{len(candidates)}) Evaluating candidate {c['id']} (similarity: {c['similarity']}, scope: {c['scope']})...")
                print(f"  [{idx}/{len(candidates)}] Evaluating candidate pair (sim: {c['similarity']:.3f}, scope: {c['scope']})...", flush=True)
                try:
                    res, tokens = self.judge_candidate(
                        candidate_id=c["id"],
                        topic_a_id=c["topic_a"],
                        topic_b_id=c["topic_b"],
                        scope=c["scope"],
                        cursor=cur,
                    )
                    print(f"       -> {res.topic_a_keyword} <-> {res.topic_b_keyword} ==> {res.verdict.upper()} ({res.type or res.rejection_reason})", flush=True)
                    results.append(res)
                    total_tokens["prompt_tokens"] += tokens["prompt_tokens"]
                    total_tokens["completion_tokens"] += tokens["completion_tokens"]
                    total_tokens["total_tokens"] += tokens["total_tokens"]

                    if res.verdict == "accept":
                        edges_created += 1
                    else:
                        candidates_rejected += 1
                        if res.verification_error:
                            verification_failures += 1
                except Exception as err:
                    logger.error(f"[Link Judge] Error evaluating candidate {c['id']}: {err}")
                    print(f"       [ERROR] Could not evaluate candidate: {err}. Skipping to preserve batch.", flush=True)
                    candidates_rejected += 1

                # 1.5s pacing delay between candidates to respect Gemini Free Tier rate limits
                time.sleep(1.5)

            # Estimated cost for Gemini Flash: $0.10/M input, $0.40/M output
            estimated_cost = (
                (total_tokens["prompt_tokens"] * 0.10 / 1_000_000)
                + (total_tokens["completion_tokens"] * 0.40 / 1_000_000)
            )

            return JudgeBatchResponse(
                total_evaluated=len(candidates),
                edges_created=edges_created,
                candidates_rejected=candidates_rejected,
                verification_failures=verification_failures,
                results=results,
                token_usage=total_tokens,
                estimated_cost_usd=round(estimated_cost, 6),
            )

        if cursor:
            return _execute(cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                return _execute(cur)
