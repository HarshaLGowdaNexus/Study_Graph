"""
Automated Tests for Syllabus Ghost Nodes, Coverage/Gaps & Source Preference (Task T18).
Covers:
  - Feature F16: Syllabus parsing into syllabus_topics, faded ghost nodes that light up on match,
                 per-module coverage & gap list, and manual match locking.
  - Feature F17: Per-subject notes vs textbook preference obeyed by chatbot and theory cards,
                 with explicit source_kind citations.
  - Risk R12: Preserves universities -> schemes -> syllabus_subjects hierarchy.
  - Risk R13: Empty graph shows syllabus ghost nodes before any notes arrive.
  - Rule 11: Multi-user privacy isolation.
"""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.api.deps import CurrentUser
from backend.app.api.routes.theory import get_subject_theory
from backend.app.schemas.syllabus import SyllabusMatchDecision
from backend.app.services.chat_service import ChatService
from backend.app.services.graph_service import GraphService
from backend.app.services.syllabus_service import SyllabusService, _fallback_parse_syllabus

USER_ALEX = "11111111-1111-4111-8111-111111111111"
USER_JORDAN = "22222222-2222-4222-8222-222222222222"
SUBJECT_OS = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _unit_vec(axis: int, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    v[axis] = 1.0
    return v


# ==============================================================================
# 1. Syllabus Parsing & University/Scheme Schema Hierarchy (F16, R12)
# ==============================================================================


def test_fallback_syllabus_parser_splits_modules_and_items():
    raw = """
    Module 1: Process States, CPU Scheduling; Context Switch
    Unit 2:
    - Deadlock Prevention
    - Banker's Algorithm
    """
    parsed = _fallback_parse_syllabus(raw)
    titles = [(t.module_no, t.title) for t in parsed.topics]
    assert (1, "Process States") in titles
    assert (1, "CPU Scheduling") in titles
    assert (1, "Context Switch") in titles
    assert (2, "Deadlock Prevention") in titles
    assert (2, "Banker's Algorithm") in titles


def test_ensure_syllabus_hierarchy_keeps_university_and_scheme():
    """Verifies universities -> schemes -> syllabus_subjects foreign keys are created & linked (R12)."""
    svc = SyllabusService(embedding_service=MagicMock())
    cur = MagicMock()
    uni_id = str(uuid4())
    scheme_id = str(uuid4())
    syl_sub_id = str(uuid4())

    cur.fetchone.side_effect = [
        None,  # university not found
        {"id": uni_id},  # INSERT university RETURNING id
        None,  # scheme not found
        {"id": scheme_id},  # INSERT scheme RETURNING id
        {"id": syl_sub_id},  # INSERT syllabus_subjects RETURNING id
    ]

    subject_row = {"id": SUBJECT_OS, "name": "Operating Systems", "syllabus_subject_id": None}
    created_id = svc._ensure_syllabus_subject_hierarchy(
        cursor=cur,
        subject_row=subject_row,
        university_name="VTU Belagavi",
        scheme_name="2022 Scheme",
        subject_code="BCS401",
        semester=4,
        branch="CSE",
    )

    assert created_id == syl_sub_id
    executed_sql = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "INSERT INTO universities" in executed_sql
    assert "INSERT INTO schemes" in executed_sql
    assert "INSERT INTO syllabus_subjects" in executed_sql
    assert "UPDATE subjects SET syllabus_subject_id" in executed_sql


# ==============================================================================
# 2. Ghost Nodes Emission & Lighting Up on Match (F16, R13)
# ==============================================================================


def test_graph_service_emits_ghost_nodes_and_lights_up_matched_topics():
    """
    Before notes cover a syllabus topic, GraphService emits it as a faded ghost node (is_ghost=True).
    Once a real topic has syllabus_topic_id pointing to it, the ghost disappears and only the lit node appears.
    """
    syl_covered_id = str(uuid4())
    syl_gap_id = str(uuid4())
    real_topic_id = str(uuid4())
    syl_sub_id = str(uuid4())

    cur = MagicMock()
    cur.fetchone.return_value = {
        "id": SUBJECT_OS,
        "name": "Operating Systems",
        "source_preference": "notes",
        "syllabus_subject_id": syl_sub_id,
    }
    cur.fetchall.side_effect = [
        # topics (covers syl_covered_id)
        [
            {
                "id": real_topic_id,
                "keyword": "Process Scheduling",
                "explanation": "Assigns CPU time to ready processes.",
                "real_world_use": "Linux CFS scheduler",
                "module_no": 1,
                "reviewed": True,
                "cluster_id": None,
                "syllabus_topic_id": syl_covered_id,
                "syllabus_match_locked": False,
                "syllabus_title": "CPU Scheduling",
                "cluster_label": None,
                "parent_cluster_id": None,
                "parent_cluster_label": None,
                "aliases": [],
            }
        ],
        # syllabus_rows (one covered, one uncovered gap)
        [
            {"id": syl_covered_id, "module_no": 1, "title": "CPU Scheduling", "reviewed": True},
            {"id": syl_gap_id, "module_no": 2, "title": "Banker's Algorithm", "reviewed": False},
        ],
        # edges
        [],
        # clusters
        [],
    ]

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    gs = GraphService()
    with patch("backend.app.services.graph_service.get_db_cursor", fake_cursor):
        graph = gs.assemble_subject_graph(subject_id=SUBJECT_OS, user_id=USER_ALEX)

    real_nodes = [n for n in graph["nodes"] if not n["is_ghost"]]
    ghost_nodes = [n for n in graph["nodes"] if n["is_ghost"]]

    assert len(real_nodes) == 1
    assert real_nodes[0]["syllabus_topic_id"] == syl_covered_id
    assert len(ghost_nodes) == 1
    assert ghost_nodes[0]["id"] == f"ghost:{syl_gap_id}"
    assert ghost_nodes[0]["keyword"] == "Banker's Algorithm"
    assert graph["syllabus_coverage"]["coverage_percent"] == 50.0
    assert graph["syllabus_coverage"]["gap_count"] == 1


# ==============================================================================
# 3. Embedding + Confirmation Matching & Manual Match Lock (F16, Rule 13.2)
# ==============================================================================


def test_matching_uses_embeddings_plus_llm_and_respects_locks():
    """
    Unlocked topics are matched using embedding similarity + LLM confirmation.
    The SQL query explicitly filters `syllabus_match_locked = FALSE` so manual corrections are sacred.
    """
    syl_id = str(uuid4())
    topic_id = str(uuid4())
    syl_sub_id = str(uuid4())

    cur = MagicMock()
    cur.fetchone.return_value = {
        "id": SUBJECT_OS,
        "user_id": USER_ALEX,
        "syllabus_subject_id": syl_sub_id,
    }
    cur.fetchall.side_effect = [
        # syllabus_topics
        [{"id": syl_id, "module_no": 2, "title": "Deadlock Avoidance", "embedding": _unit_vec(0)}],
        # unlocked topics
        [
            {
                "id": topic_id,
                "keyword": "Banker Safety Check",
                "explanation": "Checks whether allocating resources keeps the system safe.",
                "module_no": 2,
                "embedding": [0.80, 0.60, 0, 0, 0, 0, 0, 0],  # cosine = 0.80 (between 0.62 and 0.92)
                "syllabus_topic_id": None,
                "syllabus_match_locked": False,
            }
        ],
    ]

    update_cur = MagicMock()

    @contextmanager
    def fake_cursor(*args, **kwargs):
        if kwargs.get("cursor_factory") is not None:
            yield cur
        else:
            yield update_cur

    svc = SyllabusService(embedding_service=MagicMock())
    with (
        patch("backend.app.services.syllabus_service.get_db_cursor", fake_cursor),
        patch.object(
            svc,
            "_confirm_match_with_llm",
            return_value=SyllabusMatchDecision(is_match=True, confidence=0.9, reason="Banker's algorithm implements deadlock avoidance."),
        ) as mock_llm,
        patch.object(
            svc,
            "get_subject_syllabus",
            return_value=MagicMock(coverage_percent=100.0),
        ),
    ):
        res = svc.match_subject_topics(subject_id=SUBJECT_OS, user_id=USER_ALEX, refresh_cache=False)

    assert res.matches_created == 1
    assert mock_llm.called
    # Verify unlocked-only SQL guard
    select_sql = str(cur.execute.call_args_list[2].args[0])
    assert "syllabus_match_locked" in select_sql
    update_sql = str(update_cur.execute.call_args_list[0].args[0])
    assert "syllabus_match_locked" in update_sql
    assert update_cur.execute.call_args_list[0].args[1] == (syl_id, topic_id)


def test_manual_match_correction_locks_and_updates_db():
    """Student correction sets syllabus_match_locked = TRUE."""
    syl_id = str(uuid4())
    topic_id = str(uuid4())
    syl_sub_id = str(uuid4())

    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"id": SUBJECT_OS, "user_id": USER_ALEX, "syllabus_subject_id": syl_sub_id, "name": "OS", "source_preference": "notes"},
        {"id": topic_id},
        {"id": syl_id},
    ]

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    svc = SyllabusService(embedding_service=MagicMock())
    with (
        patch("backend.app.services.syllabus_service.get_db_cursor", fake_cursor),
        patch.object(svc, "_safe_refresh_graph"),
        patch.object(svc, "get_subject_syllabus", return_value=MagicMock(coverage_percent=100.0)) as mock_get,
    ):
        svc.correct_topic_match(
            user_id=USER_ALEX,
            subject_id=SUBJECT_OS,
            topic_id=topic_id,
            syllabus_topic_id=syl_id,
        )

    update_call = cur.execute.call_args_list[-1]
    assert "syllabus_match_locked = TRUE" in str(update_call.args[0])
    assert update_call.args[1] == (syl_id, topic_id, SUBJECT_OS)
    assert mock_get.called


