"""
Automated Verification Script for Task T10:
Tests Link Editing, Soft Deletion, Manual Add, and Pipeline Lock Invariance.

Relies on:
  - Feature F08: Edit / delete / lock links.
  - Risk R16: New uploads overwrite corrected links.
  - RULEBOOK Section 13 Rule 2: User edits are sacred.
"""

import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import get_db_cursor
from backend.app.services.candidate_finder import CandidateFinderService
from backend.app.services.link_judge import LinkJudgeService

client = TestClient(app)


def print_banner(msg: str):
    print("\n" + "=" * 70)
    print(f"  {msg}")
    print("=" * 70)


def run_tests():
    print_banner("RUNNING TASK T10 VERIFICATION: EDITS, DELETIONS & PIPELINE LOCKS")

    topic_a_id = str(uuid.uuid4())
    topic_b_id = str(uuid.uuid4())
    subject_id = str(uuid.uuid4())
    user_id = "00000000-0000-0000-0000-000000000001"

    print("\n[Step 1] Creating temporary test topics in database...")
    zero_vec = "[" + ",".join(["0.02"] * 768) + "]"
    with get_db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, name) VALUES (%s, 't10_tester@studygraph.io', 'T10 Tester') ON CONFLICT DO NOTHING;",
            (user_id,),
        )
        cur.execute(
            "INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, 'Computer Networks') ON CONFLICT DO NOTHING;",
            (subject_id, user_id),
        )
        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'TCP Three-Way Handshake', 'SYN, SYN-ACK, ACK sequence for reliable connection.', 'TCP connection setup', %s::vector, TRUE);
            """,
            (topic_a_id, subject_id, zero_vec),
        )
        cur.execute(
            """
            INSERT INTO topics (id, subject_id, keyword, explanation, real_world_use, embedding, reviewed)
            VALUES (%s, %s, 'HTTP Request-Response', 'Stateless request-response protocol for web resources.', 'Web browser communication', %s::vector, TRUE);
            """,
            (topic_b_id, subject_id, zero_vec),
        )
    print("  -> Created test topics: 'TCP Three-Way Handshake' and 'HTTP Request-Response'")

    try:
        # TEST 1: Manual Link Creation
        print_banner("TEST 1: Manually Adding a Link with Evidence")
        manual_payload = {
            "topic_a": topic_a_id,
            "topic_b": topic_b_id,
            "type": "prerequisite_of",
            "reason": "TCP 3-way handshake must complete successfully before HTTP headers can be transmitted.",
            "industry_example": "Web browsers send HTTP GET only after the TCP socket is connected.",
            "strength": 4,
            "snippet_a": "The connection begins with SYN, SYN-ACK, and ACK flags.",
            "snippet_b": "HTTP/1.1 requires an established underlying TCP connection.",
        }

        res = client.post("/api/edges/manual", json=manual_payload)
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
        data = res.json()
        edge_id = data["id"]
        print(f"  -> Successfully created manual edge: ID = {edge_id}")
        print(f"  -> Locked flag: {data['locked']} (Expected: True)")
        print(f"  -> Status: '{data['status']}' (Expected: 'edited')")
        print(f"  -> Scope: '{data['scope']}' (Expected: 'same_subject')")
        print(f"  -> Evidence Count: {len(data['evidence'])}")
        for ev in data["evidence"]:
            print(f"     Evidence: {ev['snippet']}")
            assert "[manual]" in ev["snippet"], "Evidence must be labeled [manual]!"
        assert data["locked"] is True
        assert data["status"] == "edited"

        # TEST 2: Edit Link
        print_banner("TEST 2: Editing the Link Reason, Type & Strength")
        edit_payload = {
            "type": "applies_in",
            "reason": "USER MODIFIED REASON: TCP handshake mechanisms apply directly to HTTP transport sessions.",
            "strength": 5,
            "industry_example": "CDN edge caching and TCP connection reuse.",
        }
        res_edit = client.patch(f"/api/edges/{edge_id}", json=edit_payload)
        assert res_edit.status_code == 200, f"Expected 200, got {res_edit.status_code}: {res_edit.text}"
        edited_data = res_edit.json()
        print(f"  -> Successfully edited edge: ID = {edge_id}")
        print(f"  -> Updated Type: {edited_data['type']} (Expected: 'applies_in')")
        print(f"  -> Updated Reason: {edited_data['reason']}")
        print(f"  -> Updated Strength: {edited_data['strength']}/5 (Expected: 5)")
        print(f"  -> Locked: {edited_data['locked']} (Expected: True)")
        print(f"  -> Status: '{edited_data['status']}' (Expected: 'edited')")
        assert edited_data["reason"] == edit_payload["reason"]
        assert edited_data["locked"] is True
        assert edited_data["status"] == "edited"

        # TEST 3: Pipeline Re-Run Protection against Edited Link
        print_banner("TEST 3: Simulating Pipeline Re-Run on Edited Link")
        print("  -> Calling CandidateFinderService._query_neighbors for Topic A...")
        finder = CandidateFinderService()
        with get_db_cursor() as cur:
            neighbors = finder._query_neighbors(
                focal_topic_id=topic_a_id,
                focal_subject_id=subject_id,
                same_subject=True,
                threshold=0.0,
                k=10,
                cursor=cur,
            )
            matched = [c for c in neighbors if c.topic_b_id == topic_b_id or c.topic_a_id == topic_b_id]
            print(f"  -> Candidates returned for this pair: {len(matched)} (Expected: 0)")
            assert len(matched) == 0, "Candidate finder must ignore locked/edited edges!"

        print("  -> Calling LinkJudgeService.judge_candidate directly...")
        judge = LinkJudgeService()
        with get_db_cursor() as cur:
            judge_res, _ = judge.judge_candidate(
                candidate_id=None,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                scope="same_subject",
                cursor=cur,
            )
            print(f"  -> LLM Judge Verdict: '{judge_res.verdict}' (Expected: 'reject')")
            print(f"  -> Rejection Reason: '{judge_res.rejection_reason}'")
            assert judge_res.verdict == "reject"
            assert "locked or deleted" in judge_res.rejection_reason.lower()

        # Check DB to verify edge was NOT overwritten
        with get_db_cursor() as cur:
            cur.execute("SELECT reason, locked, status FROM edges WHERE id = %s;", (edge_id,))
            db_row = cur.fetchone()
            print(f"  -> DB verification: reason='{db_row[0][:40]}...', locked={db_row[1]}, status='{db_row[2]}'")
            assert db_row[0] == edit_payload["reason"], "User edit was overwritten!"
            assert db_row[1] is True

        # TEST 4: Soft-Delete Link
        print_banner("TEST 4: Soft-Deleting Link and Checking Retention")
        res_del = client.delete(f"/api/edges/{edge_id}")
        assert res_del.status_code == 200, f"Expected 200, got {res_del.status_code}: {res_del.text}"
        del_action = res_del.json()
        print(f"  -> Soft-delete action: success={del_action['success']}, status='{del_action['status']}', locked={del_action['locked']}")
        assert del_action["success"] is True
        assert del_action["status"] == "deleted"
        assert del_action["locked"] is True

        # Verify active edge listing excludes it
        active_list = client.get("/api/edges?include_deleted=false").json()
        assert not any(e["id"] == edge_id for e in active_list), "Soft-deleted edge must not appear in active list!"
        print("  -> Edge successfully hidden from active graph query.")

        # Verify include_deleted=true includes it
        all_list = client.get("/api/edges?include_deleted=true").json()
        found_deleted = next((e for e in all_list if e["id"] == edge_id), None)
        assert found_deleted is not None, "Soft-deleted edge must be retained for memory/audit!"
        print(f"  -> Edge retained in audit query with status='{found_deleted['status']}', locked={found_deleted['locked']}.")

        # TEST 5: Pipeline Re-Run Protection against Deleted Link
        print_banner("TEST 5: Simulating Pipeline Re-Run on Soft-Deleted Link")
        with get_db_cursor() as cur:
            del_neighbors = finder._query_neighbors(
                focal_topic_id=topic_a_id,
                focal_subject_id=subject_id,
                same_subject=True,
                threshold=0.0,
                k=10,
                cursor=cur,
            )
            matched_del = [c for c in del_neighbors if c.topic_b_id == topic_b_id or c.topic_a_id == topic_b_id]
            print(f"  -> Candidates returned for deleted pair: {len(matched_del)} (Expected: 0)")
            assert len(matched_del) == 0, "Candidate finder must NEVER return soft-deleted pairs!"

            del_judge_res, _ = judge.judge_candidate(
                candidate_id=None,
                topic_a_id=topic_a_id,
                topic_b_id=topic_b_id,
                scope="same_subject",
                cursor=cur,
            )
            print(f"  -> LLM Judge Verdict: '{del_judge_res.verdict}' (Expected: 'reject')")
            print(f"  -> Rejection Reason: '{del_judge_res.rejection_reason}'")
            assert del_judge_res.verdict == "reject"
            assert "locked or deleted" in del_judge_res.rejection_reason.lower()

        with get_db_cursor() as cur:
            cur.execute("SELECT status, locked, is_visible FROM edges WHERE id = %s;", (edge_id,))
            final_row = cur.fetchone()
            print(f"  -> DB row remains intact: status='{final_row[0]}', locked={final_row[1]}, is_visible={final_row[2]}")
            assert final_row[0] == "deleted"
            assert final_row[1] is True
            assert final_row[2] is False

        print_banner("ALL T10 VERIFICATION TESTS PASSED SUCCESSFULLY!")

    finally:
        # Cleanup test data
        print("\n[Cleanup] Cleaning up temporary test data...")
        with get_db_cursor() as cur:
            cur.execute("DELETE FROM edges WHERE topic_a IN (%s, %s) OR topic_b IN (%s, %s);", (topic_a_id, topic_b_id, topic_a_id, topic_b_id))
            cur.execute("DELETE FROM link_candidates WHERE topic_a IN (%s, %s) OR topic_b IN (%s, %s);", (topic_a_id, topic_b_id, topic_a_id, topic_b_id))
            cur.execute("DELETE FROM topics WHERE id IN (%s, %s);", (topic_a_id, topic_b_id))
            cur.execute("DELETE FROM subjects WHERE id = %s;", (subject_id,))
        print("  -> Cleanup complete.")


if __name__ == "__main__":
    run_tests()

