"""
Chat Service for StudyGraph (Task T13).
Relies on:
  - Feature F14: Chatbot with citations + 'not in your notes' + labeled fallback.
  - Risk R10: Anti-hallucination guard and strict grounding.
  - Risk R11: Privacy rule - students only access their own notes and subjects.
  - RULEBOOK 13.4: Chatbot honesty rules.
  - Decision D05: pgvector similarity retrieval from chunks table.
  - Decision D09: Google Gemini Flash for grounded reasoning and fallback.
  - Decision D10: Google text-embedding-004 for question embeddings.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.schemas.chat import (
    ChatAnswerResponse,
    ChatHistoryResponse,
    ChatMessageHistoryItem,
    CitationItem,
)
from backend.app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class ChatService:
    """
    RAG Chatbot Service that retrieves note chunks, scores retrieval confidence,
    generates grounded answers with exact citations, or refuses to bluff with a
    clearly labeled 'Not found in your notes' notice.
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.model_name = settings.CHAT_MODEL
        self.temperature = settings.CHAT_TEMPERATURE
        self.confidence_threshold = settings.CHAT_CONFIDENCE_THRESHOLD
        self.top_k = settings.CHAT_TOP_K
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Initializes or returns the Gemini client with the configured API key."""
        if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not configured in .env.\n"
                "Please add your Google AI Studio key: GEMINI_API_KEY=AIzaSy..."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _generate_with_retry(
        self, prompt: str, system_instruction: Optional[str] = None
    ) -> Tuple[str, Dict[str, int]]:
        """
        Calls Gemini Flash with backoff retries and extracts token usage (Rule 11).
        """
        client = self._get_client()
        models_to_try = [self.model_name, "gemini-2.5-flash", "gemini-1.5-flash"]
        last_error = None

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=system_instruction,
        )

        for attempt in range(1, 4):
            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config,
                    )

                    tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    if response.usage_metadata:
                        tokens["prompt_tokens"] = response.usage_metadata.prompt_token_count or 0
                        tokens["completion_tokens"] = response.usage_metadata.candidates_token_count or 0
                        tokens["total_tokens"] = response.usage_metadata.total_token_count or 0

                    logger.info(
                        f"[Chatbot AI Call] Model: {model} | Tokens: {tokens['total_tokens']} "
                        f"(Prompt: {tokens['prompt_tokens']}, Output: {tokens['completion_tokens']})"
                    )

                    raw_text = response.text or ""
                    return raw_text, tokens

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[Chatbot] Model {model} attempt {attempt} failed: {e}. Retrying with backoff..."
                    )
                    time.sleep(1.0)

            time.sleep(1.5)

        raise RuntimeError(f"Chat generation failed after 3 attempts. Last error: {last_error}")

    def retrieve_chunks(
        self,
        user_id: str,
        subject_id: str,
        query_embedding: List[float],
        top_k: Optional[int] = None,
        cursor: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top-K nearest document chunks for this subject and user using pgvector cosine distance.
        Strictly enforces user privacy (Rule 11 / Risk R11): documents and subject must belong to user_id.
        """
        limit_k = top_k or self.top_k
        emb_str = f"[{','.join(f'{x:.6f}' for x in query_embedding)}]"

        query = """
            SELECT 
                c.id AS chunk_id,
                c.document_id,
                c.page,
                c.text,
                d.filename,
                d.source_kind,
                (1.0 - (c.embedding <=> %s::vector)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN subjects s ON s.id = d.subject_id
            WHERE s.id = %s
              AND s.user_id = %s
              AND d.source_kind != 'paper'
              AND c.embedding IS NOT NULL
            ORDER BY (c.embedding <=> %s::vector) ASC
            LIMIT %s;
        """

        if cursor is not None:
            cursor.execute(query, (emb_str, str(subject_id), str(user_id), emb_str, limit_k))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

        with get_db_cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (emb_str, str(subject_id), str(user_id), emb_str, limit_k))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _get_marks_formatting_instructions(marks: Optional[int]) -> str:
        """
        Returns explicit exam answer structure & length instructions for 2, 5, or 10 marks
        (Feature F20).
        """
        if marks == 2:
            return (
                "EXAM FORMAT (2 Marks): Write strictly 1 to 2 concise, high-yield lines "
                "(max ~40 words). Do NOT use headings or bullet lists. Give the direct definition or key point."
            )
        if marks == 5:
            return (
                "EXAM FORMAT (5 Marks): Write a 1-sentence overview followed by 3 to 5 short, "
                "structured bullet points covering the core steps, properties, or differences (~80-150 words)."
            )
        if marks == 10:
            return (
                "EXAM FORMAT (10 Marks): Write a comprehensive, structured university exam answer "
                "using clear Markdown headings (for example: ### Overview & Definition, "
                "### Core Mechanism / Architecture, ### Example / Real-World Use, ### Key Takeaways) "
                "with detailed explanation under each heading (~220-400 words)."
            )
        return "Keep it structured, scannable, and helpful for revision."

    def ask_question(
        self,
        user_id: str,
        subject_id: str,
        question: str,
        marks: Optional[int] = None,
        cursor: Optional[Any] = None,
    ) -> ChatAnswerResponse:
        """
        Main RAG pipeline:
        1. Verifies subject belongs to user.
        2. Embeds question with text-embedding-004.
        3. Retrieves top chunks using pgvector.
        4. Compares top similarity against CHAT_CONFIDENCE_THRESHOLD (default 0.60).
        5. Answers from chunks with citations or provides labeled fallback with 'Not found in your notes'.
        6. Persists conversation in chat_messages table.
        """
        clean_question = question.strip()
        if not clean_question:
            raise HTTPException(status_code=400, detail="Question cannot be empty.")

        # 1. Verify user ownership of the subject
        subject_query = "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;"
        if cursor is not None:
            cursor.execute(subject_query, (str(subject_id), str(user_id)))
            subject_row = cursor.fetchone()
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(subject_query, (str(subject_id), str(user_id)))
                subject_row = cur.fetchone()

        if not subject_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or does not belong to your account (Rule 11).",
            )

        subject_name = subject_row["name"]

        # 2. Embed the question
        query_vector = self.embedding_service.generate_single_embedding(clean_question)

        # 3. Retrieve closest chunks
        retrieved_chunks = self.retrieve_chunks(
            user_id=user_id,
            subject_id=subject_id,
            query_embedding=query_vector,
            top_k=self.top_k,
            cursor=cursor,
        )

        top_similarity = float(retrieved_chunks[0]["similarity"]) if retrieved_chunks else 0.0
        logger.info(
            f"[Chatbot] Subject: {subject_name} | Question: '{clean_question[:50]}...' | "
            f"Top similarity: {top_similarity:.4f} (Threshold: {self.confidence_threshold})"
        )

        citations: List[CitationItem] = []
        answered_from: str = "notes"
        answer_text: str = ""

        # 4. Check confidence threshold
        marks_instruction = self._get_marks_formatting_instructions(marks)

        if not retrieved_chunks or top_similarity < self.confidence_threshold:
            # Low confidence: Topic is NOT in the student's notes
            logger.info("[Chatbot] Retrieval similarity below threshold. Triggering honest fallback.")
            general_prompt = (
                f"A student studying '{subject_name}' asked the following question:\n"
                f"\"{clean_question}\"\n\n"
                f"Explain this concept clearly and educationally for a university exam.\n"
                f"{marks_instruction}"
            )
            raw_gen, _ = self._generate_with_retry(
                prompt=general_prompt,
                system_instruction="You are an honest university tutor providing a clear general-knowledge explanation.",
            )
            answer_text = f"Not found in your notes.\n\n### General Knowledge Answer\n{raw_gen.strip()}"
            answered_from = "general"
            citations = []

        else:
            # Chunks exist with sufficient similarity. Pass to Gemini Flash with strict grounding instructions
            formatted_chunks = []
            for idx, ch in enumerate(retrieved_chunks, 1):
                formatted_chunks.append(
                    f"--- [Excerpt {idx} - File: {ch['filename']} | Page: {ch['page']}] ---\n"
                    f"{ch['text']}\n"
                )
            context_str = "\n".join(formatted_chunks)

            grounded_prompt = (
                f"Student's Study Question:\n\"{clean_question}\"\n\n"
                f"Verified Excerpts from the student's notes for '{subject_name}':\n"
                f"{context_str}\n\n"
                f"Strict Grounding Rules:\n"
                f"1. Check if the provided excerpts actually explain or directly answer the question.\n"
                f"2. If the excerpts DO NOT contain the answer (e.g. only passing mentions of similar keywords without the needed facts), reply EXACTLY:\n"
                f"NOT_FOUND_IN_NOTES: <write a helpful general knowledge explanation following this format: {marks_instruction}>\n"
                f"3. If the excerpts DO contain the answer:\n"
                f"   - Explain the answer clearly using ONLY the facts from the excerpts.\n"
                f"   - Do NOT invent outside details or pretend facts were in the text if they were not.\n"
                f"   - {marks_instruction}"
            )

            raw_resp, _ = self._generate_with_retry(
                prompt=grounded_prompt,
                system_instruction=(
                    "You are StudyGraph's grounded study assistant. You answer strictly from student notes "
                    "and refuse to bluff. If notes do not have the answer, output NOT_FOUND_IN_NOTES: followed by a general answer."
                ),
            )

            if raw_resp.strip().startswith("NOT_FOUND_IN_NOTES:"):
                # LLM determined excerpts do not contain the answer
                general_body = raw_resp.strip()[len("NOT_FOUND_IN_NOTES:"):].strip()
                answer_text = f"Not found in your notes.\n\n### General Knowledge Answer\n{general_body}"
                answered_from = "general"
                citations = []
            else:
                answer_text = raw_resp.strip()
                answered_from = "notes"

                # Extract citations from relevant chunks
                for ch in retrieved_chunks:
                    # Chunks that are sufficiently close to the query
                    if ch["similarity"] >= max(0.48, self.confidence_threshold - 0.08):
                        raw_snippet = ch["text"].strip().replace("\n", " ")
                        snippet_clean = raw_snippet[:260].strip() + ("..." if len(raw_snippet) > 260 else "")
                        citations.append(
                            CitationItem(
                                document_id=str(ch["document_id"]),
                                filename=ch["filename"],
                                page=int(ch["page"]),
                                snippet=snippet_clean,
                                similarity=round(float(ch["similarity"]), 4),
                            )
                        )
                        if len(citations) >= 3:
                            break

                # Fallback: ensure at least the top chunk is cited if answered from notes
                if not citations and retrieved_chunks:
                    top_ch = retrieved_chunks[0]
                    raw_snippet = top_ch["text"].strip().replace("\n", " ")
                    snippet_clean = raw_snippet[:260].strip() + ("..." if len(raw_snippet) > 260 else "")
                    citations.append(
                        CitationItem(
                            document_id=str(top_ch["document_id"]),
                            filename=top_ch["filename"],
                            page=int(top_ch["page"]),
                            snippet=snippet_clean,
                            similarity=round(float(top_ch["similarity"]), 4),
                        )
                    )

        # 5. Persist both the user message and assistant message to chat_messages table
        citations_json = json.dumps([c.model_dump() for c in citations]) if citations else None

        insert_user_sql = """
            INSERT INTO chat_messages (user_id, subject_id, role, text, citations_json, answered_from)
            VALUES (%s, %s, 'user', %s, NULL, NULL);
        """
        insert_assistant_sql = """
            INSERT INTO chat_messages (user_id, subject_id, role, text, citations_json, answered_from)
            VALUES (%s, %s, 'assistant', %s, %s, %s)
            RETURNING id, created_at;
        """

        if cursor is not None:
            cursor.execute(insert_user_sql, (str(user_id), str(subject_id), clean_question))
            cursor.execute(
                insert_assistant_sql,
                (str(user_id), str(subject_id), answer_text, citations_json, answered_from),
            )
            saved = cursor.fetchone()
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(insert_user_sql, (str(user_id), str(subject_id), clean_question))
                cur.execute(
                    insert_assistant_sql,
                    (str(user_id), str(subject_id), answer_text, citations_json, answered_from),
                )
                saved = cur.fetchone()

        message_id = str(saved["id"])
        created_at = saved["created_at"]

        return ChatAnswerResponse(
            id=message_id,
            subject_id=str(subject_id),
            role="assistant",
            text=answer_text,
            marks=marks,
            answered_from=answered_from,  # type: ignore
            confidence=round(top_similarity, 4),
            citations=citations,
            created_at=created_at,
        )

    def get_history(
        self,
        user_id: str,
        subject_id: str,
        limit: int = 50,
        cursor: Optional[Any] = None,
    ) -> ChatHistoryResponse:
        """
        Retrieves recent conversation history for a student's subject.
        """
        subject_query = "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;"
        history_query = """
            SELECT id, role, text, citations_json, answered_from, created_at
            FROM chat_messages
            WHERE subject_id = %s AND user_id = %s
            ORDER BY created_at ASC
            LIMIT %s;
        """

        if cursor is not None:
            cursor.execute(subject_query, (str(subject_id), str(user_id)))
            subject = cursor.fetchone()
            if not subject:
                raise HTTPException(status_code=404, detail="Subject not found or access denied.")

            cursor.execute(history_query, (str(subject_id), str(user_id), limit))
            rows = cursor.fetchall()
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(subject_query, (str(subject_id), str(user_id)))
                subject = cur.fetchone()
                if not subject:
                    raise HTTPException(status_code=404, detail="Subject not found or access denied.")

                cur.execute(history_query, (str(subject_id), str(user_id), limit))
                rows = cur.fetchall()

        messages: List[ChatMessageHistoryItem] = []
        for r in rows:
            citations_data: List[CitationItem] = []
            if r["citations_json"]:
                raw_cits = r["citations_json"]
                if isinstance(raw_cits, str):
                    raw_cits = json.loads(raw_cits)
                citations_data = [CitationItem.model_validate(c) for c in raw_cits]

            messages.append(
                ChatMessageHistoryItem(
                    id=str(r["id"]),
                    role=r["role"],
                    text=r["text"],
                    answered_from=r["answered_from"],
                    citations=citations_data,
                    created_at=r["created_at"],
                )
            )

        return ChatHistoryResponse(
            subject_id=str(subject["id"]),
            subject_name=subject["name"],
            total_messages=len(messages),
            messages=messages,
        )

    def clear_history(
        self,
        user_id: str,
        subject_id: str,
        cursor: Optional[Any] = None,
    ) -> int:
        """
        Clears all conversation messages for a student's subject (Start New Chat).
        Enforces Rule 11 (Privacy): Only deletes messages belonging to the authenticated student.
        Returns the count of deleted messages.
        """
        subject_query = "SELECT id, name FROM subjects WHERE id = %s AND user_id = %s;"
        delete_query = "DELETE FROM chat_messages WHERE subject_id = %s AND user_id = %s;"

        if cursor is not None:
            cursor.execute(subject_query, (str(subject_id), str(user_id)))
            subject = cursor.fetchone()
            if not subject:
                raise HTTPException(status_code=404, detail="Subject not found or access denied.")

            cursor.execute(delete_query, (str(subject_id), str(user_id)))
            deleted_count = cursor.rowcount
        else:
            with get_db_cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(subject_query, (str(subject_id), str(user_id)))
                subject = cur.fetchone()
                if not subject:
                    raise HTTPException(status_code=404, detail="Subject not found or access denied.")

                cur.execute(delete_query, (str(subject_id), str(user_id)))
                deleted_count = cur.rowcount

        logger.info(
            f"[Chatbot] Cleared {deleted_count} messages for subject {subject_id} (user: {user_id})"
        )
        return deleted_count

