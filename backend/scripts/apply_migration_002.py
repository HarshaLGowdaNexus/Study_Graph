"""
Applies migration 002 to the database.
Updates documents status check constraint and adds storage tracking columns.
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from backend.app.core.config import settings


def apply_migration() -> bool:
    print("Applying migration 002...")
    if not settings.DATABASE_URL:
        print("[ERROR] DATABASE_URL is not set.")
        return False

    migration_file = Path(__file__).resolve().parent.parent / "migrations" / "002_update_document_status.sql"
    sql = migration_file.read_text(encoding="utf-8")

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()
        print("OK: Migration 002 applied successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply migration: {e}")
        return False


if __name__ == "__main__":
    success = apply_migration()
    sys.exit(0 if success else 1)

