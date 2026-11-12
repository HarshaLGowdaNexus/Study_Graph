"""
Automated Tests for Exam Mode (Task T17).
Covers:
  - Feature F18: Important concepts ranked by graph connectivity & coverage ('by graph importance').
  - Feature F19: Repeated questions from uploaded papers ('from your uploaded papers') + clustering.
  - Feature F20: Marks-based answers (2 / 5 / 10 marks) with citations & honest fallback.
  - Risk R05: Honest message when no papers exist; never fabricate repeats.
  - Rule 11: Multi-user privacy isolation.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.schemas.exam import QuestionPairJudgement
from backend.app.services.chat_service import ChatService
from backend.app.services.exam_service import ExamService, _fallback_parse_questions

USER_ALEX = "11111111-1111-4111-8111-111111111111"
USER_JORDAN = "22222222-2222-4222-8222-222222222222"
SUBJECT_CN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _unit_vec(axis: int, dim: int = 16) -> list[float]:
    v = [0.0] * dim
    v[axis] = 1.0
    return v


# ==============================================================================
# 1. Important Concepts ("by graph importance") — Feature F18
# ==============================================================================


def test_important_concepts_ranked_and_labeled():
    """
    Hub topic connected across modules with more sources must rank above leaf/isolated topics,
    and every item must carry the honest label 'by graph importance'.
    """
    t_hub = str(uuid4())
    t_mid = str(uuid4())
    t_leaf = str(uuid4())
    t_iso = str(uuid4())

    topics = [
        {
            "id": t_hub,
            "keyword": "TCP Congestion Control",
            "explanation": "Controls packet sending rate using AIMD and slow start.",
            "real_world_use": "Prevents internet collapse under heavy traffic.",
            "module_no": 3,
            "reviewed": True,
            "source_count": 6,
        },
        {
            "id": t_mid,
            "keyword": "Sliding Window",
            "explanation": "Buffers multiple in-flight packets for flow control.",
            "real_world_use": "Used in TCP and video streaming protocols.",
            "module_no": 2,
            "reviewed": True,
            "source_count": 3,
        },
        {
            "id": t_leaf,
            "keyword": "Checksum",
            "explanation": "Detects corrupted bits in a segment.",
            "real_world_use": "Error detection in UDP and IPv4 headers.",
            "module_no": 1,
            "reviewed": False,
            "source_count": 1,
        },
        {
            "id": t_iso,
            "keyword": "Baud Rate",
            "explanation": "Symbol changes per second on a physical channel.",
            "real_world_use": "Modem signaling rate.",
            "module_no": 1,
            "reviewed": False,
            "source_count": 1,
        },
    ]

    edges = [
        {"id": str(uuid4()), "topic_a": t_hub, "topic_b": t_mid, "strength": 5, "scope": "same_subject"},
        {"id": str(uuid4()), "topic_a": t_hub, "topic_b": t_leaf, "strength": 4, "scope": "same_subject"},
        {"id": str(uuid4()), "topic_a": t_hub, "topic_b": str(uuid4()), "strength": 4, "scope": "cross_subject"},
    ]

    ranked = ExamService._rank_topics_by_graph(topics, edges, top_n=10)
    assert len(ranked) == 4
    assert ranked[0].keyword == "TCP Congestion Control"
    assert ranked[0].degree == 3
    assert ranked[0].weighted_degree == 13
    assert ranked[0].modules_covered == 3
    assert ranked[0].cross_subject_links == 1
    assert ranked[-1].keyword == "Baud Rate"
    assert ranked[-1].degree == 0
    assert all(item.label == "by graph importance" for item in ranked)


# ==============================================================================
# 2. Honest Empty State & Privacy Isolation — Risk R05, Rule 11
# ==============================================================================


def test_exam_overview_honest_empty_state_when_no_papers():
    """
    When 0 previous-year papers exist, Exam Mode must NOT fabricate repeated questions
    and must return an honest notice.
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": SUBJECT_CN, "name": "Computer Networks"}
    # fetchall calls: topics -> edges -> papers
    mock_cursor.fetchall.side_effect = [
        [],  # topics
        [],  # exam_papers (0 papers)
    ]

    service = ExamService()
    overview = service.get_exam_overview(subject_id=SUBJECT_CN, user_id=USER_ALEX, cursor=mock_cursor)

    assert overview.has_uploaded_papers is False
    assert overview.total_papers == 0
    assert overview.repeated_questions == []
    assert overview.important_concepts_label == "by graph importance"
    assert overview.repeated_questions_label == "from your uploaded papers"
    assert overview.honest_notice is not None
    assert "no previous-year papers" in overview.honest_notice.lower()
    assert "never invent" in overview.honest_notice.lower()


