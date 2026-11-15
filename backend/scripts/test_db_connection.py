"""
Database Connection Check Script for StudyGraph.
Verifies connection to PostgreSQL on Supabase, checks pgvector extension,
and checks for the 20 tables required by docs/DATA_MODEL.md.
"""

import sys
from pathlib import Path

# Add project root to sys.path so backend imports work from scripts directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import psycopg2
from backend.app.core.config import settings

EXPECTED_TABLES = [
    "universities",
    "schemes",
    "syllabus_subjects",
    "users",
    "subjects",
    "documents",
    "chunks",
    "clusters",
    "topics",
    "topic_sources",
    "topic_aliases",
    "edges",
    "edge_evidence",
    "graph_versions",
    "exam_papers",
    "exam_questions",
    "share_links",
    "chat_messages",
]


def check_database() -> bool:
    print("Checking connection to database...")

    if not settings.DATABASE_URL or "your_password_here" in settings.DATABASE_URL:
        print("\n[ERROR] DATABASE_URL is not set or still contains placeholder text in your .env file.")
        print("Tip: Make sure you created a '.env' file from '.env.example' and put in your real Supabase connection string.")
        return False

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()

        # 1. Check PostgreSQL version
        cursor.execute("SELECT version();")
        pg_version = cursor.fetchone()[0]
        print(f"Connected to PostgreSQL: {pg_version.split(',')[0]}")

        # 2. Check pgvector extension
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        has_vector = cursor.fetchone()
        if not has_vector:
            print("[WARNING] The 'vector' extension is not enabled yet in your database.")
            print("Tip: Run the SQL in 'backend/migrations/001_initial_schema.sql' in your Supabase SQL Editor.")
            cursor.close()
            conn.close()
            return False
        print("Extension check: 'vector' extension is enabled.")

        # 3. Check tables from docs/DATA_MODEL.md
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing_tables = [t for t in EXPECTED_TABLES if t not in existing_tables]

        cursor.close()
        conn.close()

        if missing_tables:
            print(f"[WARNING] Found {len(existing_tables)} tables in database, but {len(missing_tables)} expected tables are missing:")
            for mt in missing_tables:
                print(f"  - {mt}")
            print("\nTip: Run 'backend/migrations/001_initial_schema.sql' in your Supabase SQL Editor to create all 20 tables.")
            return False

        print(f"Schema check: All {len(EXPECTED_TABLES)} required tables exist in public schema.")
        print("\nOK: Connected to Supabase PostgreSQL (pgvector is enabled and all 20 tables exist).")
        return True

    except psycopg2.OperationalError as e:
        err_msg = str(e)
        print("\n[ERROR] Failed to connect to database:")
        if "password authentication failed" in err_msg:
            print("  Reason: Incorrect password in DATABASE_URL. Please double-check your database password.")
        elif "could not translate host name" in err_msg or "Name or service not known" in err_msg:
            print("  Reason: Database host name could not be resolved. Check the URL for typos or check your internet connection.")
        elif "Connection refused" in err_msg:
            print("  Reason: Connection was refused. Ensure your Supabase project is active and port 5432/6543 is accessible.")
        elif "timeout" in err_msg.lower():
            print("  Reason: Connection timed out. Check your network or try using the Supabase Connection Pooler URL (port 6543).")
        else:
            print(f"  Details: {err_msg}")
        return False
    except Exception as e:
        print(f"\n[ERROR] Unexpected error while checking database: {e}")
        return False


if __name__ == "__main__":
    success = check_database()
    sys.exit(0 if success else 1)

