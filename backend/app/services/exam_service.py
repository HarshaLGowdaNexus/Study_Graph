"""
Exam Mode Service for StudyGraph (Task T17).
Relies on:
  - Feature F18: Important concepts ranked by graph connectivity & coverage ('by graph importance').
  - Feature F19: Repeated questions parsed from uploaded papers ('from your uploaded papers').
  - Risk R05: Never fabricate repeated questions when no papers exist.
  - Decision D09: Google Gemini Flash / Flash-Lite for question parsing & pair confirmation.
  - Decision D10: Google text-embedding-004 (768-dim) for question similarity.
  - Decision D11: NetworkX for graph centrality and connected-component clustering.
"""

import json
import logging
import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from fastapi import HTTPException, status
from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.prompts.exam_paper_v1 import (
    EXAM_QUESTION_EXTRACTION_PROMPT,
    EXAM_QUESTION_PAIR_CONFIRM_PROMPT,
)
from backend.app.schemas.exam import (
    ExamOverviewResponse,
    ExamPaperItem,
    ExtractedQuestionItem,
    ImportantConceptItem,
    PaperDeleteResponse,
    PaperExtractionOutput,
    QuestionOccurrenceItem,
    QuestionPairJudgement,
    RepeatedQuestionCluster,
)
from backend.app.services.embedding_service import (
    EmbeddingService,
    compute_cosine_similarity,
)

logger = logging.getLogger(__name__)


def parse_pgvector(raw_vec: Any) -> Optional[List[float]]:
    """Parses a PostgreSQL vector column value (str or list) into a float list."""
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


def _fallback_parse_questions(full_text: str) -> PaperExtractionOutput:
    """
    Deterministic line/prefix parser used only if the LLM call fails or returns empty
    on non-empty paper text. Extracts numbered lines (Q1., 1., 1(a), etc.).
    """
    detected_year: Optional[int] = None
    year_match = re.search(r"\b(20[0-3]\d|199\d)\b", full_text)
    if year_match:
        detected_year = int(year_match.group(1))

    questions: List[ExtractedQuestionItem] = []
    # Match lines starting with Q1., Q.1, 1., 1(a), (a), etc.
    pattern = re.compile(
        r"^(?:Q(?:uestion)?\.?\s*\d+[a-zA-Z()]*[\).:\-\s]+|\d+\s*[a-zA-Z()]*[\).:\-\s]+)(.+)$",
        re.IGNORECASE,
    )
    marks_pattern = re.compile(r"[\[\(]\s*(\d{1,2})\s*(?:marks?|m)\s*[\]\)]", re.IGNORECASE)

    for raw_line in full_text.splitlines():
        line = raw_line.strip()
        if len(line) < 12:
            continue
        match = pattern.match(line)
        if not match:
            continue
        q_body = match.group(1).strip()
        marks_val: Optional[int] = None
        m_match = marks_pattern.search(q_body)
        if m_match:
            marks_val = int(m_match.group(1))
            q_body = marks_pattern.sub("", q_body).strip(" -:")
        if len(q_body) >= 8:
            questions.append(ExtractedQuestionItem(text=q_body, marks=marks_val))

    return PaperExtractionOutput(detected_year=detected_year, questions=questions)