def test_exam_privacy_isolation_blocks_other_user():
    """Student B cannot access Student A's Exam Mode overview or delete Student A's paper."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    service = ExamService()
    with pytest.raises(HTTPException) as exc_info:
        service.get_exam_overview(subject_id=SUBJECT_CN, user_id=USER_JORDAN, cursor=mock_cursor)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as del_exc:
        service.delete_paper(
            subject_id=SUBJECT_CN,
            paper_id=str(uuid4()),
            user_id=USER_JORDAN,
            cursor=mock_cursor,
        )
    assert del_exc.value.status_code == 404


# ==============================================================================
# 3. Repeated Questions across 3 Papers (Embeddings + LLM Confirm) — Feature F19
# ==============================================================================


def test_repeated_questions_3_papers_clustering_and_distinct_count():
    """
    Simulates 3 uploaded papers sharing a semantically repeated question ('TCP 3-way handshake')
    plus a distinct single-paper question ('Dijkstra routing').
    Verifies:
      - Embeddings + LLM confirmation group all 3 papers' handshake questions into 1 cluster.
      - Distinct paper count is 3 (even if a question appeared twice in the same paper).
      - Label is 'from your uploaded papers'.
    """
    p1, p2, p3 = str(uuid4()), str(uuid4()), str(uuid4())
    q1, q2, q3 = str(uuid4()), str(uuid4()), str(uuid4())
    q_other = str(uuid4())

    handshake_vec_a = [0.95, 0.05] + [0.0] * 14
    handshake_vec_b = [0.93, 0.07] + [0.0] * 14
    handshake_vec_c = [0.94, 0.06] + [0.0] * 14
    dijkstra_vec = [0.0, 1.0] + [0.0] * 14

    rows = [
        {"id": q1, "paper_id": p1, "text": "Explain the TCP 3-way handshake.", "marks": 5, "embedding": handshake_vec_a},
        {"id": q2, "paper_id": p2, "text": "How does TCP establish a connection using SYN and ACK?", "marks": 5, "embedding": handshake_vec_b},
        {"id": q3, "paper_id": p3, "text": "Describe three-way handshake in TCP.", "marks": 10, "embedding": handshake_vec_c},
        {"id": q_other, "paper_id": p1, "text": "Explain Dijkstra's shortest path algorithm.", "marks": 10, "embedding": dijkstra_vec},
    ]

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows

    service = ExamService()
    with patch.object(
        service,
        "_confirm_question_pair",
        return_value=QuestionPairJudgement(
            is_same_question=True,
            confidence=0.96,
            canonical_question="Explain the TCP three-way handshake connection setup.",
            reason="All ask about TCP 3-way handshake.",
        ),
    ) as mock_confirm:
        cluster_count = service.recluster_subject_questions(SUBJECT_CN, cursor=mock_cursor)

    # 2 components: {q1, q2, q3} and {q_other}
    assert cluster_count == 2
    assert mock_confirm.call_count >= 2

    # Inspect SQL updates written back
    update_calls = [
        c[0][1]
        for c in mock_cursor.execute.call_args_list
        if "UPDATE exam_questions" in c[0][0]
    ]
    cluster_map = {qid: (ckey, canon) for ckey, canon, qid in update_calls}
    assert cluster_map[q1][0] == cluster_map[q2][0] == cluster_map[q3][0]
    assert cluster_map[q1][0] != cluster_map[q_other][0]
    assert "TCP three-way handshake" in cluster_map[q1][1]

    # Now verify get_exam_overview computes repeat_count = 3 of 3 papers
    overview_cursor = MagicMock()
    overview_cursor.fetchone.return_value = {"id": SUBJECT_CN, "name": "Computer Networks"}
    overview_cursor.fetchall.side_effect = [
        [],  # topics
        [
            {"paper_id": p1, "document_id": str(uuid4()), "year": 2022, "filename": "cn_2022.pdf", "status": "done", "uploaded_at": None, "question_count": 2},
            {"paper_id": p2, "document_id": str(uuid4()), "year": 2023, "filename": "cn_2023.pdf", "status": "done", "uploaded_at": None, "question_count": 1},
            {"paper_id": p3, "document_id": str(uuid4()), "year": 2024, "filename": "cn_2024.pdf", "status": "done", "uploaded_at": None, "question_count": 1},
        ],
        [
            {"question_id": q1, "paper_id": p1, "text": rows[0]["text"], "marks": 5, "cluster_key": "cluster_1", "canonical_question": "Explain the TCP three-way handshake connection setup.", "topic_id": None, "matched_topic_keyword": None, "year": 2022, "filename": "cn_2022.pdf"},
            {"question_id": q2, "paper_id": p2, "text": rows[1]["text"], "marks": 5, "cluster_key": "cluster_1", "canonical_question": "Explain the TCP three-way handshake connection setup.", "topic_id": None, "matched_topic_keyword": None, "year": 2023, "filename": "cn_2023.pdf"},
            {"question_id": q3, "paper_id": p3, "text": rows[2]["text"], "marks": 10, "cluster_key": "cluster_1", "canonical_question": "Explain the TCP three-way handshake connection setup.", "topic_id": None, "matched_topic_keyword": None, "year": 2024, "filename": "cn_2024.pdf"},
            {"question_id": q_other, "paper_id": p1, "text": rows[3]["text"], "marks": 10, "cluster_key": f"single_{q_other}", "canonical_question": rows[3]["text"], "topic_id": None, "matched_topic_keyword": None, "year": 2022, "filename": "cn_2022.pdf"},
        ],
    ]

    overview = service.get_exam_overview(subject_id=SUBJECT_CN, user_id=USER_ALEX, cursor=overview_cursor)
    assert overview.has_uploaded_papers is True
    assert overview.total_papers == 3
    assert overview.repeated_questions[0].repeat_count == 3
    assert overview.repeated_questions[0].total_papers == 3
    assert overview.repeated_questions[0].label == "from your uploaded papers"
    assert overview.repeated_questions[1].repeat_count == 1


def test_delete_paper_cascades_and_reports_remaining():
    """Deleting the last paper returns remaining_papers=0 and deletes underlying document."""
    paper_id = str(uuid4())
    doc_id = str(uuid4())

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        {"id": SUBJECT_CN, "name": "Computer Networks"},
        {"paper_id": paper_id, "document_id": doc_id, "storage_path": "local://study-documents/p1.pdf"},
        {"cnt": 0},
    ]

    service = ExamService()
    resp, storage_path = service.delete_paper(
        subject_id=SUBJECT_CN,
        paper_id=paper_id,
        user_id=USER_ALEX,
        cursor=mock_cursor,
    )

    assert resp.status == "deleted"
    assert resp.remaining_papers == 0
    assert resp.document_id == doc_id
    assert storage_path == "local://study-documents/p1.pdf"


# ==============================================================================
# 4. Marks-Based Chatbot Answers (2 / 5 / 10 Marks) — Feature F20
# ==============================================================================


@pytest.mark.parametrize(
    "marks,expected_instruction_snippet,mock_answer",
    [
        (2, "1 to 2 concise", "TCP 3-way handshake uses SYN, SYN-ACK, and ACK packets to establish a reliable connection."),
        (5, "3 to 5 short, structured bullet points", "TCP establishes connections via a 3-way handshake:\n- Client sends SYN\n- Server replies SYN-ACK\n- Client confirms ACK"),
        (10, "clear Markdown headings", "### Overview & Definition\nTCP uses a 3-way handshake.\n\n### Core Mechanism\n1. SYN\n2. SYN-ACK\n3. ACK\n\n### Real-World Use\nUsed in HTTP/HTTPS."),
    ],
)
def test_marks_based_chat_answers_with_citations(marks, expected_instruction_snippet, mock_answer):
    """
    Verifies that asking the same question at 2, 5, and 10 marks:
      1. Sends the appropriate length/structure prompt instructions to Gemini.
      2. Preserves marks on ChatAnswerResponse.
      3. Returns answered_from='notes' with real file & page citations.
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        {"id": SUBJECT_CN, "name": "Computer Networks"},
        {"id": str(uuid4()), "created_at": "2026-11-12T10:00:00Z"},
    ]
    mock_cursor.fetchall.return_value = [
        {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "page": 4,
            "text": "TCP establishes a reliable connection using a three-way handshake: SYN, SYN-ACK, and ACK.",
            "filename": "cn_mod2_transport.pdf",
            "source_kind": "notes",
            "similarity": 0.86,
        }
    ]

    mock_emb = MagicMock()
    mock_emb.generate_single_embedding.return_value = [0.1] * 768
    chat_service = ChatService(embedding_service=mock_emb)

    with patch.object(chat_service, "_generate_with_retry", return_value=(mock_answer, {"total_tokens": 100})) as mock_gen:
        resp = chat_service.ask_question(
            user_id=USER_ALEX,
            subject_id=SUBJECT_CN,
            question="Explain the TCP 3-way handshake.",
            marks=marks,
            cursor=mock_cursor,
        )

    prompt_sent = mock_gen.call_args.kwargs["prompt"]
    assert expected_instruction_snippet in prompt_sent
    assert resp.marks == marks
    assert resp.answered_from == "notes"
    assert resp.text == mock_answer
    assert len(resp.citations) == 1
    assert resp.citations[0].filename == "cn_mod2_transport.pdf"
    assert resp.citations[0].page == 4


def test_fallback_regex_paper_parser_extracts_numbered_questions():
    """Verifies fallback regex parser cleanly extracts numbered questions and marks."""
    sample_paper = """
    UNIVERSITY EXAM 2023 - COMPUTER NETWORKS
    Answer any FIVE questions.
    Q1. Explain the seven layers of the OSI reference model. [10 Marks]
    Q2. Compare TCP and UDP protocols with examples. (5M)
    3. Define subnet mask and CIDR notation. [2 Marks]
    """
    parsed = _fallback_parse_questions(sample_paper)
    assert parsed.detected_year == 2023
    assert len(parsed.questions) == 3
    assert parsed.questions[0].marks == 10
    assert parsed.questions[1].marks == 5
    assert parsed.questions[2].marks == 2
    assert "OSI reference model" in parsed.questions[0].text

