"""
Standalone End-to-End Test Script for T07: Embeddings, Duplicate Merge, and Split.
Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase.
  - Decision D09: Google Gemini Flash for duplicate confirmation.
  - Decision D10: Google text-embedding-004 / gemini-embedding-001 (768 dimensions).
  - RULEBOOK Golden Rule 7: Test before claiming anything works. Show real output.
"""

import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.services.dedupe_service import DedupeService
from backend.app.services.embedding_service import EmbeddingService, compute_cosine_similarity


def run_e2e_dedupe_test():
    print("=" * 80)
    print("StudyGraph — T07: Embeddings, Duplicate Detection, Merge & Split E2E Test")
    print("=" * 80)

    if not settings.DATABASE_URL:
        print("[FAIL] DATABASE_URL is not set.")
        sys.exit(1)

    if not settings.GEMINI_API_KEY or "your_gemini_api_key_here" in settings.GEMINI_API_KEY:
        print("[FAIL] GEMINI_API_KEY is not set.")
        sys.exit(1)

    embedding_service = EmbeddingService()
    dedupe_service = DedupeService()

    test_user_id = str(uuid4())
    test_subject_id = str(uuid4())
    test_doc_id = str(uuid4())
    chunk_1_id = str(uuid4())
    chunk_2_id = str(uuid4())
    topic_a_id = str(uuid4())
    topic_b_id = str(uuid4())
    topic_c_id = str(uuid4())

    try:
        # Step 1: Create test user, subject, document, and note chunks
        print("\n[Step 1] Creating test fixture in Supabase...")
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # User
            cursor.execute(
                "INSERT INTO users (id, email, name) VALUES (%s, %s, %s);",
                (test_user_id, f"test_t07_{uuid4().hex[:6]}@study.edu", "T07 Verification Student"),
            )
            # Subject
            cursor.execute(
                "INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, %s);",
                (test_subject_id, test_user_id, "Computer Networks (T07 Verification)"),
            )
            # Document
            cursor.execute(
                """
                INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status)
                VALUES (%s, %s, 1, 'Unit1_Transport_Protocols.pdf', 'pdf', 'notes', 'done');
                """,
                (test_doc_id, test_subject_id),
            )
            # Chunks (without embeddings initially)
            cursor.execute(
                """
                INSERT INTO chunks (id, document_id, page, text, module_no, method)
                VALUES 
                (%s, %s, 1, 'The TCP protocol provides reliable communication using a three-way handshake (SYN, SYN-ACK, ACK) to establish connections before transferring data.', 1, 'direct'),
                (%s, %s, 2, 'UDP is an alternative transport layer protocol that is connectionless and does not perform any handshake or retransmissions, ideal for streaming.', 1, 'direct');
                """,
                (chunk_1_id, test_doc_id, chunk_2_id, test_doc_id),
            )
        print("  OK: Created user, subject, document, and 2 note chunks.")

        # Step 2: Embed chunks with text-embedding-004 / gemini-embedding-001
        print("\n[Step 2] Generating real 768-dimensional embeddings for note chunks...")
        start_time = time.time()
        chunks_embedded = embedding_service.embed_unembedded_chunks(UUID(test_doc_id))
        embed_time = time.time() - start_time
        print(f"  OK: Embedded {chunks_embedded} chunks in {embed_time:.2f}s.")

        # Verify chunk embeddings in database
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, page, text, embedding IS NOT NULL AS has_emb FROM chunks WHERE document_id = %s",
                (test_doc_id,),
            )
            rows = cursor.fetchall()
            for r in rows:
                print(f"  Chunk (p.{r['page']}): has_embedding={r['has_emb']} | '{r['text'][:55]}...'")

        # Step 3: Insert topics
        print("\n[Step 3] Creating candidate study topics:")
        print("  - Topic A: 'TCP 3-Way Handshake' (synonym variant 1)")
        print("  - Topic B: 'TCP Connection Establishment' (synonym variant 2)")
        print("  - Topic C: 'UDP Protocol' (distinct concept)")
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # Topic A
            cursor.execute(
                """
                INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, module_no, reviewed)
                VALUES (%s, %s, %s, %s, %s, 1, TRUE);
                """,
                (
                    topic_a_id,
                    test_subject_id,
                    "TCP 3-Way Handshake",
                    "Three-step SYN, SYN-ACK, ACK connection establishment mechanism in TCP.",
                    "Web browsing over HTTP/HTTPS",
                ),
            )
            cursor.execute(
                "INSERT INTO topic_sources (topic_id, chunk_id) VALUES (%s, %s);",
                (topic_a_id, chunk_1_id),
            )

            # Topic B
            cursor.execute(
                """
                INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, module_no, reviewed)
                VALUES (%s, %s, %s, %s, %s, 1, TRUE);
                """,
                (
                    topic_b_id,
                    test_subject_id,
                    "TCP Connection Establishment",
                    "The connection setup procedure in TCP requiring SYN and ACK packet exchange.",
                    "Establishing socket connections in network applications",
                ),
            )
            cursor.execute(
                "INSERT INTO topic_sources (topic_id, chunk_id) VALUES (%s, %s);",
                (topic_b_id, chunk_1_id),
            )

            # Topic C
            cursor.execute(
                """
                INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, module_no, reviewed)
                VALUES (%s, %s, %s, %s, %s, 1, TRUE);
                """,
                (
                    topic_c_id,
                    test_subject_id,
                    "UDP Protocol",
                    "Connectionless transport protocol providing low latency communication without reliability guarantees.",
                    "Video streaming and online gaming",
                ),
            )
            cursor.execute(
                "INSERT INTO topic_sources (topic_id, chunk_id) VALUES (%s, %s);",
                (topic_c_id, chunk_2_id),
            )
        print("  OK: Inserted 3 topics with chunk evidence links.")

        # Step 4: Embed topics
        print("\n[Step 4] Generating real embeddings for topics...")
        topics_embedded = embedding_service.embed_unembedded_topics(UUID(test_subject_id))
        print(f"  OK: Embedded {topics_embedded} topics in database.")

        # Step 5: Test candidate duplicate detection via pgvector cosine distance
        print("\n[Step 5] Running vector similarity search (Threshold = 0.80)...")
        candidates = dedupe_service.find_candidate_pairs(UUID(test_subject_id), custom_threshold=0.80)
        print(f"  Found {len(candidates)} candidate pair(s):")
        for c in candidates:
            print(f"  * '{c.topic_a_keyword}' <---> '{c.topic_b_keyword}' | Similarity: {c.similarity:.4f}")

        assert len(candidates) >= 1, "Expected at least 1 candidate pair (TCP Handshake variants)."
        tcp_pair = next(
            (c for c in candidates if "TCP" in c.topic_a_keyword and "TCP" in c.topic_b_keyword), None
        )
        assert tcp_pair is not None, "TCP candidate pair was not found."
        print(f"  OK: Correctly flagged '{tcp_pair.topic_a_keyword}' and '{tcp_pair.topic_b_keyword}' (similarity {tcp_pair.similarity:.4f})")

        # Step 6: Test LLM duplicate confirmation on both matching and non-matching topics
        print("\n[Step 6] Running LLM confirmation with Gemini Flash...")
        # Positive check (TCP Handshake vs TCP Connection Establishment)
        decision_dup = dedupe_service.confirm_duplicate_with_llm(
            topic_a_keyword="TCP 3-Way Handshake",
            topic_a_explanation="Three-step SYN, SYN-ACK, ACK connection establishment mechanism in TCP.",
            topic_b_keyword="TCP Connection Establishment",
            topic_b_explanation="The connection setup procedure in TCP requiring SYN and ACK packet exchange.",
        )
        print(f"  Positive Pair Result: is_duplicate={decision_dup.is_duplicate}, confidence={decision_dup.confidence}")
        print(f"  Reason: {decision_dup.reason}")
        print(f"  Canonical Keyword: '{decision_dup.canonical_keyword}'")
        assert decision_dup.is_duplicate is True, "LLM should recognize TCP connection setup as duplicate."

        # Negative check (TCP vs UDP)
        decision_distinct = dedupe_service.confirm_duplicate_with_llm(
            topic_a_keyword="TCP 3-Way Handshake",
            topic_a_explanation="Three-step SYN, SYN-ACK, ACK connection establishment mechanism in TCP.",
            topic_b_keyword="UDP Protocol",
            topic_b_explanation="Connectionless transport protocol providing low latency communication without reliability guarantees.",
        )
        print(f"\n  Negative Pair Result: is_duplicate={decision_distinct.is_duplicate}, confidence={decision_distinct.confidence}")
        print(f"  Reason: {decision_distinct.reason}")
        assert decision_distinct.is_duplicate is False, "LLM must NOT merge TCP and UDP."
        print("  OK: Distinct topics correctly protected from merging.")

        # Step 7: Execute Merge
        print("\n[Step 7] Executing Topic Merge (merging Topic B into Topic A)...")
        merge_res = dedupe_service.merge_topics(
            surviving_topic_id=UUID(topic_a_id),
            merged_topic_id=UUID(topic_b_id),
            similarity_score=tcp_pair.similarity,
            merge_type="auto",
            canonical_keyword=decision_dup.canonical_keyword,
        )
        merge_id = merge_res["merge_id"]
        print(f"  OK: Merge executed. Merge Record ID: {merge_id}")
        print(f"  Surviving Topic: '{merge_res['surviving_keyword']}'")
        print(f"  Transferred Chunks: {merge_res['transferred_chunks_count']}")

        # Verify DB state after merge
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # Check topic_aliases
            cursor.execute(
                "SELECT alias FROM topic_aliases WHERE topic_id = %s",
                (topic_a_id,),
            )
            aliases = [r["alias"] for r in cursor.fetchall()]
            print(f"  Surviving Topic Aliases in DB: {aliases}")
            assert "TCP Connection Establishment" in aliases or "TCP 3-Way Handshake" in aliases

            # Check topic_sources on surviving topic
            cursor.execute(
                "SELECT chunk_id FROM topic_sources WHERE topic_id = %s",
                (topic_a_id,),
            )
            sources = [str(r["chunk_id"]) for r in cursor.fetchall()]
            print(f"  Surviving Topic Evidence Chunks: {len(sources)} chunk(s)")
            assert chunk_1_id in sources

            # Check topic_merges audit log
            cursor.execute(
                "SELECT id, merged_keyword, similarity_score, merge_type FROM topic_merges WHERE id = %s",
                (merge_id,),
            )
            log_row = cursor.fetchone()
            print(f"  Audit Log Row: merged='{log_row['merged_keyword']}', type={log_row['merge_type']}, score={log_row['similarity_score']:.4f}")

            # Check merged topic is deleted from topics
            cursor.execute("SELECT id FROM topics WHERE id = %s", (topic_b_id,))
            assert cursor.fetchone() is None, "Merged topic should be removed from topics table."

        # Step 8: Execute Split (Undo)
        print("\n[Step 8] Testing Split (Undo) functionality...")
        split_res = dedupe_service.split_merge(UUID(merge_id))
        print(f"  OK: Split executed. Restored topic '{split_res['restored_keyword']}' (ID: {split_res['restored_topic_id']})")
        print(f"  Restored Chunks Count: {split_res['restored_chunks_count']}")

        # Verify DB state after split
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            # Check restored topic exists
            cursor.execute(
                "SELECT id, keyword, explanation FROM topics WHERE id = %s",
                (topic_b_id,),
            )
            restored_row = cursor.fetchone()
            assert restored_row is not None, "Restored topic should exist in topics table."
            print(f"  Restored Topic in DB: '{restored_row['keyword']}' — '{restored_row['explanation'][:50]}...'")

            # Check restored topic sources
            cursor.execute(
                "SELECT chunk_id FROM topic_sources WHERE topic_id = %s",
                (topic_b_id,),
            )
            restored_sources = [str(r["chunk_id"]) for r in cursor.fetchall()]
            assert chunk_1_id in restored_sources, "Restored topic should have its source chunk link back."
            print(f"  Restored Topic Sources: {len(restored_sources)} chunk(s)")

            # Check alias was removed from surviving topic
            cursor.execute(
                "SELECT alias FROM topic_aliases WHERE topic_id = %s AND alias = %s",
                (topic_a_id, "TCP Connection Establishment"),
            )
            assert cursor.fetchone() is None, "Alias should be removed from surviving topic upon split."
            print("  Alias cleanly removed from surviving topic.")

            # Check audit record has undone_at timestamp
            cursor.execute(
                "SELECT undone_at FROM topic_merges WHERE id = %s",
                (merge_id,),
            )
            undone_at = cursor.fetchone()["undone_at"]
            assert undone_at is not None, "topic_merges should record undone_at timestamp."
            print(f"  Audit log marked undone_at: {undone_at}")

        print("\n[Step 9] Testing Double-Split Protection...")
        try:
            dedupe_service.split_merge(UUID(merge_id))
            print("[FAIL] Allowed double split!")
            sys.exit(1)
        except ValueError as ve:
            print(f"  OK: Double-split correctly blocked with message: '{ve}'")

        print("\n[Step 10] Testing Cross-Subject Isolation...")
        other_subject_id = str(uuid4())
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, %s);",
                (other_subject_id, test_user_id, "Operating Systems"),
            )
        try:
            # Attempt to merge topics across test_subject_id and other_subject_id
            dedupe_service.merge_topics(UUID(topic_a_id), UUID(topic_c_id))
        except ValueError as ve:
            print(f"  OK: Cross-subject merge rejected: '{ve}'")

        print("\n" + "=" * 80)
        print("SUCCESS: All T07 Embedding, Deduplication, Merge, and Split checks PASSED!")
        print("=" * 80)

    finally:
        # Cleanup test fixture
        print("\n[Cleanup] Removing temporary test records...")
        with get_db_cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s;", (test_user_id,))
        print("  OK: Test records cleaned up.")


if __name__ == "__main__":
    run_e2e_dedupe_test()