class ExamService:
    """
    Handles Exam Mode analytics:
      1. Important Concepts ranked by graph centrality & module/source coverage.
      2. Paper Question Extraction, embedding, LLM repeat confirmation & clustering.
      3. Honest empty-state reporting and clean paper deletion.
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.extraction_model = settings.EXAM_QUESTION_MODEL
        self.confirm_model = settings.EXAM_CLUSTER_CONFIRM_MODEL
        self.temperature = settings.EXAM_QUESTION_TEMPERATURE
        self.similarity_threshold = settings.EXAM_QUESTION_SIMILARITY_THRESHOLD
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in .env.")
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _verify_subject_owner(self, cursor: Any, subject_id: str, user_id: str) -> str:
        """Enforces Rule 11 privacy: ensures subject belongs to current_user."""
        cursor.execute(
            "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;",
            (str(subject_id), str(user_id)),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or you do not have permission to access it.",
            )
        return row["name"] if isinstance(row, dict) else row[1]

    # --------------------------------------------------------------------------
    # 1. Important Concepts ("by graph importance") — Feature F18
    # --------------------------------------------------------------------------
    def compute_important_concepts(
        self,
        subject_id: str,
        user_id: str,
        limit: Optional[int] = None,
        cursor: Optional[Any] = None,
    ) -> List[ImportantConceptItem]:
        """
        Ranks topics in a subject using NetworkX graph connectivity (degree, weighted
        edge strength, degree centrality, betweenness centrality) and curriculum
        coverage (distinct modules reached + source chunk count).
        Always tagged 'by graph importance'.
        """
        top_n = limit or settings.EXAM_IMPORTANT_CONCEPTS_LIMIT

        def _query(cur: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            self._verify_subject_owner(cur, subject_id, user_id)
            cur.execute(
                """
                SELECT
                    t.id,
                    t.keyword,
                    t.explanation,
                    t.real_world_use,
                    t.module_no,
                    t.reviewed,
                    COUNT(DISTINCT ts.chunk_id) AS source_count
                FROM topics t
                LEFT JOIN topic_sources ts ON ts.topic_id = t.id
                WHERE t.subject_id = %s
                GROUP BY t.id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed
                ORDER BY t.keyword ASC;
                """,
                (str(subject_id),),
            )
            topic_rows = [dict(r) for r in (cur.fetchall() or [])]
            if not topic_rows:
                return [], []

            topic_ids = [str(t["id"]) for t in topic_rows]
            cur.execute(
                """
                SELECT id, topic_a, topic_b, strength, scope
                FROM edges
                WHERE status != 'deleted'
                  AND (topic_a = ANY(%s::uuid[]) OR topic_b = ANY(%s::uuid[]));
                """,
                (topic_ids, topic_ids),
            )
            edge_rows = [dict(r) for r in (cur.fetchall() or [])]
            return topic_rows, edge_rows

        if cursor is not None:
            topics, edges = _query(cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                topics, edges = _query(cur)

        if not topics:
            return []

        return self._rank_topics_by_graph(topics, edges, top_n)

    @staticmethod
    def _rank_topics_by_graph(
        topics: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        top_n: int,
    ) -> List[ImportantConceptItem]:
        """Pure computation helper for NetworkX centrality & coverage ranking."""
        topic_by_id: Dict[str, Dict[str, Any]] = {str(t["id"]): t for t in topics}
        subject_graph = nx.Graph()
        for tid in topic_by_id:
            subject_graph.add_node(tid)

        weighted_deg: Dict[str, int] = defaultdict(int)
        total_deg: Dict[str, int] = defaultdict(int)
        cross_links: Dict[str, int] = defaultdict(int)
        neighbor_modules: Dict[str, Set[int]] = defaultdict(set)

        for tid, t in topic_by_id.items():
            if t.get("module_no") is not None:
                neighbor_modules[tid].add(int(t["module_no"]))

        for edge in edges:
            u = str(edge["topic_a"])
            v = str(edge["topic_b"])
            strength = int(edge.get("strength") or 1)
            scope = edge.get("scope") or "same_subject"

            if u in topic_by_id:
                total_deg[u] += 1
                weighted_deg[u] += strength
                if scope == "cross_subject":
                    cross_links[u] += 1
                if v in topic_by_id and topic_by_id[v].get("module_no") is not None:
                    neighbor_modules[u].add(int(topic_by_id[v]["module_no"]))

            if v in topic_by_id:
                total_deg[v] += 1
                weighted_deg[v] += strength
                if scope == "cross_subject":
                    cross_links[v] += 1
                if u in topic_by_id and topic_by_id[u].get("module_no") is not None:
                    neighbor_modules[v].add(int(topic_by_id[u]["module_no"]))

            if u in topic_by_id and v in topic_by_id and u != v:
                subject_graph.add_edge(u, v, weight=strength)

        deg_centrality = nx.degree_centrality(subject_graph) if len(topic_by_id) > 1 else {}
        betweenness = (
            nx.betweenness_centrality(subject_graph, normalized=True)
            if len(topic_by_id) >= 3 and subject_graph.number_of_edges() > 0
            else {}
        )

        max_wdeg = max(weighted_deg.values(), default=1) or 1
        max_sources = max((int(t.get("source_count") or 0) for t in topics), default=1) or 1
        max_modules = max((len(neighbor_modules[tid]) for tid in topic_by_id), default=1) or 1

        ranked: List[ImportantConceptItem] = []
        for tid, t in topic_by_id.items():
            wdeg_norm = weighted_deg[tid] / max_wdeg
            cent_score = 0.7 * deg_centrality.get(tid, 0.0) + 0.3 * betweenness.get(tid, 0.0)
            connectivity_score = 0.65 * wdeg_norm + 0.35 * cent_score

            modules_cov = len(neighbor_modules[tid])
            src_cnt = int(t.get("source_count") or 0)
            coverage_score = 0.6 * (modules_cov / max_modules) + 0.4 * (src_cnt / max_sources)

            combined = round(0.60 * connectivity_score + 0.40 * coverage_score, 4)

            ranked.append(
                ImportantConceptItem(
                    topic_id=tid,
                    keyword=t["keyword"],
                    explanation=t["explanation"],
                    real_world_use=t.get("real_world_use"),
                    module_no=t.get("module_no"),
                    reviewed=bool(t.get("reviewed")),
                    importance_score=min(1.0, max(0.0, combined)),
                    degree=total_deg[tid],
                    weighted_degree=weighted_deg[tid],
                    modules_covered=modules_cov,
                    source_count=src_cnt,
                    cross_subject_links=cross_links[tid],
                    label="by graph importance",
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.importance_score,
                -item.weighted_degree,
                -item.modules_covered,
                -item.source_count,
                item.keyword.lower(),
            )
        )
        return ranked[:top_n]

    # --------------------------------------------------------------------------
    # 2. Question Paper Extraction, Embedding & Repeat Clustering — Feature F19
    # --------------------------------------------------------------------------
    def extract_questions_from_pages(
        self,
        pages: List[Tuple[int, str]],
        filename: str,
    ) -> PaperExtractionOutput:
        """
        Extracts structured exam questions from extracted paper pages using Gemini Flash
        (Decision D09), logging token usage (Rule 11). Falls back to deterministic parsing
        if the API is temporarily unavailable.
        """
        combined_pages = "\n\n".join(
            f"--- Page {page_no} ---\n{text.strip()}"
            for page_no, text in pages
            if text and text.strip()
        ).strip()

        if not combined_pages:
            return PaperExtractionOutput(detected_year=None, questions=[])

        prompt = (
            f"Filename: {filename}\n\n"
            f"Raw Question Paper Text:\n{combined_pages}\n\n"
            "Extract every individual exam question and its marks if stated."
        )

        try:
            client = self._get_client()
            models_to_try = [self.extraction_model, "gemini-2.5-flash", "gemini-1.5-flash"]
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                system_instruction=EXAM_QUESTION_EXTRACTION_PROMPT,
                response_mime_type="application/json",
                response_schema=PaperExtractionOutput,
            )

            for attempt in range(1, 3):
                for model in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=config,
                        )
                        tokens = {"prompt": 0, "output": 0, "total": 0}
                        if response.usage_metadata:
                            tokens["prompt"] = response.usage_metadata.prompt_token_count or 0
                            tokens["output"] = response.usage_metadata.candidates_token_count or 0
                            tokens["total"] = response.usage_metadata.total_token_count or 0
                        logger.info(
                            f"[Exam Paper Extraction] Model: {model} | File: {filename} | "
                            f"Tokens: {tokens['total']} (Prompt: {tokens['prompt']}, Output: {tokens['output']})"
                        )
                        parsed = PaperExtractionOutput.model_validate_json(response.text)
                        if parsed.questions:
                            return parsed
                    except Exception as err:
                        logger.warning(
                            f"[Exam Paper Extraction] Model {model} attempt {attempt} failed: {err}"
                        )
                        time.sleep(1.0)
        except Exception as outer_err:
            logger.warning(f"[Exam Paper Extraction] Falling back to regex parser: {outer_err}")

        return _fallback_parse_questions(combined_pages)

    def _confirm_question_pair(
        self,
        question_a: str,
        question_b: str,
    ) -> QuestionPairJudgement:
        """
        Uses Gemini Flash-Lite (Decision D09) to confirm whether two candidate
        questions with high embedding similarity really ask the same exam question.
        """
        prompt = (
            f"Question A: \"{question_a}\"\n"
            f"Question B: \"{question_b}\"\n\n"
            "Do Question A and Question B ask essentially the same underlying exam question?"
        )
        try:
            client = self._get_client()
            models_to_try = [self.confirm_model, "gemini-2.5-flash", "gemini-1.5-flash"]
            config = types.GenerateContentConfig(
                temperature=0.0,
                system_instruction=EXAM_QUESTION_PAIR_CONFIRM_PROMPT,
                response_mime_type="application/json",
                response_schema=QuestionPairJudgement,
            )
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config,
                    )
                    total_tokens = (
                        response.usage_metadata.total_token_count
                        if response.usage_metadata
                        else 0
                    )
                    logger.info(
                        f"[Exam Question Confirm] Model: {model} | Tokens: {total_tokens}"
                    )
                    return QuestionPairJudgement.model_validate_json(response.text)
                except Exception as err:
                    logger.warning(f"[Exam Question Confirm] Model {model} failed: {err}")
                    time.sleep(0.5)
        except Exception as outer_err:
            logger.warning(f"[Exam Question Confirm] LLM unavailable: {outer_err}")

        return QuestionPairJudgement(
            is_same_question=False,
            confidence=0.0,
            canonical_question="",
            reason="Confirmation unavailable",
        )

    def ingest_paper_document(
        self,
        document_id: str,
        subject_id: str,
        filename: str,
        pages: List[Tuple[int, str]],
        year: Optional[int] = None,
        cursor: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Extracts exam questions from a paper document, generates 768-dim embeddings,
        persists exam_papers + exam_questions, links matching topics if close,
        and re-clusters repeated questions across all papers in the subject.
        """
        extraction = self.extract_questions_from_pages(pages=pages, filename=filename)
        resolved_year = year or extraction.detected_year
        if resolved_year is None:
            m = re.search(r"(20[0-3]\d|199\d)", filename)
            if m:
                resolved_year = int(m.group(1))

        questions = extraction.questions
        embeddings: List[List[float]] = []
        if questions:
            embeddings = self.embedding_service.generate_embeddings([q.text for q in questions])

        def _persist(cur: Any) -> str:
            cur.execute(
                "SELECT id FROM exam_papers WHERE document_id = %s;",
                (str(document_id),),
            )
            existing = cur.fetchone()
            if existing:
                paper_id = str(existing["id"] if isinstance(existing, dict) else existing[0])
                cur.execute(
                    "UPDATE exam_papers SET year = COALESCE(%s, year) WHERE id = %s;",
                    (resolved_year, paper_id),
                )
                cur.execute("DELETE FROM exam_questions WHERE paper_id = %s;", (paper_id,))
            else:
                cur.execute(
                    """
                    INSERT INTO exam_papers (subject_id, year, document_id)
                    VALUES (%s, %s, %s)
                    RETURNING id;
                    """,
                    (str(subject_id), resolved_year, str(document_id)),
                )
                row = cur.fetchone()
                paper_id = str(row["id"] if isinstance(row, dict) else row[0])

            # Load subject topic embeddings for optional topic matching
            cur.execute(
                "SELECT id, embedding FROM topics WHERE subject_id = %s AND embedding IS NOT NULL;",
                (str(subject_id),),
            )
            topic_vecs: List[Tuple[str, List[float]]] = []
            for trow in cur.fetchall() or []:
                tid = str(trow["id"] if isinstance(trow, dict) else trow[0])
                vec = parse_pgvector(trow["embedding"] if isinstance(trow, dict) else trow[1])
                if vec:
                    topic_vecs.append((tid, vec))

            for idx, q in enumerate(questions):
                vec = embeddings[idx] if idx < len(embeddings) else None
                emb_str = f"[{','.join(f'{x:.6f}' for x in vec)}]" if vec else None

                matched_topic_id: Optional[str] = None
                if vec and topic_vecs:
                    best_tid, best_sim = max(
                        ((tid, compute_cosine_similarity(vec, tvec)) for tid, tvec in topic_vecs),
                        key=lambda pair: pair[1],
                    )
                    if best_sim >= 0.70:
                        matched_topic_id = best_tid

                cur.execute(
                    """
                    INSERT INTO exam_questions (paper_id, text, marks, canonical_question, topic_id, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s::vector);
                    """,
                    (paper_id, q.text, q.marks, q.text, matched_topic_id, emb_str),
                )
            return paper_id

        if cursor is not None:
            paper_id = _persist(cursor)
            cluster_count = self.recluster_subject_questions(subject_id, cursor=cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                paper_id = _persist(cur)
                cluster_count = self.recluster_subject_questions(subject_id, cursor=cur)

        return {
            "paper_id": paper_id,
            "year": resolved_year,
            "questions_extracted": len(questions),
            "clusters_count": cluster_count,
        }

    def recluster_subject_questions(
        self,
        subject_id: str,
        cursor: Optional[Any] = None,
    ) -> int:
        """
        Groups semantically similar questions across uploaded papers in the subject
        using 768-dim cosine similarity + Gemini confirmation, then writes cluster_key
        and canonical_question back to exam_questions.
        """

        def _load(cur: Any) -> List[Dict[str, Any]]:
            cur.execute(
                """
                SELECT eq.id, eq.paper_id, eq.text, eq.marks, eq.embedding
                FROM exam_questions eq
                JOIN exam_papers ep ON ep.id = eq.paper_id
                WHERE ep.subject_id = %s
                ORDER BY ep.year ASC NULLS LAST, eq.id ASC;
                """,
                (str(subject_id),),
            )
            return [dict(r) for r in (cur.fetchall() or [])]

        def _save_updates(cur: Any, updates: List[Tuple[str, str, str]]) -> None:
            for cluster_key, canonical_q, qid in updates:
                cur.execute(
                    """
                    UPDATE exam_questions
                    SET cluster_key = %s,
                        canonical_question = %s
                    WHERE id = %s;
                    """,
                    (cluster_key, canonical_q, qid),
                )

        if cursor is not None:
            rows = _load(cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                rows = _load(cur)

        if not rows:
            return 0

        vectors: Dict[str, Optional[List[float]]] = {
            str(r["id"]): parse_pgvector(r.get("embedding")) for r in rows
        }
        q_by_id: Dict[str, Dict[str, Any]] = {str(r["id"]): r for r in rows}

        # Build graph of confirmed equivalent questions across DIFFERENT papers
        q_graph = nx.Graph()
        for qid in q_by_id:
            q_graph.add_node(qid)

        qids = list(q_by_id.keys())
        canonical_suggestions: Dict[Tuple[str, str], str] = {}

        for i in range(len(qids)):
            id_a = qids[i]
            vec_a = vectors.get(id_a)
            if not vec_a:
                continue
            for j in range(i + 1, len(qids)):
                id_b = qids[j]
                if str(q_by_id[id_a]["paper_id"]) == str(q_by_id[id_b]["paper_id"]):
                    continue
                vec_b = vectors.get(id_b)
                if not vec_b:
                    continue

                sim = compute_cosine_similarity(vec_a, vec_b)
                if sim >= self.similarity_threshold:
                    judgement = self._confirm_question_pair(
                        q_by_id[id_a]["text"],
                        q_by_id[id_b]["text"],
                    )
                    if judgement.is_same_question:
                        q_graph.add_edge(id_a, id_b)
                        if judgement.canonical_question.strip():
                            canonical_suggestions[(id_a, id_b)] = judgement.canonical_question.strip()

        updates: List[Tuple[str, str, str]] = []
        components = list(nx.connected_components(q_graph))
        cluster_idx = 0
        for comp in components:
            comp_ids = sorted(comp)
            if len(comp_ids) == 1:
                qid = comp_ids[0]
                updates.append((f"single_{qid}", q_by_id[qid]["text"], qid))
            else:
                cluster_idx += 1
                cluster_key = f"cluster_{cluster_idx}"
                # Pick first LLM canonical suggestion inside this component, else shortest clean text
                canonical_text = ""
                for u, v in q_graph.subgraph(comp_ids).edges():
                    canonical_text = (
                        canonical_suggestions.get((u, v))
                        or canonical_suggestions.get((v, u))
                        or ""
                    )
                    if canonical_text:
                        break
                if not canonical_text:
                    canonical_text = min((q_by_id[qid]["text"] for qid in comp_ids), key=len)

                for qid in comp_ids:
                    updates.append((cluster_key, canonical_text, qid))

        if cursor is not None:
            _save_updates(cursor, updates)
        else:
            with get_db_cursor() as cur:
                _save_updates(cur, updates)

        return len(components)

    # --------------------------------------------------------------------------
    # 3. Exam Mode Overview & Paper Management (Delete)
    # --------------------------------------------------------------------------
    def get_exam_overview(
        self,
        subject_id: str,
        user_id: str,
        cursor: Optional[Any] = None,
    ) -> ExamOverviewResponse:
        """
        Returns the full Exam Mode overview for a subject:
          - Important concepts ('by graph importance')
          - Uploaded papers and repeated questions ('from your uploaded papers')
          - Honest empty-state notice if no papers exist (Risk R05)
        """

        def _fetch(cur: Any) -> Tuple[str, List[ImportantConceptItem], List[Dict[str, Any]], List[Dict[str, Any]]]:
            subject_name = self._verify_subject_owner(cur, subject_id, user_id)
            concepts = self.compute_important_concepts(subject_id, user_id, cursor=cur)

            cur.execute(
                """
                SELECT
                    ep.id AS paper_id,
                    ep.document_id,
                    ep.year,
                    d.filename,
                    d.status,
                    d.uploaded_at,
                    COUNT(eq.id) AS question_count
                FROM exam_papers ep
                JOIN documents d ON d.id = ep.document_id
                LEFT JOIN exam_questions eq ON eq.paper_id = ep.id
                WHERE ep.subject_id = %s
                GROUP BY ep.id, ep.document_id, ep.year, d.filename, d.status, d.uploaded_at
                ORDER BY ep.year DESC NULLS LAST, d.uploaded_at DESC;
                """,
                (str(subject_id),),
            )
            paper_rows = [dict(r) for r in (cur.fetchall() or [])]

            question_rows: List[Dict[str, Any]] = []
            if paper_rows:
                cur.execute(
                    """
                    SELECT
                        eq.id AS question_id,
                        eq.paper_id,
                        eq.text,
                        eq.marks,
                        eq.cluster_key,
                        eq.canonical_question,
                        eq.topic_id,
                        t.keyword AS matched_topic_keyword,
                        ep.year,
                        d.filename
                    FROM exam_questions eq
                    JOIN exam_papers ep ON ep.id = eq.paper_id
                    JOIN documents d ON d.id = ep.document_id
                    LEFT JOIN topics t ON t.id = eq.topic_id
                    WHERE ep.subject_id = %s
                    ORDER BY ep.year DESC NULLS LAST, d.filename ASC, eq.id ASC;
                    """,
                    (str(subject_id),),
                )
                question_rows = [dict(r) for r in (cur.fetchall() or [])]

            return subject_name, concepts, paper_rows, question_rows

        if cursor is not None:
            subject_name, concepts, paper_rows, question_rows = _fetch(cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                subject_name, concepts, paper_rows, question_rows = _fetch(cur)

        papers = [
            ExamPaperItem(
                id=str(p["paper_id"]),
                document_id=str(p["document_id"]),
                filename=p["filename"],
                year=p.get("year"),
                status=p.get("status") or "done",
                question_count=int(p.get("question_count") or 0),
                uploaded_at=str(p["uploaded_at"]) if p.get("uploaded_at") else None,
            )
            for p in paper_rows
        ]

        total_papers = len(papers)
        if total_papers == 0:
            return ExamOverviewResponse(
                subject_id=str(subject_id),
                subject_name=subject_name,
                important_concepts_label="by graph importance",
                important_concepts=concepts,
                repeated_questions_label="from your uploaded papers",
                has_uploaded_papers=False,
                total_papers=0,
                total_questions=0,
                honest_notice=(
                    "No previous-year papers uploaded yet for this subject. "
                    "Upload past question papers to detect repeated questions — we never invent or guess exam repeats."
                ),
                papers=[],
                repeated_questions=[],
            )

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for q in question_rows:
            key = q.get("cluster_key") or f"single_{q['question_id']}"
            grouped[key].append(q)

        clusters: List[RepeatedQuestionCluster] = []
        for cluster_key, items in grouped.items():
            distinct_paper_ids = {str(it["paper_id"]) for it in items}
            repeat_count = len(distinct_paper_ids)
            canonical = next(
                (it["canonical_question"] for it in items if it.get("canonical_question")),
                items[0]["text"],
            )
            marks_list = [int(it["marks"]) for it in items if it.get("marks") is not None]
            typical_marks = Counter(marks_list).most_common(1)[0][0] if marks_list else None
            matched_topic_id = next(
                (str(it["topic_id"]) for it in items if it.get("topic_id")),
                None,
            )
            matched_topic_kw = next(
                (it["matched_topic_keyword"] for it in items if it.get("matched_topic_keyword")),
                None,
            )

            occurrences = [
                QuestionOccurrenceItem(
                    question_id=str(it["question_id"]),
                    paper_id=str(it["paper_id"]),
                    filename=it["filename"],
                    year=it.get("year"),
                    text=it["text"],
                    marks=it.get("marks"),
                )
                for it in items
            ]

            clusters.append(
                RepeatedQuestionCluster(
                    cluster_key=cluster_key,
                    canonical_question=canonical,
                    repeat_count=repeat_count,
                    total_papers=total_papers,
                    typical_marks=typical_marks,
                    matched_topic_id=matched_topic_id,
                    matched_topic_keyword=matched_topic_kw,
                    label="from your uploaded papers",
                    occurrences=occurrences,
                )
            )

        clusters.sort(
            key=lambda c: (-c.repeat_count, -len(c.occurrences), c.canonical_question.lower())
        )

        repeated_2_plus = sum(1 for c in clusters if c.repeat_count >= 2)
        honest_notice: Optional[str] = None
        if repeated_2_plus == 0:
            honest_notice = (
                f"Analyzed {total_papers} uploaded paper(s) ({len(question_rows)} question(s) parsed). "
                "No question repeated across 2 or more uploaded papers yet."
            )

        return ExamOverviewResponse(
            subject_id=str(subject_id),
            subject_name=subject_name,
            important_concepts_label="by graph importance",
            important_concepts=concepts,
            repeated_questions_label="from your uploaded papers",
            has_uploaded_papers=True,
            total_papers=total_papers,
            total_questions=len(question_rows),
            honest_notice=honest_notice,
            papers=papers,
            repeated_questions=clusters,
        )

    def delete_paper(
        self,
        subject_id: str,
        paper_id: str,
        user_id: str,
        cursor: Optional[Any] = None,
    ) -> Tuple[PaperDeleteResponse, Optional[str]]:
        """
        Deletes a previous-year paper (and its document/questions via ON DELETE CASCADE)
        after verifying user ownership, then re-clusters remaining papers.
        Returns (PaperDeleteResponse, storage_path_to_cleanup).
        """

        def _delete(cur: Any) -> Tuple[str, Optional[str], int]:
            self._verify_subject_owner(cur, subject_id, user_id)
            cur.execute(
                """
                SELECT ep.id AS paper_id, ep.document_id, d.storage_path
                FROM exam_papers ep
                JOIN documents d ON d.id = ep.document_id
                WHERE ep.id = %s AND ep.subject_id = %s;
                """,
                (str(paper_id), str(subject_id)),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Exam paper not found in this subject.",
                )

            document_id = str(row["document_id"] if isinstance(row, dict) else row[1])
            storage_path = row["storage_path"] if isinstance(row, dict) else row[2]

            # Deleting document cascades to exam_papers, exam_questions, and chunks
            cur.execute("DELETE FROM documents WHERE id = %s;", (document_id,))

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM exam_papers WHERE subject_id = %s;",
                (str(subject_id),),
            )
            cnt_row = cur.fetchone()
            remaining = int(cnt_row["cnt"] if isinstance(cnt_row, dict) else cnt_row[0])

            if remaining > 0:
                self.recluster_subject_questions(subject_id, cursor=cur)

            return document_id, storage_path, remaining

        if cursor is not None:
            document_id, storage_path, remaining = _delete(cursor)
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                document_id, storage_path, remaining = _delete(cur)

        resp = PaperDeleteResponse(
            status="deleted",
            paper_id=str(paper_id),
            document_id=document_id,
            remaining_papers=remaining,
            message="Uploaded paper removed and repeat counts updated.",
        )
        return resp, storage_path


exam_service = ExamService()

