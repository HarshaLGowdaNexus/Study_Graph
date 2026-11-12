"""
Applies migration 010 to the database.
Adds embedding vector(768) and canonical_question to exam_questions plus exam indexes.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from backend.app.core.config import settings


def apply_migration() -> bool:
    print("Applying migration 010 (exam question embeddings and indexes)...")
    if not settings.DATABASE_URL:
        print("[ERROR] DATABASE_URL is not set.")
        return False

    migration_file = Path(__file__).resolve().parent.parent / "migrations" / "010_exam_question_embeddings.sql"
    sql = migration_file.read_text(encoding="utf-8")

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        print("OK: Migration 010 applied successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply migration 010: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)

