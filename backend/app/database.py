"""
Database connection utilities for StudyGraph.
Relies on Decision D05: PostgreSQL on Supabase.
"""

from contextlib import contextmanager
from typing import Generator
import psycopg2
from psycopg2.extensions import connection as PgConnection
from backend.app.core.config import settings


def get_connection() -> PgConnection:
    """
    Establish and return a direct connection to the PostgreSQL database.
    Raises ValueError with a helpful message if DATABASE_URL is not configured.
    """
    if not settings.DATABASE_URL or "your_password_here" in settings.DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not configured in your .env file.\n"
            "Please copy .env.example to .env and fill in your Supabase connection string."
        )

    # Clean connection string if needed (e.g. handle sslmode for Supabase)
    db_url = settings.DATABASE_URL
    return psycopg2.connect(db_url)


@contextmanager
def get_db_cursor() -> Generator:
    """
    Context manager providing a database cursor that automatically commits
    or rolls back transactions and closes cleanly.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

