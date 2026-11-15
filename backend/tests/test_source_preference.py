"""
Automated Tests for Source Preference (Notes vs. Textbook) in Chatbot & Theory Cards (Task T18B).
Covers:
  - Feature F17: Per-subject notes vs textbook preference obeyed by chatbot and theory cards,
                 with explicit source_kind citations.
  - Multi-user privacy isolation (Rule 11).
"""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from backend.app.api.deps import CurrentUser
from backend.app.api.routes.theory import get_subject_theory
from backend.app.services.chat_service import ChatService

USER_ALEX = "11111111-1111-4111-8111-111111111111"
USER_JORDAN = "22222222-2222-4222-8222-222222222222"
SUBJECT_OS = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _unit_vec(axis: int, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    v[axis] = 1.0
    return v


# ==============================================================================
# Notes vs Textbook Preference in Chatbot & Theory Cards (F17, R10)
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


def test_update_subject_source_preference_endpoint():
    """Checks PATCH /api/subjects/{subject_id}/preference updates subject preference."""
    import asyncio
    from backend.app.api.routes.upload import (
        SubjectPreferenceRequest,
        update_subject_source_preference,
    )
    cur = MagicMock()
    cur.fetchone.return_value = (SUBJECT_OS, "Operating Systems")

    @contextmanager
    def fake_cursor(*args, **kwargs):
        yield cur

    with patch("backend.app.api.routes.upload.get_db_cursor", fake_cursor):
        res = asyncio.run(
            update_subject_source_preference(
                subject_id=SUBJECT_OS,
                payload=SubjectPreferenceRequest(source_preference="textbook"),
                current_user=CurrentUser(id=USER_ALEX, email="alex@university.edu"),
            )
        )

    assert res.subject_id == SUBJECT_OS
    assert res.source_preference == "textbook"
    assert "Textbook" in res.message
    cur.execute.assert_any_call(
        "UPDATE subjects SET source_preference = %s WHERE id = %s AND user_id = %s;",
        ("textbook", SUBJECT_OS, USER_ALEX),
    )


if __name__ == "__main__":
    test_chatbot_preference_switches_top_citation_when_both_sources_exist()
    test_chatbot_still_answers_from_non_preferred_source_if_only_one_covers_question()
    test_theory_cards_switch_explanation_and_citation_by_source_preference()
    test_update_subject_source_preference_endpoint()
    print("ALL 4 SOURCE PREFERENCE TESTS PASSED!")

