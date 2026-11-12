"""
Applies migration 011 to the database.
Adds embedding & reviewed columns to syllabus_topics, and syllabus_match_locked &
source_variants to topics, plus pgvector/lookup indexes.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from backend.app.core.config import settings


def apply_migration() -> bool:
    print("Applying migration 011 (syllabus ghost nodes & source preference variants)...")
    if not settings.DATABASE_URL:
        print("[ERROR] DATABASE_URL is not set.")
        return False

    migration_file = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "011_syllabus_ghost_nodes_and_source_pref.sql"
    )
    sql = migration_file.read_text(encoding="utf-8")

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        print("OK: Migration 011 applied successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply migration 011: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)

