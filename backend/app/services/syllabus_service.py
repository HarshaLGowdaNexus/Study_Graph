"""
Syllabus Ghost Nodes, Matching, Coverage/Gap Analysis & Source Preference Service (Task T18).
Relies on:
  - Feature F16: Ghost nodes from syllabus (coverage and gaps).
  - Feature F17: Notes vs textbook preference per subject.
  - Risk R12: Preserve university > scheme > syllabus_subject > syllabus_topics hierarchy.
  - Risk R13: Empty graph shows syllabus ghost nodes before any notes arrive.
  - Decision D09: Google Gemini Flash for syllabus parsing & match confirmation.
  - Decision D10: Google text-embedding-004 / gemini-embedding-001 (768-dim) for matching.
  - RULEBOOK 13.2: User match corrections are locked and never overwritten.
"""

import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.prompts.syllabus_extraction_v1 import (
    SYLLABUS_EXTRACTION_PROMPT,
    SYLLABUS_MATCH_CONFIRM_PROMPT,
)
from backend.app.schemas.syllabus import (
    ExtractedSyllabusItem,
    MatchRunResponse,
    MatchedTopicSummary,
    ModuleCoverageItem,
    SubjectPreferenceResponse,
    SubjectSyllabusResponse,
    SyllabusExtractionOutput,
    SyllabusMatchDecision,
    SyllabusMetadata,
    SyllabusTopicItem,
)
from backend.app.services.embedding_service import (
    EmbeddingService,
    compute_cosine_similarity,
)
from backend.app.services.extractor import extractor_service
from backend.app.services.graph_service import graph_service

logger = logging.getLogger(__name__)


def _parse_pgvector(raw_vec: Any) -> Optional[List[float]]:
    """Converts a pgvector string or list into a Python float list."""
    if raw_vec is None:
        return None
    if isinstance(raw_vec, list):
        return [float(x) for x in raw_vec]
    if isinstance(raw_vec, str):
        cleaned = raw_vec.strip().strip("[]")
        if not cleaned:
            return None
        return [float(x) for x in cleaned.split(",")]
    return None