def test_coverage_and_gaps_computed_per_module():
    syl_sub_id = str(uuid4())
    s1, s2, s3 = str(uuid4()), str(uuid4()), str(uuid4())
    t1 = str(uuid4())

    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"id": SUBJECT_OS, "user_id": USER_ALEX, "syllabus_subject_id": syl_sub_id, "name": "OS", "source_preference": "notes"},
        {
            "syllabus_subject_id": syl_sub_id,
            "subject_code": "BCS401",
            "semester": 4,
            "branch": "CSE",
            "scheme_id": str(uuid4()),
            "scheme_name": "2022 Scheme",
            "university_id": str(uuid4()),
            "university_name": "VTU",
        },
    ]
    cur.fetchall.side_effect = [
        [
            {"id": s1, "syllabus_subject_id": syl_sub_id, "module_no": 1, "title": "Process States", "parent_id": None, "reviewed": True},
            {"id": s2, "syllabus_subject_id": syl_sub_id, "module_no": 1, "title": "Threads", "parent_id": None, "reviewed": True},
            {"id": s3, "syllabus_subject_id": syl_sub_id, "module_no": 2, "title": "Paging", "parent_id": None, "reviewed": False},
        ],
        [
            {"id": t1, "keyword": "Process Control Block", "module_no": 1, "syllabus_topic_id": s1, "syllabus_match_locked": False},
        ],
    ]

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    svc = SyllabusService(embedding_service=MagicMock())
    with patch("backend.app.services.syllabus_service.get_db_cursor", fake_cursor):
        res = svc.get_subject_syllabus(user_id=USER_ALEX, subject_id=SUBJECT_OS)

    assert res.total_syllabus_topics == 3
    assert res.covered_count == 1
    assert res.gap_count == 2
    assert res.coverage_percent == 33.3
    assert len(res.modules) == 2
    assert res.modules[0].coverage_percent == 50.0
    assert res.modules[1].coverage_percent == 0.0
    assert [g.title for g in res.gaps] == ["Threads", "Paging"]


