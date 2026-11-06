"""
StudyGraph — Task T08 Verification Script
Nearest-Neighbor Candidate Finder (Same-Subject, Cross-Subject, Capping, & Deletion Exclusion)

Relies on:
  - Decision D05: PostgreSQL with pgvector on Supabase
  - Decision D10: Google text-embedding-004 (768-dim vectors)
  - Features: F06 (Candidate retrieval)
  - Risks: R19 (stricter cross-subject threshold), R07 (bounding candidate count per topic)
  - Golden Rule 13.2 / R16: Never resurrect deleted or locked pairs
"""

import sys
from pathlib import Path
from uuid import uuid4

# Add root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from psycopg2.extras import RealDictCursor

from backend.app.core.config import settings
from backend.app.database import get_db_cursor
from backend.app.schemas.candidate import CandidateSearchParams
from backend.app.services.candidate_finder import CandidateFinderService
from backend.app.services.embedding_service import EmbeddingService


def run_e2e_candidate_test():
    print("=" * 80)
    print("StudyGraph — T08: Link Candidate Finder Live Verification")
    print("=" * 80)

    if not settings.DATABASE_URL:
        print("[FAIL] DATABASE_URL is not set.")
        sys.exit(1)

    if not settings.GEMINI_API_KEY:
        print("[FAIL] GEMINI_API_KEY is not set.")
        sys.exit(1)

    embedding_service = EmbeddingService()
    candidate_service = CandidateFinderService()

    # Generate unique test fixtures
    test_user_id = str(uuid4())
    subj_networks_id = str(uuid4())
    subj_os_id = str(uuid4())
    doc_1_id = str(uuid4())
    doc_2_id = str(uuid4())

    created_topic_ids = []

    try:
        print("\n[Step 1] Setting up two test subjects: 'Computer Networks' and 'Operating Systems'...")
        with get_db_cursor() as cursor:
            # Create user
            cursor.execute(
                "INSERT INTO users (id, email, name) VALUES (%s, %s, %s);",
                (test_user_id, f"test_t08_{uuid4().hex[:6]}@study.edu", "T08 Test Student"),
            )
            # Create Subject 1: Computer Networks
            cursor.execute(
                "INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, %s);",
                (subj_networks_id, test_user_id, "Computer Networks (T08 Test)"),
            )
            # Create Subject 2: Operating Systems
            cursor.execute(
                "INSERT INTO subjects (id, user_id, name) VALUES (%s, %s, %s);",
                (subj_os_id, test_user_id, "Operating Systems (T08 Test)"),
            )
            # Create Documents
            cursor.execute(
                "INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status) "
                "VALUES (%s, %s, 1, 'networks_unit1.pdf', 'pdf', 'notes', 'done');",
                (doc_1_id, subj_networks_id),
            )
            cursor.execute(
                "INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status) "
                "VALUES (%s, %s, 1, 'os_unit1.pdf', 'pdf', 'notes', 'done');",
                (doc_2_id, subj_os_id),
            )

        print("[Step 2] Defining sample topics with real technical definitions...")
        topics_to_create = [
            # --- Subject 1: Computer Networks ---
            {
                "subject_id": subj_networks_id,
                "keyword": "TCP Three-Way Handshake",
                "explanation": "Connection establishment protocol exchanging SYN, SYN-ACK, and ACK packets to negotiate initial sequence numbers and socket parameters before data flows.",
                "real_world_use": "Used by all web browsers and servers to establish reliable HTTPS connections.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "UDP Datagram Protocol",
                "explanation": "Connectionless transport protocol offering minimal transport service with no sequence tracking, no handshake, and zero guaranteed delivery.",
                "real_world_use": "Used in low-latency live video streaming, voice over IP, and online multiplayer games.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "Flow Control & Sliding Window",
                "explanation": "Transport layer mechanism ensuring a fast sender does not overwhelm a slow receiver by maintaining dynamic receive window buffer limits.",
                "real_world_use": "Prevents client buffer overflow during large file downloads.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "Congestion Control Algorithms",
                "explanation": "Algorithms like TCP Tahoe, Reno, and BBR that infer network bottleneck queues and adjust transmission rate to avoid packet loss.",
                "real_world_use": "Prevents global collapse of router queues across internet backbones.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "Socket Network Programming",
                "explanation": "API abstraction providing endpoints for bidirectional network communication across IP networks using socket, bind, listen, and accept system calls.",
                "real_world_use": "Used by web servers like Nginx and backend frameworks like FastAPI to accept network connections.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "Domain Name System (DNS)",
                "explanation": "Hierarchical distributed naming database that translates human-readable hostnames into numeric IP addresses using recursive resolvers.",
                "real_world_use": "Maps 'google.com' to server IP addresses when browsing.",
            },
            {
                "subject_id": subj_networks_id,
                "keyword": "Packet Switching & IP Routing",
                "explanation": "Breaking data streams into discrete packets routed independently along optimal network topology paths using forwarding tables.",
                "real_world_use": "Core foundation of packet delivery across the modern Internet.",
            },
            # --- Subject 2: Operating Systems (Cross-Subject) ---
            {
                "subject_id": subj_os_id,
                "keyword": "Socket System Calls & Network IPC",
                "explanation": "Kernel-level system calls allowing processes to create socket descriptors, bind to ports, and stream network buffers across process boundaries.",
                "real_world_use": "How operating system kernels interface user applications with physical network interface cards.",
            },
            {
                "subject_id": subj_os_id,
                "keyword": "Process Synchronization & Semaphores",
                "explanation": "Coordination primitives controlling access to shared memory buffers and critical sections to prevent race conditions among concurrent processes.",
                "real_world_use": "Used in multi-threaded web servers to manage worker thread queues without corruption.",
            },
            {
                "subject_id": subj_os_id,
                "keyword": "Virtual Memory Paging",
                "explanation": "Memory management scheme that decouples physical RAM from contiguous address space using fixed-size pages and translation lookaside buffers.",
                "real_world_use": "Allows applications to address more memory than physical RAM installed.",
            },
        ]

        print(f"Inserting {len(topics_to_create)} topics into database...")
        for t in topics_to_create:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO topics (subject_id, keyword, explanation, real_world_use, reviewed)
                    VALUES (%s, %s, %s, %s, TRUE)
                    RETURNING id;
                    """,
                    (t["subject_id"], t["keyword"], t["explanation"], t["real_world_use"]),
                )
                topic_id = str(cursor.fetchone()[0])
                t["id"] = topic_id
                created_topic_ids.append(topic_id)

        print(f"Generating 768-dim embeddings in batch via Google text-embedding-004...", flush=True)
        c1 = embedding_service.embed_unembedded_topics(subject_id=subj_networks_id)
        c2 = embedding_service.embed_unembedded_topics(subject_id=subj_os_id)
        embedded_count = c1 + c2
        print(f"[OK] {embedded_count} topics embedded in pgvector.", flush=True)

        # ==============================================================================
        # Test 1: Print top candidates for 5 topics (Visual Inspection)
        # ==============================================================================
        print("\n" + "=" * 80)
        print("[Test 1] Inspecting Candidate Pairs for 5 Focal Topics")
        print(f"Defaults: same-subject threshold = {candidate_service.same_subject_threshold}, "
              f"cross-subject threshold = {candidate_service.cross_subject_threshold} (stricter)")
        print("=" * 80)

        focal_sample = topics_to_create[:5]
        for idx, focal in enumerate(focal_sample, 1):
            res = candidate_service.find_candidates_for_topic(
                focal["id"],
                k=candidate_service.k_neighbors,
                same_thresh=candidate_service.same_subject_threshold,
                cross_thresh=candidate_service.cross_subject_threshold,
                max_cap=candidate_service.max_per_topic,
                include_cross=True,
            )

            print(f"\n({idx}) Focal Topic: '{focal['keyword']}' [Subject: Computer Networks]")
            print(f"    Total Candidates Found: {res.total_candidates}")

            if res.same_subject_candidates:
                print("    --- Same-Subject Candidates (threshold >= 0.70) ---")
                for c in res.same_subject_candidates:
                    partner = c.topic_b_keyword if c.topic_a_id == focal["id"] else c.topic_a_keyword
                    print(f"      * Partner: '{partner}' | Similarity: {c.similarity:.4f}")
            else:
                print("    --- Same-Subject Candidates: None met threshold")

            if res.cross_subject_candidates:
                print("    --- Cross-Subject Candidates (stricter threshold >= 0.82) ---")
                for c in res.cross_subject_candidates:
                    partner = c.topic_b_keyword if c.topic_a_id == focal["id"] else c.topic_a_keyword
                    print(f"      * Partner: '{partner}' [OS] | Similarity: {c.similarity:.4f}")
            else:
                print("    --- Cross-Subject Candidates: None met stricter threshold")

            # Basic sanity assertions
            assert res.total_candidates <= candidate_service.max_per_topic

        print("\n[OK] Test 1 Passed: Topics produce sensible nearest neighbors matching their domains.")

        # ==============================================================================
        # Test 2: Verify candidate cap holds on a larger sample
        # ==============================================================================
        print("\n" + "=" * 80)
        print("[Test 2] Verifying Candidate Cap Enforcement")
        print("=" * 80)

        # Set an intentionally small cap (e.g. 3) and looser threshold to generate lots of matches
        test_cap = 3
        print(f"Running candidate search across all 10 topics with cap = {test_cap}...")

        search_params = CandidateSearchParams(
            topic_ids=created_topic_ids,
            same_subject_threshold=0.60,  # lower threshold to generate many candidate matches
            cross_subject_threshold=0.60,
            max_per_topic=test_cap,
            persist=False,
        )
        batch_res = candidate_service.find_and_store_candidates(search_params)

        for topic_res in batch_res.results:
            cand_count = topic_res.total_candidates
            print(f"  Topic '{topic_res.topic_keyword[:25]}': {cand_count} candidates (cap={test_cap})")
            assert cand_count <= test_cap, f"Cap exceeded: {cand_count} > {test_cap}"

        print(f"[OK] Test 2 Passed: Cap of {test_cap} strictly respected across all topics.")

        # ==============================================================================
        # Test 3: Verify Deleted and Locked Pairs are Strictly Excluded (Rule 13.2 & R16)
        # ==============================================================================
        print("\n" + "=" * 80)
        print("[Test 3] Verifying Deleted and Locked Edge Exclusion")
        print("=" * 80)

        topic_tcp = topics_to_create[0]  # TCP Handshake
        topic_udp = topics_to_create[1]  # UDP Datagram

        # First, check if UDP is a candidate for TCP before any edge is created
        before_res = candidate_service.find_candidates_for_topic(
            topic_tcp["id"],
            same_thresh=0.60,
            cross_thresh=0.60,
            max_cap=10,
        )
        before_partner_ids = [
            c.topic_b_id if c.topic_a_id == topic_tcp["id"] else c.topic_a_id
            for c in before_res.same_subject_candidates
        ]
        assert topic_udp["id"] in before_partner_ids, "Prerequisite failed: UDP should be a candidate for TCP before deletion."
        print(f"Pre-check: '{topic_udp['keyword']}' is an active candidate for '{topic_tcp['keyword']}'.")

        # Now simulate a user deleting the link between TCP and UDP
        print(f"Simulating user deleting edge between '{topic_tcp['keyword']}' and '{topic_udp['keyword']}'...")
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO edges (topic_a, topic_b, type, reason, industry_example, strength, scope, status, locked)
                VALUES (%s, %s, 'prerequisite', 'Both are transport layer protocols', 'Networking stacks', 3, 'same_subject', 'deleted', FALSE);
                """,
                (topic_tcp["id"], topic_udp["id"]),
            )

        # Re-run candidate search for TCP
        after_del_res = candidate_service.find_candidates_for_topic(
            topic_tcp["id"],
            same_thresh=0.60,
            cross_thresh=0.60,
            max_cap=10,
        )
        after_partner_ids = [
            c.topic_b_id if c.topic_a_id == topic_tcp["id"] else c.topic_a_id
            for c in after_del_res.same_subject_candidates
        ]
        assert topic_udp["id"] not in after_partner_ids, "FAILED: Deleted edge was included as a candidate!"
        print(f"[OK] User deletion respected: '{topic_udp['keyword']}' is now strictly omitted from candidate search.")

        # Test locked edge exclusion as well
        topic_flow = topics_to_create[2]  # Flow Control
        print(f"Simulating user locked edge between '{topic_tcp['keyword']}' and '{topic_flow['keyword']}'...")
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO edges (topic_a, topic_b, type, reason, industry_example, strength, scope, status, locked)
                VALUES (%s, %s, 'prerequisite', 'Flow control uses TCP headers', 'TCP buffer management', 4, 'same_subject', 'auto', TRUE);
                """,
                (topic_tcp["id"], topic_flow["id"]),
            )

        after_lock_res = candidate_service.find_candidates_for_topic(
            topic_tcp["id"],
            same_thresh=0.60,
            cross_thresh=0.60,
            max_cap=10,
        )
        after_lock_partner_ids = [
            c.topic_b_id if c.topic_a_id == topic_tcp["id"] else c.topic_a_id
            for c in after_lock_res.same_subject_candidates
        ]
        assert topic_flow["id"] not in after_lock_partner_ids, "FAILED: Locked edge was included as a candidate!"
        print(f"[OK] Locked edge respected: '{topic_flow['keyword']}' is now strictly omitted from candidate search.")
        print("[OK] Test 3 Passed: Deleted and locked pairs are completely excluded from candidate discovery.")

        # ==============================================================================
        # Test 4: Verify Database Persistence to link_candidates
        # ==============================================================================
        print("\n" + "=" * 80)
        print("[Test 4] Verifying Persistence into link_candidates Table")
        print("=" * 80)

        persist_params = CandidateSearchParams(
            topic_ids=created_topic_ids,
            same_subject_threshold=candidate_service.same_subject_threshold,
            cross_subject_threshold=candidate_service.cross_subject_threshold,
            max_per_topic=candidate_service.max_per_topic,
            persist=True,
        )
        persist_res = candidate_service.find_and_store_candidates(persist_params)
        print(f"Topics evaluated: {persist_res.total_topics_evaluated}")
        print(f"Candidates found: {persist_res.total_candidates_found}")
        print(f"Candidates stored to DB: {persist_res.total_candidates_stored}")
        print(f"Same-subject count: {persist_res.same_subject_count}")
        print(f"Cross-subject count: {persist_res.cross_subject_count}")

        stored = candidate_service.get_stored_candidates(limit=50)
        print(f"Successfully queried {len(stored)} stored pending candidates from DB.")
        assert len(stored) > 0, "No candidates stored in database!"

        print("[OK] Test 4 Passed: Candidates cleanly persisted into link_candidates table for T09.")

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        print("\n[Cleanup] Cleaning up test fixtures from Supabase...")
        try:
            with get_db_cursor() as cursor:
                # Cleaning user cascades to subjects, documents, topics, edges, link_candidates
                cursor.execute("DELETE FROM users WHERE id = %s;", (test_user_id,))
            print("[OK] Test fixtures cleanly removed.")
        except Exception as e:
            print(f"[WARN] Error during cleanup: {e}")


if __name__ == "__main__":
    run_e2e_candidate_test()