def _normalize_title(text: str) -> str:
    """Normalizes topic titles for exact/substring fast matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _fallback_parse_syllabus(raw_text: str) -> SyllabusExtractionOutput:
    """
    Deterministic line/delimiter parser used when LLM extraction fails or is unavailable.
    Recognizes 'Module X' / 'Unit X' headers and splits bullet/comma/semicolon topics.
    """
    current_module = 1
    items: List[ExtractedSyllabusItem] = []
    seen = set()

    mod_header_re = re.compile(
        r"^(?:module|unit|chapter|section)\s*[-:]?\s*(\d+|i{1,3}|iv|v|vi{0,3}|ix|x)\b[:\s-]*(.*)$",
        re.IGNORECASE,
    )
    roman_map = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}

    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip().lstrip("•*-–— ").strip()
        if not line:
            continue

        m = mod_header_re.match(line)
        if m:
            mod_token = m.group(1).lower()
            current_module = int(mod_token) if mod_token.isdigit() else roman_map.get(mod_token, current_module)
            remainder = (m.group(2) or "").strip()
            if not remainder:
                continue
            line = remainder

        # Split comma/semicolon lists into atomic ghost nodes
        parts = [p.strip(" .:-") for p in re.split(r"[;,]", line) if p.strip()]
        for part in parts:
            if len(part) < 3 or len(part) > 180:
                continue
            key = (current_module, part.lower())
            if key in seen:
                continue
            seen.add(key)
            items.append(ExtractedSyllabusItem(module_no=current_module, title=part))

    return SyllabusExtractionOutput(topics=items)


class SyllabusService:
    """
    Manages official syllabus upload, parsing, review, two-step matching to note topics,
    per-module coverage/gaps, and per-subject source preference (notes vs textbook).
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.parse_model = settings.SYLLABUS_PARSE_MODEL
        self.confirm_model = settings.SYLLABUS_MATCH_CONFIRM_MODEL
        self.temperature = settings.SYLLABUS_PARSE_TEMPERATURE
        self.match_threshold = settings.SYLLABUS_MATCH_THRESHOLD
        self.auto_exact_threshold = settings.SYLLABUS_AUTO_EXACT_THRESHOLD
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in .env.")
        if self._client is None:
            self._client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options={"timeout": 30000},
            )
        return self._client

    def _safe_refresh_graph(self, user_id: str, subject_id: str) -> None:
        """Refreshes subject graph cache after syllabus/match/preference changes."""
        try:
            graph_service.refresh_and_cache_graph(user_id=user_id, subject_id=subject_id)
        except Exception as err:
            logger.warning(f"[Syllabus] Non-fatal graph cache refresh failure for {subject_id}: {err}")

    def _verify_subject_owner(self, cursor, subject_id: str, user_id: str) -> Dict[str, Any]:
        cursor.execute(
            """
            SELECT id, user_id, syllabus_subject_id, name, source_preference
            FROM subjects
            WHERE id = %s AND user_id = %s;
            """,
            (str(subject_id), str(user_id)),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or access denied.",
            )
        return dict(row)

    def _extract_syllabus_items(self, raw_text: str) -> SyllabusExtractionOutput:
        """Parses syllabus text into (module_no, title) items via Gemini Flash with deterministic fallback."""
        clean_text = (raw_text or "").strip()
        if not clean_text:
            raise HTTPException(status_code=400, detail="Syllabus text is empty.")

        try:
            client = self._get_client()
            prompt = SYLLABUS_EXTRACTION_PROMPT.format(syllabus_text=clean_text[:18000])
            models_to_try = [self.parse_model]
            for fb in ("gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-flash-latest"):
                if fb not in models_to_try:
                    models_to_try.append(fb)

            last_err = None
            retired = set()
            for attempt in range(1, 3):
                for model in models_to_try:
                    if model in retired:
                        continue
                    try:
                        response = client.models.generate_content(
                            model=model,
                            contents=[prompt],
                            config=types.GenerateContentConfig(
                                temperature=self.temperature,
                                response_mime_type="application/json",
                                response_schema=SyllabusExtractionOutput,
                            ),
                        )
                        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                        if response.usage_metadata:
                            tokens["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
                            tokens["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
                            tokens["total_tokens"] = response.usage_metadata.total_token_count or 0
                        logger.info(
                            f"[Syllabus Parse AI] Model: {model} | Tokens: {tokens['total_tokens']} "
                            f"(Prompt: {tokens['prompt_tokens']}, Output: {tokens['completion_tokens']})"
                        )
                        parsed = SyllabusExtractionOutput.model_validate_json(response.text or "{}")
                        if parsed.topics:
                            return parsed
                    except Exception as e:
                        last_err = e
                        if "404" in str(e) or "NOT_FOUND" in str(e):
                            retired.add(model)
                            continue
                        logger.warning(f"[Syllabus Parse] Model {model} attempt {attempt} failed: {e}")
                        time.sleep(0.8)
            logger.warning(f"[Syllabus Parse] Falling back to deterministic parser after error: {last_err}")
        except Exception as outer_err:
            logger.warning(f"[Syllabus Parse] Using deterministic parser ({outer_err})")

        fallback = _fallback_parse_syllabus(clean_text)
        if not fallback.topics:
            raise HTTPException(
                status_code=400,
                detail="Could not extract any syllabus topics from the provided text.",
            )
        return fallback

    def _ensure_syllabus_subject_hierarchy(
        self,
        cursor,
        subject_row: Dict[str, Any],
        university_name: str,
        scheme_name: str,
        subject_code: Optional[str],
        semester: Optional[int],
        branch: Optional[str],
    ) -> str:
        """
        Ensures universities -> schemes -> syllabus_subjects hierarchy is populated
        and linked on subjects.syllabus_subject_id (Risk R12).
        """
        uni_clean = (university_name or "Default University").strip()
        scheme_clean = (scheme_name or "2022 Scheme").strip()
        code_clean = (subject_code or re.sub(r"[^A-Z0-9]", "", subject_row["name"].upper())[:8] or "SUBJ101").strip()

        # 1. Find or create university
        cursor.execute(
            "SELECT id FROM universities WHERE LOWER(name) = LOWER(%s) LIMIT 1;",
            (uni_clean,),
        )
        uni_row = cursor.fetchone()
        if uni_row:
            university_id = str(uni_row["id"])
        else:
            cursor.execute(
                "INSERT INTO universities (name) VALUES (%s) RETURNING id;",
                (uni_clean,),
            )
            university_id = str(cursor.fetchone()["id"])

        # 2. Find or create scheme under that university
        cursor.execute(
            "SELECT id FROM schemes WHERE university_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1;",
            (university_id, scheme_clean),
        )
        scheme_row = cursor.fetchone()
        if scheme_row:
            scheme_id = str(scheme_row["id"])
        else:
            cursor.execute(
                "INSERT INTO schemes (university_id, name) VALUES (%s, %s) RETURNING id;",
                (university_id, scheme_clean),
            )
            scheme_id = str(cursor.fetchone()["id"])

        # 3. Reuse or create a dedicated syllabus_subject for this student's subject
        existing_syl_sub_id = subject_row.get("syllabus_subject_id")
        if existing_syl_sub_id:
            cursor.execute(
                """
                UPDATE syllabus_subjects
                SET scheme_id = %s,
                    code = %s,
                    name = %s,
                    semester = COALESCE(%s, semester),
                    branch = COALESCE(%s, branch)
                WHERE id = %s
                RETURNING id;
                """,
                (scheme_id, code_clean, subject_row["name"], semester, branch, str(existing_syl_sub_id)),
            )
            updated = cursor.fetchone()
            if updated:
                return str(updated["id"])

        cursor.execute(
            """
            INSERT INTO syllabus_subjects (scheme_id, code, name, semester, branch)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (scheme_id, code_clean, subject_row["name"], semester, branch),
        )
        syl_sub_id = str(cursor.fetchone()["id"])

        cursor.execute(
            "UPDATE subjects SET syllabus_subject_id = %s WHERE id = %s;",
            (syl_sub_id, str(subject_row["id"])),
        )
        return syl_sub_id

    def ingest_syllabus_text(
        self,
        user_id: str,
        subject_id: str,
        syllabus_text: str,
        university_name: str = "Default University",
        scheme_name: str = "2022 Scheme",
        subject_code: Optional[str] = None,
        semester: Optional[int] = None,
        branch: Optional[str] = None,
    ) -> SubjectSyllabusResponse:
        """
        Parses syllabus text into syllabus_topics, embeds them, stores hierarchy,
        and immediately matches against any existing topics in the subject.
        """
        parsed = self._extract_syllabus_items(syllabus_text)
        final_code = subject_code or parsed.detected_subject_code

        # Deduplicate parsed titles within same module
        deduped_items: List[ExtractedSyllabusItem] = []
        seen_keys = set()
        for item in parsed.topics:
            clean_title = item.title.strip()
            if not clean_title:
                continue
            key = (item.module_no, clean_title.lower())
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_items.append(ExtractedSyllabusItem(module_no=item.module_no, title=clean_title))

        # Generate 768-dim embeddings in batch (Decision D10)
        texts_to_embed = [f"Module {it.module_no}: {it.title}" for it in deduped_items]
        embeddings: List[Optional[List[float]]] = [None] * len(deduped_items)
        try:
            batch_vecs = self.embedding_service.generate_embeddings(texts_to_embed)
            if len(batch_vecs) == len(deduped_items):
                embeddings = batch_vecs
        except Exception as emb_err:
            logger.warning(f"[Syllabus] Embedding batch skipped/failed cleanly: {emb_err}")

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subject_row = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = self._ensure_syllabus_subject_hierarchy(
                cursor=cursor,
                subject_row=subject_row,
                university_name=university_name,
                scheme_name=scheme_name,
                subject_code=final_code,
                semester=semester,
                branch=branch,
            )

            # Clear previous auto-matches on this subject before replacing syllabus topics
            cursor.execute(
                """
                UPDATE topics
                SET syllabus_topic_id = NULL,
                    syllabus_match_locked = FALSE
                WHERE subject_id = %s;
                """,
                (str(subject_id),),
            )
            cursor.execute(
                "DELETE FROM syllabus_topics WHERE syllabus_subject_id = %s;",
                (syl_sub_id,),
            )

            for item, vec in zip(deduped_items, embeddings):
                emb_str = f"[{','.join(f'{x:.6f}' for x in vec)}]" if vec else None
                cursor.execute(
                    """
                    INSERT INTO syllabus_topics (syllabus_subject_id, module_no, title, parent_id, embedding, reviewed)
                    VALUES (%s, %s, %s, NULL, %s::vector, FALSE);
                    """,
                    (syl_sub_id, item.module_no, item.title, emb_str),
                )

        # Match newly created syllabus ghost nodes against any notes already uploaded
        self.match_subject_topics(subject_id=subject_id, user_id=user_id, refresh_cache=False)
        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        return self.get_subject_syllabus(user_id=user_id, subject_id=subject_id)

    def ingest_syllabus_file(
        self,
        user_id: str,
        subject_id: str,
        file_bytes: bytes,
        filename: str,
        university_name: str = "Default University",
        scheme_name: str = "2022 Scheme",
        subject_code: Optional[str] = None,
        semester: Optional[int] = None,
        branch: Optional[str] = None,
    ) -> SubjectSyllabusResponse:
        """Extracts text from an uploaded syllabus file (PDF/PPTX/image) and parses it."""
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            self._verify_subject_owner(cursor, subject_id, user_id)

        extraction_res = extractor_service.extract_document(
            file_bytes=file_bytes,
            filename=filename,
            source_kind="syllabus",
        )
        full_text = "\n".join(ch.text for ch in extraction_res.chunks if ch.text.strip())
        if not full_text.strip():
            raise HTTPException(
                status_code=400,
                detail="No readable text was found in the uploaded syllabus file.",
            )

        return self.ingest_syllabus_text(
            user_id=user_id,
            subject_id=subject_id,
            syllabus_text=full_text,
            university_name=university_name,
            scheme_name=scheme_name,
            subject_code=subject_code,
            semester=semester,
            branch=branch,
        )

    def _confirm_match_with_llm(
        self,
        topic_keyword: str,
        topic_explanation: str,
        topic_module_no: Optional[int],
        syllabus_title: str,
        syllabus_module_no: int,
    ) -> SyllabusMatchDecision:
        """Calls Gemini Flash-Lite to confirm whether a note topic covers a syllabus topic."""
        try:
            client = self._get_client()
            prompt = SYLLABUS_MATCH_CONFIRM_PROMPT.format(
                topic_keyword=topic_keyword,
                topic_explanation=topic_explanation,
                topic_module_no=topic_module_no or 1,
                syllabus_title=syllabus_title,
                syllabus_module_no=syllabus_module_no,
            )
            models_to_try = [self.confirm_model]
            for fb in ("gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-flash-latest"):
                if fb not in models_to_try:
                    models_to_try.append(fb)

            last_err = None
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                            response_schema=SyllabusMatchDecision,
                        ),
                    )
                    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    if response.usage_metadata:
                        tokens["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
                        tokens["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
                        tokens["total_tokens"] = response.usage_metadata.total_token_count or 0
                    logger.info(
                        f"[Syllabus Match AI] Model: {model} | Tokens: {tokens['total_tokens']} "
                        f"('{topic_keyword}' <-> '{syllabus_title}')"
                    )
                    return SyllabusMatchDecision.model_validate_json(response.text or "{}")
                except Exception as inner_err:
                    last_err = inner_err
                    if "404" in str(inner_err) or "NOT_FOUND" in str(inner_err):
                        continue
                    logger.warning(f"[Syllabus Match AI] Model {model} failed: {inner_err}")
            raise RuntimeError(str(last_err))
        except Exception as err:
            logger.warning(f"[Syllabus Match AI] Confirmation failed ({err}); falling back to high-sim rule.")
            return SyllabusMatchDecision(is_match=False, confidence=0.0, reason=str(err))

    def match_subject_topics(
        self,
        subject_id: str,
        user_id: Optional[str] = None,
        refresh_cache: bool = True,
    ) -> MatchRunResponse:
        """
        Matches unlocked topics in a subject to syllabus_topics using:
          1. Embedding cosine similarity (D10)
          2. Exact/near-exact fast confirmation OR Gemini Flash-Lite confirmation (D09)
        Respects syllabus_match_locked = TRUE (Rule 13.2).
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, user_id, syllabus_subject_id FROM subjects WHERE id = %s;",
                (str(subject_id),),
            )
            subj = cursor.fetchone()
            if not subj:
                raise HTTPException(status_code=404, detail="Subject not found.")
            owner_id = str(subj["user_id"])
            if user_id and owner_id != str(user_id):
                raise HTTPException(status_code=404, detail="Subject not found or access denied.")

            syl_sub_id = subj.get("syllabus_subject_id")
            if not syl_sub_id:
                return MatchRunResponse(
                    subject_id=str(subject_id),
                    topics_evaluated=0,
                    matches_created=0,
                    coverage_percent=0.0,
                )

            cursor.execute(
                """
                SELECT id, module_no, title, embedding
                FROM syllabus_topics
                WHERE syllabus_subject_id = %s
                ORDER BY module_no ASC, title ASC;
                """,
                (str(syl_sub_id),),
            )
            syl_rows = cursor.fetchall() or []

            cursor.execute(
                """
                SELECT id, keyword, explanation, module_no, embedding, syllabus_topic_id, syllabus_match_locked
                FROM topics
                WHERE subject_id = %s
                  AND COALESCE(syllabus_match_locked, FALSE) = FALSE
                  AND syllabus_topic_id IS NULL;
                """,
                (str(subject_id),),
            )
            topic_rows = cursor.fetchall() or []

        if not syl_rows or not topic_rows:
            cov = self.get_subject_syllabus(user_id=owner_id, subject_id=subject_id).coverage_percent
            return MatchRunResponse(
                subject_id=str(subject_id),
                topics_evaluated=len(topic_rows),
                matches_created=0,
                coverage_percent=cov,
            )

        # Backfill any NULL syllabus embeddings cleanly so vector matching always works
        missing_emb = [s for s in syl_rows if s.get("embedding") is None]
        if missing_emb:
            try:
                vecs = self.embedding_service.generate_embeddings(
                    [f"Module {int(s.get('module_no') or 1)}: {s['title']}" for s in missing_emb]
                )
                if len(vecs) == len(missing_emb):
                    with get_db_cursor() as cursor:
                        for s, vec in zip(missing_emb, vecs):
                            emb_str = f"[{','.join(f'{x:.6f}' for x in vec)}]"
                            cursor.execute(
                                "UPDATE syllabus_topics SET embedding = %s::vector WHERE id = %s;",
                                (emb_str, str(s["id"])),
                            )
                            s["embedding"] = vec
            except Exception as emb_err:
                logger.warning(f"[Syllabus] Backfill embedding skipped: {emb_err}")

        # Parse embeddings
        syl_items = []
        for s in syl_rows:
            syl_items.append({
                "id": str(s["id"]),
                "module_no": int(s["module_no"] or 1),
                "title": s["title"],
                "norm": _normalize_title(s["title"]),
                "vec": _parse_pgvector(s.get("embedding")),
            })

        matches_to_save: List[Tuple[str, str]] = []
        for t in topic_rows:
            t_id = str(t["id"])
            t_kw = t["keyword"]
            t_norm = _normalize_title(t_kw)
            t_mod = int(t["module_no"] or 1)
            t_vec = _parse_pgvector(t.get("embedding"))

            scored_candidates: List[Tuple[float, float, Dict[str, Any], bool]] = []
            for s in syl_items:
                exact_text = bool(
                    t_norm and s["norm"] and (t_norm == s["norm"] or t_norm in s["norm"] or s["norm"] in t_norm)
                )
                sim = compute_cosine_similarity(t_vec, s["vec"]) if (t_vec and s["vec"]) else (0.95 if exact_text else 0.0)
                if exact_text or sim >= self.match_threshold:
                    # Prefer same module gently during ranking tie-break
                    rank_score = sim + (0.04 if s["module_no"] == t_mod else 0.0) + (0.05 if exact_text else 0.0)
                    scored_candidates.append((rank_score, sim, s, exact_text))

            if not scored_candidates:
                continue

            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_rank, best_sim, best_syl, is_exact = scored_candidates[0]

            confirmed = False
            if is_exact or best_sim >= self.auto_exact_threshold:
                confirmed = True
            else:
                decision = self._confirm_match_with_llm(
                    topic_keyword=t_kw,
                    topic_explanation=t["explanation"] or "",
                    topic_module_no=t_mod,
                    syllabus_title=best_syl["title"],
                    syllabus_module_no=best_syl["module_no"],
                )
                confirmed = bool(decision.is_match and decision.confidence >= 0.5)

            if confirmed:
                matches_to_save.append((best_syl["id"], t_id))

        if matches_to_save:
            with get_db_cursor() as cursor:
                for syl_topic_id, topic_id in matches_to_save:
                    cursor.execute(
                        """
                        UPDATE topics
                        SET syllabus_topic_id = %s
                        WHERE id = %s
                          AND COALESCE(syllabus_match_locked, FALSE) = FALSE;
                        """,
                        (syl_topic_id, topic_id),
                    )
            if refresh_cache:
                self._safe_refresh_graph(user_id=owner_id, subject_id=subject_id)

        updated_cov = self.get_subject_syllabus(user_id=owner_id, subject_id=subject_id).coverage_percent
        return MatchRunResponse(
            subject_id=str(subject_id),
            topics_evaluated=len(topic_rows),
            matches_created=len(matches_to_save),
            coverage_percent=updated_cov,
        )

    def get_subject_syllabus(self, user_id: str, subject_id: str) -> SubjectSyllabusResponse:
        """
        Returns syllabus metadata, all syllabus topics, matched topic links,
        per-module coverage percentages, and the list of uncovered gap topics.
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            pref = subj.get("source_preference") or "notes"
            if pref not in ("notes", "textbook"):
                pref = "notes"

            if not syl_sub_id:
                return SubjectSyllabusResponse(
                    subject_id=str(subject_id),
                    subject_name=subj["name"],
                    source_preference=pref,  # type: ignore
                    has_syllabus=False,
                )

            cursor.execute(
                """
                SELECT
                    ss.id AS syllabus_subject_id,
                    ss.code AS subject_code,
                    ss.semester,
                    ss.branch,
                    sc.id AS scheme_id,
                    sc.name AS scheme_name,
                    u.id AS university_id,
                    u.name AS university_name
                FROM syllabus_subjects ss
                JOIN schemes sc ON ss.scheme_id = sc.id
                JOIN universities u ON sc.university_id = u.id
                WHERE ss.id = %s;
                """,
                (str(syl_sub_id),),
            )
            meta_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT id, syllabus_subject_id, COALESCE(module_no, 1) AS module_no, title, parent_id, COALESCE(reviewed, FALSE) AS reviewed
                FROM syllabus_topics
                WHERE syllabus_subject_id = %s
                ORDER BY COALESCE(module_no, 1) ASC, title ASC;
                """,
                (str(syl_sub_id),),
            )
            syl_rows = cursor.fetchall() or []

            cursor.execute(
                """
                SELECT id, keyword, module_no, syllabus_topic_id, COALESCE(syllabus_match_locked, FALSE) AS syllabus_match_locked
                FROM topics
                WHERE subject_id = %s AND syllabus_topic_id IS NOT NULL
                ORDER BY keyword ASC;
                """,
                (str(subject_id),),
            )
            matched_rows = cursor.fetchall() or []

        matched_by_syl: Dict[str, List[MatchedTopicSummary]] = defaultdict(list)
        for t in matched_rows:
            matched_by_syl[str(t["syllabus_topic_id"])].append(
                MatchedTopicSummary(
                    topic_id=str(t["id"]),
                    keyword=t["keyword"],
                    module_no=t.get("module_no"),
                    syllabus_match_locked=bool(t.get("syllabus_match_locked")),
                )
            )

        items: List[SyllabusTopicItem] = []
        modules_bucket: Dict[int, List[SyllabusTopicItem]] = defaultdict(list)
        gaps: List[SyllabusTopicItem] = []
        covered_count = 0
        unreviewed_count = 0

        for s in syl_rows:
            sid = str(s["id"])
            m_list = matched_by_syl.get(sid, [])
            is_cov = len(m_list) > 0
            is_rev = bool(s.get("reviewed"))
            if is_cov:
                covered_count += 1
            if not is_rev:
                unreviewed_count += 1

            item = SyllabusTopicItem(
                id=sid,
                syllabus_subject_id=str(s["syllabus_subject_id"]),
                module_no=int(s["module_no"] or 1),
                title=s["title"],
                parent_id=str(s["parent_id"]) if s.get("parent_id") else None,
                reviewed=is_rev,
                is_covered=is_cov,
                matched_topics=m_list,
            )
            items.append(item)
            modules_bucket[item.module_no].append(item)
            if not is_cov:
                gaps.append(item)

        module_summaries: List[ModuleCoverageItem] = []
        for mod_no in sorted(modules_bucket.keys()):
            mod_items = modules_bucket[mod_no]
            mod_cov = [x for x in mod_items if x.is_covered]
            mod_gaps = [x for x in mod_items if not x.is_covered]
            pct = round((len(mod_cov) / len(mod_items)) * 100.0, 1) if mod_items else 0.0
            module_summaries.append(
                ModuleCoverageItem(
                    module_no=mod_no,
                    total_topics=len(mod_items),
                    covered_count=len(mod_cov),
                    gap_count=len(mod_gaps),
                    coverage_percent=pct,
                    covered_titles=[x.title for x in mod_cov],
                    gap_topics=mod_gaps,
                )
            )

        total_syl = len(items)
        overall_pct = round((covered_count / total_syl) * 100.0, 1) if total_syl else 0.0

        metadata = None
        if meta_row:
            metadata = SyllabusMetadata(
                syllabus_subject_id=str(meta_row["syllabus_subject_id"]),
                university_id=str(meta_row["university_id"]),
                university_name=meta_row["university_name"],
                scheme_id=str(meta_row["scheme_id"]),
                scheme_name=meta_row["scheme_name"],
                subject_code=meta_row["subject_code"],
                semester=meta_row.get("semester"),
                branch=meta_row.get("branch"),
            )

        return SubjectSyllabusResponse(
            subject_id=str(subject_id),
            subject_name=subj["name"],
            source_preference=pref,  # type: ignore
            has_syllabus=True,
            metadata=metadata,
            total_syllabus_topics=total_syl,
            covered_count=covered_count,
            gap_count=len(gaps),
            coverage_percent=overall_pct,
            unreviewed_count=unreviewed_count,
            syllabus_topics=items,
            modules=module_summaries,
            gaps=gaps,
        )

    def update_syllabus_topic(
        self,
        user_id: str,
        subject_id: str,
        syllabus_topic_id: str,
        title: Optional[str] = None,
        module_no: Optional[int] = None,
    ) -> SyllabusTopicItem:
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            if not syl_sub_id:
                raise HTTPException(status_code=404, detail="No syllabus linked to this subject.")

            cursor.execute(
                "SELECT id, module_no, title FROM syllabus_topics WHERE id = %s AND syllabus_subject_id = %s;",
                (str(syllabus_topic_id), str(syl_sub_id)),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Syllabus topic not found.")

            new_title = title.strip() if title is not None else row["title"]
            new_mod = module_no if module_no is not None else int(row["module_no"] or 1)

            emb_str = None
            if title is not None or module_no is not None:
                try:
                    vec = self.embedding_service.generate_single_embedding(f"Module {new_mod}: {new_title}")
                    emb_str = f"[{','.join(f'{x:.6f}' for x in vec)}]"
                except Exception as emb_err:
                    logger.warning(f"[Syllabus] Re-embed skipped on edit: {emb_err}")

            if emb_str:
                cursor.execute(
                    """
                    UPDATE syllabus_topics
                    SET title = %s, module_no = %s, embedding = %s::vector, reviewed = TRUE
                    WHERE id = %s;
                    """,
                    (new_title, new_mod, emb_str, str(syllabus_topic_id)),
                )
            else:
                cursor.execute(
                    """
                    UPDATE syllabus_topics
                    SET title = %s, module_no = %s, reviewed = TRUE
                    WHERE id = %s;
                    """,
                    (new_title, new_mod, str(syllabus_topic_id)),
                )

        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        full = self.get_subject_syllabus(user_id=user_id, subject_id=subject_id)
        for item in full.syllabus_topics:
            if item.id == str(syllabus_topic_id):
                return item
        raise HTTPException(status_code=404, detail="Syllabus topic not found after update.")

    def add_syllabus_topic(
        self,
        user_id: str,
        subject_id: str,
        title: str,
        module_no: int = 1,
    ) -> SyllabusTopicItem:
        clean_title = title.strip()
        emb_str = None
        try:
            vec = self.embedding_service.generate_single_embedding(f"Module {module_no}: {clean_title}")
            emb_str = f"[{','.join(f'{x:.6f}' for x in vec)}]"
        except Exception as emb_err:
            logger.warning(f"[Syllabus] Embed skipped on manual add: {emb_err}")

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            if not syl_sub_id:
                syl_sub_id = self._ensure_syllabus_subject_hierarchy(
                    cursor=cursor,
                    subject_row=subj,
                    university_name="Default University",
                    scheme_name="2022 Scheme",
                    subject_code=None,
                    semester=None,
                    branch=None,
                )

            cursor.execute(
                """
                INSERT INTO syllabus_topics (syllabus_subject_id, module_no, title, embedding, reviewed)
                VALUES (%s, %s, %s, %s::vector, TRUE)
                RETURNING id;
                """,
                (str(syl_sub_id), module_no, clean_title, emb_str),
            )
            new_id = str(cursor.fetchone()["id"])

        self.match_subject_topics(subject_id=subject_id, user_id=user_id, refresh_cache=False)
        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        full = self.get_subject_syllabus(user_id=user_id, subject_id=subject_id)
        for item in full.syllabus_topics:
            if item.id == new_id:
                return item
        raise HTTPException(status_code=500, detail="Created syllabus topic could not be reloaded.")

    def delete_syllabus_topic(self, user_id: str, subject_id: str, syllabus_topic_id: str) -> None:
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            if not syl_sub_id:
                raise HTTPException(status_code=404, detail="No syllabus linked to this subject.")

            cursor.execute(
                "UPDATE topics SET syllabus_topic_id = NULL, syllabus_match_locked = FALSE WHERE syllabus_topic_id = %s AND subject_id = %s;",
                (str(syllabus_topic_id), str(subject_id)),
            )
            cursor.execute(
                "DELETE FROM syllabus_topics WHERE id = %s AND syllabus_subject_id = %s;",
                (str(syllabus_topic_id), str(syl_sub_id)),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Syllabus topic not found.")

        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)

    def approve_all_syllabus_topics(self, user_id: str, subject_id: str) -> SubjectSyllabusResponse:
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            if not syl_sub_id:
                raise HTTPException(status_code=404, detail="No syllabus linked to this subject.")
            cursor.execute(
                "UPDATE syllabus_topics SET reviewed = TRUE WHERE syllabus_subject_id = %s;",
                (str(syl_sub_id),),
            )
        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        return self.get_subject_syllabus(user_id=user_id, subject_id=subject_id)

    def correct_topic_match(
        self,
        user_id: str,
        subject_id: str,
        topic_id: str,
        syllabus_topic_id: Optional[str],
    ) -> SubjectSyllabusResponse:
        """
        Allows the student to manually link, reassign, or unlink a note topic to/from
        a syllabus topic, locking the choice so auto-matching never overwrites it (Rule 13.2).
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")

            cursor.execute(
                "SELECT id FROM topics WHERE id = %s AND subject_id = %s;",
                (str(topic_id), str(subject_id)),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Topic not found in this subject.")

            if syllabus_topic_id is not None:
                if not syl_sub_id:
                    raise HTTPException(status_code=400, detail="Subject has no syllabus uploaded.")
                cursor.execute(
                    "SELECT id FROM syllabus_topics WHERE id = %s AND syllabus_subject_id = %s;",
                    (str(syllabus_topic_id), str(syl_sub_id)),
                )
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Target syllabus topic not found in this subject.")

            cursor.execute(
                """
                UPDATE topics
                SET syllabus_topic_id = %s,
                    syllabus_match_locked = TRUE
                WHERE id = %s AND subject_id = %s;
                """,
                (str(syllabus_topic_id) if syllabus_topic_id else None, str(topic_id), str(subject_id)),
            )

        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        return self.get_subject_syllabus(user_id=user_id, subject_id=subject_id)

    def update_source_preference(
        self,
        user_id: str,
        subject_id: str,
        source_preference: str,
    ) -> SubjectPreferenceResponse:
        """Updates per-subject source preference ('notes' or 'textbook') (Feature F17)."""
        if source_preference not in ("notes", "textbook"):
            raise HTTPException(status_code=400, detail="source_preference must be 'notes' or 'textbook'.")

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            cursor.execute(
                "UPDATE subjects SET source_preference = %s WHERE id = %s AND user_id = %s;",
                (source_preference, str(subject_id), str(user_id)),
            )

        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        label = "Lecture Notes" if source_preference == "notes" else "Textbook"
        return SubjectPreferenceResponse(
            subject_id=str(subject_id),
            subject_name=subj["name"],
            source_preference=source_preference,  # type: ignore
            message=f"Preferred source for '{subj['name']}' set to {label}.",
        )

    def reassign_syllabus(
        self,
        user_id: str,
        from_subject_id: str,
        target_subject_id: str,
    ) -> SubjectSyllabusResponse:
        """
        Moves a syllabus (syllabus_subject_id) from one subject owned by the student
        to another subject owned by the student, then re-runs matching and refreshes both graphs.
        """
        if str(from_subject_id) == str(target_subject_id):
            return self.get_subject_syllabus(user_id=user_id, subject_id=target_subject_id)

        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            src_subj = self._verify_subject_owner(cursor, from_subject_id, user_id)
            dst_subj = self._verify_subject_owner(cursor, target_subject_id, user_id)
            syl_sub_id = src_subj.get("syllabus_subject_id")
            if not syl_sub_id:
                raise HTTPException(status_code=400, detail="Source subject has no syllabus to move.")

            # Detach from source subject and reset its syllabus topic matches
            cursor.execute(
                "UPDATE topics SET syllabus_topic_id = NULL, syllabus_match_locked = FALSE WHERE subject_id = %s;",
                (str(from_subject_id),),
            )
            cursor.execute(
                "UPDATE subjects SET syllabus_subject_id = NULL WHERE id = %s;",
                (str(from_subject_id),),
            )
            # Attach to destination subject and update syllabus_subjects.name
            cursor.execute(
                "UPDATE topics SET syllabus_topic_id = NULL, syllabus_match_locked = FALSE WHERE subject_id = %s;",
                (str(target_subject_id),),
            )
            cursor.execute(
                "UPDATE subjects SET syllabus_subject_id = %s WHERE id = %s;",
                (str(syl_sub_id), str(target_subject_id)),
            )
            cursor.execute(
                "UPDATE syllabus_subjects SET name = %s WHERE id = %s;",
                (dst_subj["name"], str(syl_sub_id)),
            )

        self.match_subject_topics(subject_id=target_subject_id, user_id=user_id, refresh_cache=False)
        self._safe_refresh_graph(user_id=user_id, subject_id=from_subject_id)
        self._safe_refresh_graph(user_id=user_id, subject_id=target_subject_id)
        return self.get_subject_syllabus(user_id=user_id, subject_id=target_subject_id)

    def delete_syllabus(self, user_id: str, subject_id: str) -> Dict[str, Any]:
        """Unlinks and deletes the syllabus attached to a student's subject."""
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            subj = self._verify_subject_owner(cursor, subject_id, user_id)
            syl_sub_id = subj.get("syllabus_subject_id")
            cursor.execute(
                "UPDATE topics SET syllabus_topic_id = NULL, syllabus_match_locked = FALSE WHERE subject_id = %s;",
                (str(subject_id),),
            )
            cursor.execute(
                "UPDATE subjects SET syllabus_subject_id = NULL WHERE id = %s;",
                (str(subject_id),),
            )
            if syl_sub_id:
                cursor.execute("DELETE FROM syllabus_topics WHERE syllabus_subject_id = %s;", (str(syl_sub_id),))
                cursor.execute("DELETE FROM syllabus_subjects WHERE id = %s;", (str(syl_sub_id),))

        self._safe_refresh_graph(user_id=user_id, subject_id=subject_id)
        return {"subject_id": str(subject_id), "deleted": True}


syllabus_service = SyllabusService()

