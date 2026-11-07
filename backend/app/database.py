"""
Database connection utilities for StudyGraph.
Relies on Decision D05: PostgreSQL on Supabase.
"""

import time
import logging
from contextlib import contextmanager
from typing import Generator
import psycopg2
from psycopg2.extensions import connection as PgConnection
from backend.app.core.config import settings

logger = logging.getLogger(__name__)


def get_connection(retries: int = 3, delay: float = 0.5) -> PgConnection:
    """
    Establish and return a direct connection to the PostgreSQL database on Supabase.
    Includes retry logic with exponential backoff to absorb transient Wi-Fi drops or pooler latency.
    """
    if not settings.DATABASE_URL or "your_password_here" in settings.DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not configured in your .env file.\n"
            "Please copy .env.example to .env and fill in your Supabase connection string."
        )

    db_url = settings.DATABASE_URL
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return psycopg2.connect(db_url, connect_timeout=10)
        except Exception as e:
            last_error = e
            logger.warning(f"Database connection attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay * attempt)

    raise last_error


@contextmanager
def get_db_cursor(*args, commit: bool = True, **kwargs) -> Generator:
    """
    Context manager providing a database cursor that automatically commits
    or rolls back transactions and closes cleanly.
    Accepts optional cursor_factory (e.g. psycopg2.extras.RealDictCursor).
    """
    conn = get_connection()
    try:
        with conn.cursor(*args, **kwargs) as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

