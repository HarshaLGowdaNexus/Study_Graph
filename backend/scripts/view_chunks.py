"""
Quick inspection tool for StudyGraph chunks.
Run: python backend/scripts/view_chunks.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import get_db_cursor


def show_chunks():
    print("=" * 70)
    print("       STUDYGRAPH EXTRACTED CHUNKS VIEWER")
    print("=" * 70)

    try:
        with get_db_cursor() as cursor:
            # Fetch latest documents
            cursor.execute(
                """
                SELECT id, filename, module_no, status, uploaded_at 
                FROM documents 
                ORDER BY uploaded_at DESC 
                LIMIT 5;
                """
            )
            docs = cursor.fetchall()

            if not docs:
                print("\nNo documents found in database yet. Try uploading one first!")
                return

            print(f"\nFound {len(docs)} recent document(s):\n")

            for doc in docs:
                doc_id, filename, module_no, status, uploaded_at = doc
                print(f"📄 Document: {filename} (Module {module_no}) | Status: {status}")

                cursor.execute(
                    """
                    SELECT page, method, text 
                    FROM chunks 
                    WHERE document_id = %s 
                    ORDER BY page, id;
                    """,
                    (doc_id,),
                )
                chunks = cursor.fetchall()

                if not chunks:
                    print("   [No chunks extracted yet]\n")
                    continue

                print(f"   Total chunks: {len(chunks)}")
                for i, (page, method, text) in enumerate(chunks, 1):
                    preview = text.replace("\n", " ")
                    if len(preview) > 100:
                        preview = preview[:100] + "..."
                    badge = "[DIRECT TEXT]" if method == "direct" else "[VISION AI]"
                    print(f"   ├─ Chunk {i} | Page {page} | {badge}: \"{preview}\"")
                print()

    except Exception as e:
        print(f"\n[ERROR] Could not query database: {e}")


if __name__ == "__main__":
    show_chunks()