# ==============================================================================
# 4. Notes vs Textbook Preference in Chatbot & Theory Cards (F17, R10)
# ==============================================================================


def test_chatbot_preference_switches_top_citation_when_both_sources_exist():
    """
    When both Lecture Notes and Textbook have relevant chunks that compete,
    switching subject source_preference between 'notes' and 'textbook' flips which source ranks #1 and is cited.
    """
    notes_chunk = {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "page": 3,
        "text": "Lecture notes define Thrashing as spending more time paging than executing.",
        "filename": "OS_Lecture_Notes.pdf",
        "source_kind": "notes",
        "similarity": 0.80,
    }
    textbook_chunk = {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "page": 412,
        "text": "Silberschatz textbook states high paging activity causing low CPU utilization is thrashing.",
        "filename": "Silberschatz_OS_Textbook.pdf",
        "source_kind": "textbook",
        "similarity": 0.82,
    }

    mock_emb = MagicMock()
    mock_emb.generate_single_embedding.return_value = _unit_vec(0)
    chat = ChatService(embedding_service=mock_emb)

    # Case A: source_preference = 'notes' -> Notes (0.80 + 0.08 = 0.88) beats Textbook (0.82)
    cur_notes = MagicMock()
    cur_notes.fetchone.side_effect = [
        {"id": SUBJECT_OS, "name": "OS", "source_preference": "notes"},
        {"id": str(uuid4()), "created_at": datetime.utcnow()},
    ]
    cur_notes.fetchall.return_value = [textbook_chunk, notes_chunk]

    with patch.object(chat, "_generate_with_retry", return_value=("From Lecture Notes: Thrashing occurs when...", {"total_tokens": 20})):
        res_notes = chat.ask_question(user_id=USER_ALEX, subject_id=SUBJECT_OS, question="What is thrashing?", cursor=cur_notes)

    assert res_notes.active_source_preference == "notes"
    assert res_notes.citations[0].source_kind == "notes"
    assert res_notes.citations[0].filename == "OS_Lecture_Notes.pdf"

    # Case B: source_preference = 'textbook' -> Textbook (0.82 + 0.08 = 0.90) beats Notes (0.80)
    cur_tb = MagicMock()
    cur_tb.fetchone.side_effect = [
        {"id": SUBJECT_OS, "name": "OS", "source_preference": "textbook"},
        {"id": str(uuid4()), "created_at": datetime.utcnow()},
    ]
    cur_tb.fetchall.return_value = [textbook_chunk, notes_chunk]

    with patch.object(chat, "_generate_with_retry", return_value=("From Textbook: Thrashing is high paging activity...", {"total_tokens": 20})):
        res_tb = chat.ask_question(user_id=USER_ALEX, subject_id=SUBJECT_OS, question="What is thrashing?", cursor=cur_tb)

    assert res_tb.active_source_preference == "textbook"
    assert res_tb.citations[0].source_kind == "textbook"
    assert res_tb.citations[0].filename == "Silberschatz_OS_Textbook.pdf"


