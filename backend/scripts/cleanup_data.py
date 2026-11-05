"""
Cleanup script to remove test artifacts, duplicate uploads, and redundant folders for Student A.
"""

import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import get_db_cursor

USER_A = "11111111-1111-4111-8111-111111111111"

def run_cleanup():
    with get_db_cursor() as cur:
        # 1. Delete dummy test document 'Network_Layers_Lecture.pdf'
        cur.execute("DELETE FROM documents WHERE filename = 'Network_Layers_Lecture.pdf';")
        print("Deleted dummy test document 'Network_Layers_Lecture.pdf'")

        # 2. Delete empty zero-chunk duplicate documents for Student A
        cur.execute("""
            DELETE FROM documents d
            USING subjects s
            WHERE d.subject_id = s.id
              AND s.user_id = %s
              AND d.id NOT IN (
                  '3339ad59-25cb-4ff9-a543-334ca75014bb',
                  '675132aa-bc0f-45c6-bb5e-6466f34c5b48'
              );
        """, (USER_A,))
        print("Deleted empty/failed duplicate documents for Student A")

        # 3. Delete redundant duplicate subjects for Student A, keeping only the two active ones
        cur.execute("""
            DELETE FROM subjects
            WHERE user_id = %s
              AND id NOT IN (
                  'a7ba8b8e-5679-4c3c-af5a-dfdf0a64ee95',
                  'c385da4d-6df0-4504-b243-767a8099764f'
              );
        """, (USER_A,))
        print("Cleaned up duplicate subject folders for Student A")

        # 4. Standardize subject names
        cur.execute("UPDATE subjects SET name = 'Operating Systems' WHERE id = 'a7ba8b8e-5679-4c3c-af5a-dfdf0a64ee95';")
        cur.execute("UPDATE subjects SET name = 'Computer Networks' WHERE id = 'c385da4d-6df0-4504-b243-767a8099764f';")
        print("Standardized subject names to Title Case")

if __name__ == "__main__":
    run_cleanup()
