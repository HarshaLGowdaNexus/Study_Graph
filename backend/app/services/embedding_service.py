"""
Embedding Service for StudyGraph (T07).
Relies on:
  - Decision D10: Google text-embedding-004 / gemini-embedding-001 (768 dimensions).
  - Decision D05: PostgreSQL with pgvector on Supabase (chunks.embedding & topics.embedding).
  - Rule 11: Protect secrets and track usage / cost.
"""

import logging
import math
import time
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor

logger = logging.getLogger(__name__)


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes cosine similarity between two vector lists.
    Returns a float between -1.0 and 1.0 (typically 0.0 to 1.0 for normalized text embeddings).
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class EmbeddingService:
    """
    Handles generating 768-dimensional semantic embeddings for document chunks
    and extracted topics, and updating the pgvector database.
    """

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.vector_dim = settings.VECTOR_DIMENSION
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
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

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates 768-dim embeddings for a list of text strings in batches.
        Includes exponential backoff for Google Free Tier rate limits (429).
        """
        if not texts:
            return []

        client = self._get_client()
        all_embeddings: List[List[float]] = []

        # Configure 768 output dimensions matching vector(768) schema
        config = types.EmbedContentConfig(output_dimensionality=self.vector_dim)

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            clean_batch = [t.strip() if t.strip() else "empty text" for t in batch]

            batch_success = False
            last_err = None

            for attempt in range(1, 5):
                try:
                    response = client.models.embed_content(
                        model=self.model_name,
                        contents=clean_batch,
                        config=config,
                    )

                    for item in response.embeddings:
                        values = list(item.values)
                        if len(values) != self.vector_dim:
                            logger.warning(
                                f"Embedding dimension mismatch: expected {self.vector_dim}, got {len(values)}"
                            )
                        all_embeddings.append(values)

                    batch_success = True
                    break

                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        backoff = attempt * 5
                        logger.warning(
                            f"[Embedding Service] Rate limit 429 hit for batch {i}. "
                            f"Attempt {attempt}/4. Sleeping {backoff}s..."
                        )
                        time.sleep(backoff)
                    else:
                        logger.warning(f"[Embedding Service] Attempt {attempt} failed: {e}. Retrying in 2s...")
                        time.sleep(2)

            if not batch_success:
                logger.error(f"Failed to embed batch {i}-{i+len(batch)}: {last_err}")
                raise last_err

            time.sleep(0.3)

        return all_embeddings

    def generate_single_embedding(self, text: str) -> List[float]:
        """Convenience method to embed a single text string."""
        results = self.generate_embeddings([text])
        return results[0] if results else []

    def embed_unembedded_chunks(self, document_id: Optional[UUID] = None) -> int:
        """
        Finds all chunks with NULL embedding (optionally filtered by document_id),
        generates their embeddings in batches, and immediately saves each batch.
        Returns the count of chunks updated.
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            query = "SELECT id, text FROM chunks WHERE embedding IS NULL"
            params = []
            if document_id:
                query += " AND document_id = %s"
                params.append(str(document_id))
            query += " ORDER BY page ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            logger.info("No unembedded chunks found.")
            return 0

        logger.info(f"Found {len(rows)} unembedded chunks. Starting incremental batch embedding...")
        total_embedded = 0
        batch_size = 20  # Paced batching

        for i in range(0, len(rows), batch_size):
            batch_rows = rows[i : i + batch_size]
            chunk_ids = [r["id"] for r in batch_rows]
            texts = [r["text"] for r in batch_rows]

            embeddings = self.generate_embeddings(texts)

            with get_db_cursor() as cursor:
                for chunk_id, emb in zip(chunk_ids, embeddings):
                    emb_str = f"[{','.join(f'{x:.6f}' for x in emb)}]"
                    cursor.execute(
                        "UPDATE chunks SET embedding = %s::vector WHERE id = %s",
                        (emb_str, chunk_id),
                    )

            total_embedded += len(chunk_ids)
            logger.info(f"Progress: successfully embedded and saved {total_embedded}/{len(rows)} chunks.")
            time.sleep(0.5)

        logger.info(f"Successfully embedded all {total_embedded} chunks.")
        return total_embedded

    def embed_unembedded_topics(self, subject_id: Optional[UUID] = None) -> int:
        """
        Finds all topics with NULL embedding (optionally filtered by subject_id),
        constructs a semantic text representation ("{keyword}: {explanation}"),
        generates embeddings, and writes them to the database.
        Returns the count of topics updated.
        """
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            query = "SELECT id, keyword, explanation FROM topics WHERE embedding IS NULL"
            params = []
            if subject_id:
                query += " AND subject_id = %s"
                params.append(str(subject_id))

            cursor.execute(query, params)
            rows = cursor.fetchall()

        if not rows:
            logger.info("No unembedded topics found.")
            return 0

        topic_ids = [r["id"] for r in rows]
        # Rich semantic string combining keyword and explanation
        texts = [f"{r['keyword']}: {r['explanation']}" for r in rows]
        logger.info(f"Generating embeddings for {len(topic_ids)} topics...")

        embeddings = self.generate_embeddings(texts)

        with get_db_cursor() as cursor:
            for topic_id, emb in zip(topic_ids, embeddings):
                emb_str = f"[{','.join(f'{x:.6f}' for x in emb)}]"
                cursor.execute(
                    "UPDATE topics SET embedding = %s::vector WHERE id = %s",
                    (emb_str, topic_id),
                )

        logger.info(f"Successfully embedded {len(topic_ids)} topics.")
        return len(topic_ids)