def test_chatbot_still_answers_from_non_preferred_source_if_only_one_covers_question():
    """Preference only arbitrates when both sources compete; never hides the sole answering source."""
    notes_irrelevant = {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "page": 1,
        "text": "Course syllabus overview.",
        "filename": "Notes.pdf",
        "source_kind": "notes",
        "similarity": 0.22,
    }
    textbook_hit = {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "page": 250,
        "text": "Belady's Anomaly occurs in FIFO page replacement.",
        "filename": "Textbook.pdf",
        "source_kind": "textbook",
        "similarity": 0.85,
    }
    cur = MagicMock()
    cur.fetchall.return_value = [textbook_hit, notes_irrelevant]

    chat = ChatService(embedding_service=MagicMock())
    top = chat.retrieve_chunks(
        user_id=USER_ALEX,
        subject_id=SUBJECT_OS,
        query_embedding=_unit_vec(0),
        source_preference="notes",
        cursor=cur,
    )
    assert top[0]["source_kind"] == "textbook"
    assert top[0]["filename"] == "Textbook.pdf"


def test_theory_cards_switch_explanation_and_citation_by_source_preference():
    """Theory View obeys subject source_preference when both notes and textbook variants exist."""
    topic_id = str(uuid4())
    variants = {
        "notes": {
            "explanation": "Notes version: Short 2-line class explanation of Paging.",
            "real_world_use": "OS virtual memory",
            "filename": "Class_Notes.pdf",
            "page": 4,
        },
        "textbook": {
            "explanation": "Textbook version: Fixed-size frame mapping in physical memory.",
            "real_world_use": "x86-64 MMU page tables",
            "filename": "OS_Textbook.pdf",
            "page": 355,
        },
    }

    def _run_theory_for_pref(pref: str):
        cur = MagicMock()
        cur.fetchone.return_value = {"id": SUBJECT_OS, "name": "OS", "source_preference": pref}
        cur.fetchall.side_effect = [
            [
                {
                    "id": topic_id,
                    "subject_id": SUBJECT_OS,
                    "keyword": "Paging",
                    "explanation": variants["notes"]["explanation"],
                    "real_world_use": variants["notes"]["real_world_use"],
                    "module_no": 2,
                    "reviewed": True,
                    "source_variants": variants,
                    "syllabus_topic_id": None,
                    "syllabus_match_locked": False,
                    "syllabus_title": None,
                    "cluster_label": "Memory",
                    "source_citations": [
                        {"filename": "Class_Notes.pdf", "page": 4, "source_kind": "notes"},
                        {"filename": "OS_Textbook.pdf", "page": 355, "source_kind": "textbook"},
                    ],
                }
            ],
            [],  # edges
        ]

        @contextmanager
        def fake_cursor(*args, **kwargs):
            yield cur

        with patch("backend.app.api.routes.theory.get_db_cursor", fake_cursor):
            return get_subject_theory(
                subject_id=SUBJECT_OS,
                current_user=CurrentUser(id=USER_ALEX, email="alex@university.edu"),
            )

    res_notes = _run_theory_for_pref("notes")
    card_notes = res_notes.modules[0].topics[0]
    assert card_notes.active_source_kind == "notes"
    assert card_notes.has_multiple_sources is True
    assert "Notes version" in card_notes.explanation
    assert card_notes.source_citations[0].source_kind == "notes"

    res_tb = _run_theory_for_pref("textbook")
    card_tb = res_tb.modules[0].topics[0]
    assert card_tb.active_source_kind == "textbook"
    assert "Textbook version" in card_tb.explanation
    assert card_tb.source_citations[0].source_kind == "textbook"


def test_syllabus_route_enforces_user_privacy():
    """Another user cannot access or mutate a student's syllabus or source preference (Rule 11)."""
    cur = MagicMock()
    cur.fetchone.return_value = None

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    svc = SyllabusService(embedding_service=MagicMock())
    with patch("backend.app.services.syllabus_service.get_db_cursor", fake_cursor):
        with pytest.raises(HTTPException) as exc:
            svc.get_subject_syllabus(user_id=USER_JORDAN, subject_id=SUBJECT_OS)
        assert exc.value.status_code == 404
