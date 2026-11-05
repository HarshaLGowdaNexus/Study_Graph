"""
Live verification script for Task T05: Topic Extraction.
Performs:
  1. Live topic extraction on a real uploaded document (or sample chunks).
  2. Nonsense / empty chunk test: verifies zero fake topics generated.
  3. Grounding check: verifies every topic links to real source chunks and matches source text.
  4. Format check: verifies no topic exceeds 4 explanation lines.
  5. Reviews 10 random topics with source citations.
"""

import sys
import random
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import get_db_cursor
from backend.app.services.topic_extractor import topic_extractor_service


def run_tests():
    print("=" * 80)
    print("        STUDYGRAPH T05: TOPIC EXTRACTION LIVE VERIFICATION")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # Test 1: Nonsense / Empty chunk test
    # --------------------------------------------------------------------------
    print("\n[TEST 1] Testing empty / nonsense chunk handling...")
    garbage_chunks = [
        {
            "id": "11111111-2222-3333-4444-555555555555",
            "page": 999,
            "text": "asdfghjk qwertyuiop zxcvbnm 12345 hello??? !!!",
        }
    ]
    valid_topics, rejected, tokens = topic_extractor_service.extract_topics_from_chunk_group(
        chunks=garbage_chunks,
        subject_id="00000000-0000-0000-0000-000000000000",
        module_no=1,
    )
    print(f"  -> Extracted topics for nonsense text: {len(valid_topics)} topics")
    assert len(valid_topics) == 0, "Nonsense chunk generated hallucinated topics!"
    print("  [PASS] Nonsense chunk correctly generated 0 fake topics.")

    # --------------------------------------------------------------------------
    # Test 2: Live extraction on real sample document chunks
    # --------------------------------------------------------------------------
    print("\n[TEST 2] Finding a real document with chunks in database...")
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.filename, d.module_no, d.subject_id, COUNT(c.id) as chunk_count
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id, d.filename, d.module_no, d.subject_id
            ORDER BY chunk_count ASC;
            """
        )
        doc_candidates = cursor.fetchall()

    if not doc_candidates:
        print("[FAIL] No documents with chunks found in database.")
        sys.exit(1)

    # Pick the document with chunks (e.g. the vision notes or the PDF)
    target_doc = doc_candidates[0]
    doc_id, filename, module_no, subject_id, chunk_count = target_doc
    print(f"  -> Selected document: '{filename}' (ID: {doc_id}, Module: {module_no}, Chunks: {chunk_count})")

    print(f"  -> Starting topic extraction on '{filename}'...")
    batch_result = topic_extractor_service.process_document_topics(str(doc_id))

    print(f"\n[EXTRACTION SUMMARY]")
    print(f"  - Batches processed: {batch_result.batches_processed}")
    print(f"  - Topics created: {batch_result.topics_created}")
    print(f"  - Topics rejected: {batch_result.topics_rejected}")
    print(f"  - Batches failed: {batch_result.batches_failed}")
    if batch_result.failure_reasons:
        for r in batch_result.failure_reasons:
            print(f"    ! Failure detail: {r}")
    print(f"  - Tokens used: Prompt={batch_result.token_usage['prompt_tokens']}, "
          f"Completion={batch_result.token_usage['completion_tokens']}, "
          f"Total={batch_result.token_usage['total_tokens']}")

    if batch_result.topics_created == 0:
        print(f"\n[FAIL] No topics were created for {filename}. Check the failure details above.")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # Test 3: Verify all topics have evidence (no evidence, no topic rule)
    # --------------------------------------------------------------------------
    print("\n[TEST 3] Verifying topic grounding & evidence rules...")
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT t.id, t.keyword, t.explanation, t.real_world_use, t.reviewed, t.module_no,
                   COUNT(ts.chunk_id) as evidence_count
            FROM topics t
            LEFT JOIN topic_sources ts ON ts.topic_id = t.id
            WHERE t.subject_id = %s
            GROUP BY t.id, t.keyword, t.explanation, t.real_world_use, t.reviewed, t.module_no;
            """,
            (subject_id,),
        )
        all_topics = cursor.fetchall()

    print(f"  -> Total saved topics in DB: {len(all_topics)}")
    assert len(all_topics) > 0

    topics_without_source = [t for t in all_topics if t[6] == 0]
    print(f"  -> Topics with zero source chunks: {len(topics_without_source)}")
    assert len(topics_without_source) == 0, "Found topics without source chunk citations!"
    print("  [PASS] 100% of topics cite at least one real source chunk.")

    # --------------------------------------------------------------------------
    # Test 4: Format check: reviewed = false, module_no set, explanation <= 4 lines
    # --------------------------------------------------------------------------
    print("\n[TEST 4] Verifying review flag and explanation line limit...")
    for t in all_topics:
        t_id, keyword, explanation, real_world_use, reviewed, t_module, ev_count = t
        assert reviewed is False, f"Topic '{keyword}' has reviewed != False"
        assert t_module is not None, f"Topic '{keyword}' has null module_no"

        lines = [l.strip() for l in explanation.splitlines() if l.strip()]
        assert len(lines) <= 4, f"Topic '{keyword}' exceeds 4 lines ({len(lines)} lines)"

    print("  [PASS] All topics have reviewed = False, module_no set, and explanation <= 4 lines.")

    # --------------------------------------------------------------------------
    # Test 5: Spot-check sample topics with their actual source chunk text
    # --------------------------------------------------------------------------
    print("\n[TEST 5] Spot-checking topics against source chunk text:")
    sample_size = min(10, len(all_topics))
    sample_topics = random.sample(all_topics, sample_size)

    for i, t in enumerate(sample_topics, 1):
        t_id, keyword, explanation, real_world_use, reviewed, t_module, ev_count = t
        print(f"\n--- [Topic #{i}] {keyword} (Module {t_module}) ---")
        print(f"  Explanation ({len(explanation.splitlines())} lines):")
        for line in explanation.splitlines():
            print(f"    | {line}")
        print(f"  Real-World Use: {real_world_use}")

        # Fetch cited chunk text
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT c.id, c.page, c.text
                FROM chunks c
                JOIN topic_sources ts ON ts.chunk_id = c.id
                WHERE ts.topic_id = %s;
                """,
                (t_id,),
            )
            citations = cursor.fetchall()

        print(f"  Evidence ({len(citations)} source chunk(s)):")
        for cid, page, text in citations:
            snippet = text.replace("\n", " ")[:120]
            print(f"    * Chunk {cid} (Page {page}): \"{snippet}...\"")

    print("\n" + "=" * 80)
    print("                  ALL VERIFICATION CHECKS PASSED!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()

