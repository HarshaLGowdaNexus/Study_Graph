"""
Cost Estimation and Token Logging Service for StudyGraph.
Relies on:
  - Decision D05: PostgreSQL for persistent token_logs table.
  - Decision D09: Google Gemini Flash for structured reasoning.
  - Decision D10: Google text-embedding-004 for semantic search.
  - Golden Rule 8 & 11: Protect secrets and track token costs per upload and chat.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import psycopg2.extras

from backend.app.database import get_db_cursor

logger = logging.getLogger(__name__)

# Standard Google AI Studio API pricing per 1,000,000 tokens
# Free tier gives 15 RPM / 1500 RPD for free, but commercial rates provide transparency
PRICING_PER_MILLION = {
    "gemini_flash_input": Decimal("0.075"),       # $0.075 per 1M prompt tokens
    "gemini_flash_output": Decimal("0.300"),      # $0.300 per 1M completion tokens
    "text_embedding_input": Decimal("0.020"),     # $0.020 per 1M embedding tokens
}


def calculate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Computes estimated USD cost based on official Gemini Flash and embedding rates.
    """
    model_lower = (model or "").lower()
    
    if "embedding" in model_lower:
        rate_input = PRICING_PER_MILLION["text_embedding_input"]
        rate_output = Decimal("0")
    else:
        # Default to Gemini Flash pricing (Decision D08 / D09)
        rate_input = PRICING_PER_MILLION["gemini_flash_input"]
        rate_output = PRICING_PER_MILLION["gemini_flash_output"]

    cost_prompt = (Decimal(prompt_tokens) / Decimal(1_000_000)) * rate_input
    cost_output = (Decimal(completion_tokens) / Decimal(1_000_000)) * rate_output
    total_cost = cost_prompt + cost_output

    return float(round(total_cost, 6))


def log_token_usage(
    user_id: str,
    operation: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    subject_id: Optional[str] = None,
    document_id: Optional[str] = None,
) -> Optional[str]:
    """
    Persists token usage and estimated cost to the PostgreSQL 'token_logs' table (Rule 11).
    Fails safely without breaking user workflows if logging encounters transient errors.
    """
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0:
        return None

    cost_usd = calculate_cost_usd(model, prompt_tokens, completion_tokens)

    try:
        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO token_logs (
                    user_id, subject_id, document_id, operation, model,
                    prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    user_id,
                    subject_id,
                    document_id,
                    operation,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_usd,
                ),
            )
            row = cursor.fetchone()
            log_id = str(row["id"]) if row else None
            logger.info(
                f"[CostService] Logged {total_tokens} tokens for '{operation}' "
                f"(User: {user_id[:8]}..., Cost: ${cost_usd:.6f})"
            )
            return log_id
    except Exception as e:
        logger.warning(f"[CostService] Could not record token log (safe fallback): {e}")
        return None


def get_user_cost_summary(user_id: str) -> Dict[str, Any]:
    """
    Returns an aggregated cost and token consumption breakdown for the specified user:
      1. Overall totals (prompt, completion, total, estimated USD).
      2. Per-upload breakdown (tokens & cost grouped by document).
      3. Per-chat breakdown (tokens & cost for recent study chat interactions).
      4. By operation summary (OCR, topic extraction, candidate judging, chat, exam).
    """
    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        # 1. Total Aggregates
        cursor.execute(
            """
            SELECT 
                COALESCE(SUM(prompt_tokens), 0) AS total_prompt,
                COALESCE(SUM(completion_tokens), 0) AS total_completion,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS total_cost_usd
            FROM token_logs
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        totals_row = cursor.fetchone() or {}

        # 2. Per-Upload breakdown
        cursor.execute(
            """
            SELECT 
                d.id AS document_id,
                d.filename,
                d.uploaded_at,
                s.name AS subject_name,
                COALESCE(SUM(tl.prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(tl.completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(tl.total_tokens), 0) AS total_tokens,
                COALESCE(SUM(tl.estimated_cost_usd), 0.0) AS estimated_cost_usd,
                ARRAY_AGG(DISTINCT tl.operation) AS operations
            FROM documents d
            JOIN subjects s ON d.subject_id = s.id
            LEFT JOIN token_logs tl ON tl.document_id = d.id
            WHERE s.user_id = %s
            GROUP BY d.id, d.filename, d.uploaded_at, s.name
            ORDER BY d.uploaded_at DESC;
            """,
            (user_id,),
        )
        uploads_rows = cursor.fetchall() or []
        uploads = [
            {
                "document_id": str(r["document_id"]),
                "filename": r["filename"],
                "subject_name": r["subject_name"],
                "uploaded_at": r["uploaded_at"].isoformat() if r["uploaded_at"] else None,
                "prompt_tokens": int(r["prompt_tokens"]),
                "completion_tokens": int(r["completion_tokens"]),
                "total_tokens": int(r["total_tokens"]),
                "estimated_cost_usd": float(round(float(r["estimated_cost_usd"]), 6)),
                "operations": [op for op in (r["operations"] or []) if op],
            }
            for r in uploads_rows
        ]

        # 3. Per-Chat breakdown (recent chat interactions)
        cursor.execute(
            """
            SELECT 
                tl.id,
                tl.created_at,
                s.name AS subject_name,
                tl.prompt_tokens,
                tl.completion_tokens,
                tl.total_tokens,
                tl.estimated_cost_usd
            FROM token_logs tl
            LEFT JOIN subjects s ON tl.subject_id = s.id
            WHERE tl.user_id = %s AND tl.operation IN ('chat_message', 'exam_answer')
            ORDER BY tl.created_at DESC
            LIMIT 25;
            """,
            (user_id,),
        )
        chat_rows = cursor.fetchall() or []
        chats = [
            {
                "id": str(r["id"]),
                "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
                "subject_name": r["subject_name"] or "General",
                "prompt_tokens": int(r["prompt_tokens"]),
                "completion_tokens": int(r["completion_tokens"]),
                "total_tokens": int(r["total_tokens"]),
                "estimated_cost_usd": float(round(float(r["estimated_cost_usd"]), 6)),
            }
            for r in chat_rows
        ]

        # 4. Grouped by operation
        cursor.execute(
            """
            SELECT 
                operation,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_cost_usd), 0.0) AS cost_usd,
                COUNT(*) AS call_count
            FROM token_logs
            WHERE user_id = %s
            GROUP BY operation
            ORDER BY total_tokens DESC;
            """,
            (user_id,),
        )
        op_rows = cursor.fetchall() or []
        by_operation = [
            {
                "operation": r["operation"],
                "total_tokens": int(r["total_tokens"]),
                "cost_usd": float(round(float(r["cost_usd"]), 6)),
                "call_count": int(r["call_count"]),
            }
            for r in op_rows
        ]

    return {
        "user_id": user_id,
        "total_prompt_tokens": int(totals_row.get("total_prompt", 0)),
        "total_completion_tokens": int(totals_row.get("total_completion", 0)),
        "total_tokens": int(totals_row.get("total_tokens", 0)),
        "total_estimated_cost_usd": float(round(float(totals_row.get("total_cost_usd", 0.0)), 6)),
        "per_upload_breakdown": uploads,
        "per_chat_breakdown": chats,
        "by_operation": by_operation,
        "pricing_reference": {
            "gemini_flash_input_per_million": float(PRICING_PER_MILLION["gemini_flash_input"]),
            "gemini_flash_output_per_million": float(PRICING_PER_MILLION["gemini_flash_output"]),
            "free_tier_notice": "Google AI Studio provides a free tier (15 requests/min, 1,500/day). Actual spend under quota is $0.00.",
        },
    }
