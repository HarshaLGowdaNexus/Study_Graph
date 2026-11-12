"""
Unit & Integration Tests for Offline Demo Mode and Demo Service (Task T21).
Verifies:
  - Frozen graph loading from local snapshots without database.
  - Scripted grounded chat citations for demo questions.
  - Honest 'not found in notes' fallback for out-of-notes questions.
  - Scripted exam mode concepts and 2/5/10-mark answers.
  - Instant demo upload simulation.
  - FastAPI endpoints operating in offline demo mode.

Relies on:
  - Risks R01, R17
  - Quality Gate G10
"""

import os
from unittest.mock import patch
import pytest

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.services.demo_service import demo_service


def test_frozen_graph_integrity():
    """
    Ensures that the frozen demo graph snapshot contains valid subjects,
    topics, clusters, and cross-subject links with evidence.
    """
    graph = demo_service.get_frozen_graph()
    assert "nodes" in graph
    assert "links" in graph
    assert "subjects" in graph
    assert len(graph["nodes"]) >= 10
    assert len(graph["subjects"]) >= 2

    # Verify that at least one cross-subject link exists with dual evidence
    cross_links = [
        l for l in graph["links"]
        if l.get("is_cross_subject") or l.get("scope") == "cross_subject" or l.get("source_subject_id") != l.get("target_subject_id")
    ]
    assert len(cross_links) >= 1
    sample_link = cross_links[0]
    assert "reason" in sample_link or "type" in sample_link
    assert sample_link.get("strength", 0) >= 3


def test_scripted_chat_grounded_answer():
    """
    Verifies that asking a scripted in-notes question (e.g. TCP 3-way handshake)
    returns exact citations without calling external AI APIs.
    """
    question = "How does the TCP 3-way handshake establish a connection?"
    answer_res = demo_service.get_scripted_chat_answer(question)
    assert answer_res is not None
    assert answer_res.answered_from == "notes"
    assert "SYN" in answer_res.text
    assert len(answer_res.citations) >= 1

    citation = answer_res.citations[0]
    assert citation.filename is not None
    assert citation.page >= 1
    assert citation.snippet is not None


def test_scripted_chat_honest_out_of_notes():
    """
    Verifies that asking an out-of-notes question returns 'Not found in your notes'
    with an honest labeled general knowledge answer (Rule 13.4, Risk R10).
    """
    question = "How does Shor's quantum algorithm factor large composite integers?"
    answer_res = demo_service.get_scripted_chat_answer(question)
    assert answer_res is not None
    assert answer_res.answered_from == "general"
    assert "Not found in your notes" in answer_res.text
    assert len(answer_res.citations) == 0


def test_scripted_exam_overview():
    """
    Verifies that the frozen exam data contains important concepts by graph importance
    and repeated questions with structured marks metadata.
    """
    overview = demo_service.get_scripted_exam_overview()
    assert overview is not None
    assert len(overview.important_concepts) >= 2
    assert len(overview.repeated_questions) >= 1

    q = overview.repeated_questions[0]
    assert q.canonical_question != ""
    assert q.repeat_count >= 1
    assert q.typical_marks is not None


def test_demo_upload_simulation():
    """
    Verifies that the demo note identifier and instant result work properly.
    """
    assert demo_service.is_demo_upload_file("demo_upload_sample.txt") is True
    assert demo_service.is_demo_upload_file("november_lecture_sample.pdf") is True
    assert demo_service.is_demo_upload_file("ordinary_notes.pdf") is False

    result = demo_service.get_demo_upload_result()
    assert result["status"] == "success"
    assert "document_id" in result


def test_fastapi_endpoints_in_offline_demo_mode():
    """
    Tests that FastAPI route handlers correctly route to demo_service when
    OFFLINE_DEMO_MODE is active.
    """
    from backend.app.api.deps import CurrentUser
    from backend.app.api.routes.chat import ask_chat_question
    from backend.app.api.routes.exam import get_exam_overview
    from backend.app.api.routes.graphs import get_cross_subject_graph, get_graph_config
    from backend.app.schemas.chat import ChatAskRequest

    test_user = CurrentUser(id="11111111-1111-4111-8111-111111111111", email="test@example.com")

    with patch.object(demo_service, "is_demo_mode", return_value=True), patch.object(settings, "OFFLINE_DEMO_MODE", True):
        # 1. Config endpoint reports offline demo mode
        config_data = get_graph_config()
        assert config_data["offline_demo_mode"] is True

        # 2. Cross-subject graph endpoint returns frozen demo snapshot
        graph_data = get_cross_subject_graph(current_user=test_user)
        assert len(graph_data["nodes"]) >= 10
        assert len(graph_data["subjects"]) >= 2

        # 3. Chat endpoint returns scripted citation response
        chat_req = ChatAskRequest(question="How does the TCP 3-way handshake establish a connection?")
        chat_res = ask_chat_question("sub-demo-cn", chat_req, test_user)
        assert chat_res.answered_from == "notes"
        assert len(chat_res.citations) >= 1

        # 4. Exam overview returns scripted concepts
        exam_res = get_exam_overview("sub-demo-cn", test_user)
        assert len(exam_res.important_concepts) >= 2

