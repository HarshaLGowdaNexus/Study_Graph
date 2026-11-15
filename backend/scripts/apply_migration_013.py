"""
Applies migration 013 to the database.
Removes syllabus ghost nodes columns and tables while keeping source_variants
and source_preference intact.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from backend.app.core.config import settings


def apply_migration() -> bool:
    print("Applying migration 013 (remove syllabus ghost nodes)...")
    if not settings.DATABASE_URL:
        print("[ERROR] DATABASE_URL is not set.")
        return False

    migration_file = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "013_remove_ghost_nodes.sql"
    )
    sql = migration_file.read_text(encoding="utf-8")

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        print("OK: Migration 013 applied successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply migration 013: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)
