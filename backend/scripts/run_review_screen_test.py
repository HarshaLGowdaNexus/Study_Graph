"""
Live verification script for Task T06: Topic Review Screen.
Tests:
  1. Fetch topics for a real document in database with page citations.
  2. Edit topic keyword & explanation, verify persistence.
  3. Reject explanation > 4 lines (Rule 13.3).
  4. Toggle reviewed flag (single topic approval).
  5. Delete topic (verifies deletion in DB and topic_sources cleanup).
  6. Approve all topics for a document.
  7. Skip review (verifies topics stay unreviewed).
  8. Privacy Rule 11: verify student B cannot access student A's document topics.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import get_db_cursor

client = TestClient(app)

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


def run_live_tests():
    print("=" * 80)
    print("        STUDYGRAPH T06: TOPIC REVIEW SCREEN LIVE VERIFICATION")
    print("=" * 80)

    test_doc_created = None
    try:
        # Find a document in DB that belongs to User A and has extracted topics
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT d.id, d.filename, s.id as subject_id, s.name as subject_name, COUNT(t.id) as topic_count
                FROM documents d
                JOIN subjects s ON d.subject_id = s.id
                JOIN chunks c ON c.document_id = d.id
                JOIN topic_sources ts ON ts.chunk_id = c.id
                JOIN topics t ON t.id = ts.topic_id
                WHERE s.user_id = %s
                GROUP BY d.id, d.filename, s.id, s.name
                HAVING COUNT(t.id) > 0
                LIMIT 1;
                """,
                (USER_A,),
            )
            row = cursor.fetchone()

        if not row:
            print("[NOTICE] Creating isolated test document for verification...")
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO subjects (user_id, name, source_preference)
                    VALUES (%s, '__isolated_test_subject__', 'notes')
                    RETURNING id;
                    """,
                    (USER_A,),
                )
                subject_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO documents (subject_id, module_no, filename, type, source_kind, status)
                    VALUES (%s, 1, '__test_doc__.pdf', 'pdf', 'notes', 'done')
                    RETURNING id;
                    """,
                    (subject_id,),
                )
                doc_id = cursor.fetchone()[0]
                test_doc_created = (doc_id, subject_id)

                cursor.execute(
                    """
                    INSERT INTO chunks (document_id, page, text, module_no, method)
                    VALUES (%s, 1, 'Test content for isolated verification.', 1, 'direct')
                    RETURNING id;
                    """,
                    (doc_id,),
                )
                chunk_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO topics (subject_id, module_no, keyword, explanation, real_world_use, reviewed)
                    VALUES (%s, 1, 'Test Concept', 'Line 1: Test explanation.\nLine 2: Test verification.', 'Industrial test use.', FALSE)
                    RETURNING id;
                    """,
                    (subject_id,),
                )
                topic_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO topic_sources (topic_id, chunk_id)
                    VALUES (%s, %s);
                    """,
                    (topic_id, chunk_id),
                )
            doc_id = str(doc_id)
            filename = "__test_doc__.pdf"
        else:
            doc_id, filename, subject_id, subject_name, topic_count = row
            doc_id = str(doc_id)
            print(f"  -> Found existing document '{filename}' (ID: {doc_id}) with {topic_count} topics.")

        headers_a = {"x-test-user-id": USER_A, "x-test-user-email": "alex@university.edu"}
        headers_b = {"x-test-user-id": USER_B, "x-test-user-email": "jordan@university.edu"}

        # --------------------------------------------------------------------------
        # Test 1: Fetch topics for document (GET /api/documents/{id}/topics)
        # --------------------------------------------------------------------------
        print("\n[TEST 1] Fetching topics for document via API...")
        res = client.get(f"/api/documents/{doc_id}/topics", headers=headers_a)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        print(f"  -> Fetched {data['total_count']} topics (Reviewed: {data['reviewed_count']}, Unreviewed: {data['unreviewed_count']})")
        assert len(data["topics"]) > 0
        sample_topic = data["topics"][0]
        topic_id = sample_topic["id"]
        original_keyword = sample_topic["keyword"]
        original_explanation = sample_topic["explanation"]
        print(f"  -> Selected topic: '{original_keyword}' (Page citations: {sample_topic['source_pages']})")
        print("  [PASS] Topics successfully fetched with source citations.")

        # --------------------------------------------------------------------------
        # Test 2: Edit topic keyword and explanation (PATCH /api/topics/{id})
        # --------------------------------------------------------------------------
        print("\n[TEST 2] Testing inline edit of keyword & explanation...")
        updated_keyword = original_keyword + " (Edited)"
        updated_explanation = "Line 1: Updated explanation.\nLine 2: Verified accurate.\nLine 3: Tested inline edit."
        patch_res = client.patch(
            f"/api/topics/{topic_id}",
            json={"keyword": updated_keyword, "explanation": updated_explanation},
            headers=headers_a,
        )
        assert patch_res.status_code == 200, f"PATCH failed: {patch_res.text}"
        patch_data = patch_res.json()
        assert patch_data["keyword"] == updated_keyword
        assert patch_data["explanation"] == updated_explanation
        print("  -> Topic successfully updated via API.")

        # Verify persistence directly from DB
        with get_db_cursor() as cursor:
            cursor.execute("SELECT keyword, explanation FROM topics WHERE id = %s;", (topic_id,))
            db_kw, db_exp = cursor.fetchone()
            assert db_kw == updated_keyword
            assert db_exp == updated_explanation
        print("  [PASS] Edits persisted directly to database.")

        # Revert to original
        client.patch(
            f"/api/topics/{topic_id}",
            json={"keyword": original_keyword, "explanation": original_explanation},
            headers=headers_a,
        )

        # --------------------------------------------------------------------------
        # Test 3: Reject explanation > 4 lines (Rule 13.3)
        # --------------------------------------------------------------------------
        print("\n[TEST 3] Testing 4-line limit validation...")
        too_long_exp = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5: Illegal extra line"
        reject_res = client.patch(
            f"/api/topics/{topic_id}",
            json={"explanation": too_long_exp},
            headers=headers_a,
        )
        assert reject_res.status_code == 422, f"Expected 422, got {reject_res.status_code}"
        print("  [PASS] Explanations exceeding 4 lines are strictly rejected (HTTP 422).")

        # --------------------------------------------------------------------------
        # Test 4: Toggle individual reviewed flag
        # --------------------------------------------------------------------------
        print("\n[TEST 4] Testing single topic approval toggle...")
        toggle_res = client.patch(
            f"/api/topics/{topic_id}",
            json={"reviewed": True},
            headers=headers_a,
        )
        assert toggle_res.status_code == 200
        assert toggle_res.json()["reviewed"] is True
        print("  [PASS] Single topic approved (reviewed = true).")

        # --------------------------------------------------------------------------
        # Test 5: Approve All topics
        # --------------------------------------------------------------------------
        print("\n[TEST 5] Testing 'Approve All' bulk action...")
        appr_res = client.post(f"/api/documents/{doc_id}/topics/approve-all", headers=headers_a)
        assert appr_res.status_code == 200
        appr_data = appr_res.json()
        assert appr_data["status"] == "approved"
        print(f"  -> Bulk approved: {appr_data['updated_count']} topics")

        # Verify all topics in this doc now have reviewed = True
        list_after_appr = client.get(f"/api/documents/{doc_id}/topics", headers=headers_a).json()
        assert list_after_appr["unreviewed_count"] == 0
        assert list_after_appr["reviewed_count"] == list_after_appr["total_count"]
        print("  [PASS] All document topics verified as reviewed = true.")

        # --------------------------------------------------------------------------
        # Test 6: Skip review
        # --------------------------------------------------------------------------
        print("\n[TEST 6] Testing 'Skip & Continue' action...")
        # First un-review one topic to test skip behavior
        client.patch(f"/api/topics/{topic_id}", json={"reviewed": False}, headers=headers_a)
        skip_res = client.post(f"/api/documents/{doc_id}/topics/skip", headers=headers_a)
        assert skip_res.status_code == 200
        skip_data = skip_res.json()
        assert skip_data["status"] == "skipped"
        print(f"  -> Skip response: {skip_data['message']}")

        # Check that unreviewed topics remain unreviewed
        list_after_skip = client.get(f"/api/documents/{doc_id}/topics", headers=headers_a).json()
        assert list_after_skip["unreviewed_count"] > 0
        print("  [PASS] Skip preserved unreviewed status correctly.")

        # --------------------------------------------------------------------------
        # Test 7: Delete a topic
        # --------------------------------------------------------------------------
        print("\n[TEST 7] Testing topic deletion & cascade cleanup...")
        # Create a temporary topic to delete
        with get_db_cursor() as cursor:
            cursor.execute("SELECT subject_id FROM documents WHERE id = %s;", (doc_id,))
            sub_id = cursor.fetchone()[0]
            cursor.execute("SELECT id FROM chunks WHERE document_id = %s LIMIT 1;", (doc_id,))
            chk_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO topics (subject_id, module_no, keyword, explanation, reviewed)
                VALUES (%s, 1, 'Temporary Topic for Delete Test', 'Temporary explanation.', FALSE)
                RETURNING id;
                """,
                (sub_id,),
            )
            temp_topic_id = str(cursor.fetchone()[0])
            cursor.execute(
                "INSERT INTO topic_sources (topic_id, chunk_id) VALUES (%s, %s);",
                (temp_topic_id, chk_id),
            )

        del_res = client.delete(f"/api/topics/{temp_topic_id}", headers=headers_a)
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True

        # Verify gone from DB
        with get_db_cursor() as cursor:
            cursor.execute("SELECT count(*) FROM topics WHERE id = %s;", (temp_topic_id,))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT count(*) FROM topic_sources WHERE topic_id = %s;", (temp_topic_id,))
            assert cursor.fetchone()[0] == 0
        print("  [PASS] Topic and its topic_sources row completely removed from database.")

        # --------------------------------------------------------------------------
        # Test 8: Multi-user privacy & isolation (Rule 11)
        # --------------------------------------------------------------------------
        print("\n[TEST 8] Verifying student privacy & isolation (Rule 11)...")
        res_b = client.get(f"/api/documents/{doc_id}/topics", headers=headers_b)
        assert res_b.status_code == 404, f"Student B accessed Student A's document topics! (Status: {res_b.status_code})"

        del_b = client.delete(f"/api/topics/{topic_id}", headers=headers_b)
        assert del_b.status_code == 404, "Student B deleted Student A's topic!"
        print("  [PASS] Multi-user isolation verified: Student B cannot view or modify Student A's topics.")

        print("\n" + "=" * 80)
        print("        ALL T06 REVIEW SCREEN TESTS PASSED SUCCESSFULLY! ")
        print("=" * 80)

    finally:
        if test_doc_created:
            t_doc_id, t_sub_id = test_doc_created
            with get_db_cursor() as cursor:
                cursor.execute("DELETE FROM documents WHERE id = %s;", (t_doc_id,))
                cursor.execute("DELETE FROM subjects WHERE id = %s;", (t_sub_id,))
            print(f"  [CLEANUP] Deleted temporary test subject and document {t_doc_id}")


if __name__ == "__main__":
    run_live_tests()
