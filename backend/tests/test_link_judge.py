"""
Automated Unit and Logic Tests for LLM Link Judge (Task T09).
Relies on:
  - Decision D04: Python with FastAPI
  - Decision D05: PostgreSQL on Supabase (edges, edge_evidence)
  - Decision D09: Google Gemini Flash
  - Decision D14: pytest testing framework
  - RULEBOOK.md Section 13:
      - Rule 1: No evidence, no link.
      - Rule 2: User edits are sacred.
      - Rule 8: Weak links hidden by default; cross-subject links need strength >= 3.
  - Risks:
      - R03: Wrong or nonsense links (verified snippets).
      - R19: Cross-subject links look forced.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

from backend.app.schemas.edge import LLMJudgeRawOutput
from backend.app.services.link_judge import (
    ALLOWED_LINK_TYPES,
    LinkJudgeService,
    normalize_for_verification,
)


# ==============================================================================
# 1. Unit Tests: Text Normalization and Snippet Verification Logic
# ==============================================================================


def test_normalize_for_verification():
    """Verify smart quotes, dashes, newlines, and capitalization are normalized."""
    raw = '  “The TCP Handshake—it’s crucial for reliable connection!”  \n\t  '
    normalized = normalize_for_verification(raw)
    assert normalized == 'the tcp handshake-it\'s crucial for reliable connection!'


def test_verify_snippet_exact_match():
    """Verify that an exact verbatim excerpt from a source chunk passes verification."""
    service = LinkJudgeService()
    chunk_1_id = str(uuid4())
    chunk_2_id = str(uuid4())

    chunks = [
        {
            "id": chunk_1_id,
            "text": "The Transmission Control Protocol establishes connections using a three-way handshake before transmitting data packets.",
        },
        {
            "id": chunk_2_id,
            "text": "UDP is a connectionless transport protocol providing low latency at the cost of reliability.",
        },
    ]

    snippet = "establishes connections using a three-way handshake"
    verified, matched_id = service.verify_snippet_in_chunks(snippet, chunks, suggested_chunk_id=chunk_1_id)

    assert verified is True
    assert matched_id == chunk_1_id


def test_verify_snippet_tampered_fails():
    """Verify that tampering with even a single word in the snippet causes immediate failure."""
    service = LinkJudgeService()
    chunk_id = str(uuid4())
    chunks = [
        {
            "id": chunk_id,
            "text": "QuickSort chooses a pivot element and partitions the array into two sub-arrays around the pivot.",
        }
    ]

    # Tampered snippet: "pivot element" replaced by "median element"
    tampered_snippet = "QuickSort chooses a median element and partitions the array"
    verified, matched_id = service.verify_snippet_in_chunks(tampered_snippet, chunks)

    assert verified is False
    assert matched_id is None


def test_verify_snippet_empty_or_short_fails():
    """Verify that empty or excessively short snippets are rejected."""
    service = LinkJudgeService()
    chunks = [{"id": str(uuid4()), "text": "Some text content in chunk."}]

    assert service.verify_snippet_in_chunks("", chunks)[0] is False
    assert service.verify_snippet_in_chunks("abc", chunks)[0] is False
    assert service.verify_snippet_in_chunks(None, chunks)[0] is False


# ==============================================================================
# 2. Unit Tests: Strict Link Types and Schema Validation
# ==============================================================================


def test_allowed_link_types_set():
    """Ensure the allowed link types strictly match the T09 specification."""
    expected_types = {
        "prerequisite_of",
        "same_concept",
        "example_of",
        "applies_in",
        "contrasts_with",
        "part_of",
    }
    assert ALLOWED_LINK_TYPES == expected_types


# ==============================================================================
# 3. Unit Tests: Candidate Judge Decision and Persistence Logic
# ==============================================================================


def test_judge_candidate_rejection_by_llm():
    """When the LLM judge explicitly returns verdict='reject', no edge is created."""
    service = LinkJudgeService()
    candidate_id = uuid4()
    topic_a_id = uuid4()
    topic_b_id = uuid4()

    mock_cursor = MagicMock()
    # 1. No existing edge
    mock_cursor.fetchone.side_effect = [
        None,  # existing edge check
        {"id": str(topic_a_id), "keyword": "Bubble Sort", "subject_id": str(uuid4()), "subject_name": "CS"},
        {"id": str(topic_b_id), "keyword": "Mitochondria", "subject_id": str(uuid4()), "subject_name": "Bio"},
    ]
    # Source chunks
    mock_cursor.fetchall.side_effect = [
        [{"id": str(uuid4()), "text": "Bubble sort repeatedly swaps adjacent elements.", "page": 1}],
        [{"id": str(uuid4()), "text": "Mitochondria is the powerhouse of the cell.", "page": 1}],
    ]

    # Mock Gemini Flash returning 'reject'
    mock_llm_output = LLMJudgeRawOutput(
        verdict="reject",
        rejection_reason="Computer science sorting algorithm and cellular biology have no conceptual relationship.",
    )

    with patch.object(service, "_call_gemini_judge", return_value=(mock_llm_output, {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})):
        result, tokens = service.judge_candidate(
            candidate_id=candidate_id,
            topic_a_id=topic_a_id,
            topic_b_id=topic_b_id,
            scope="cross_subject",
            cursor=mock_cursor,
        )

    assert result.verdict == "reject"
    assert "rejection_reason" in result.model_dump()
    assert result.edge_id is None
    assert result.snippets_verified is False
    # Candidate status should be updated to dismissed
    mock_cursor.execute.assert_any_call(
        "UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;",
        (str(candidate_id),),
    )


def test_judge_candidate_snippet_verification_failure_auto_rejects():
    """If the LLM returns verdict='accept' but fabricates a snippet, the link is auto-rejected."""
    service = LinkJudgeService()
    candidate_id = uuid4()
    topic_a_id = uuid4()
    topic_b_id = uuid4()
    chunk_a_id = str(uuid4())
    chunk_b_id = str(uuid4())

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        None,  # existing edge check
        {"id": str(topic_a_id), "keyword": "QuickSort", "subject_id": str(uuid4()), "subject_name": "Algorithms"},
        {"id": str(topic_b_id), "keyword": "Divide and Conquer", "subject_id": str(uuid4()), "subject_name": "Algorithms"},
    ]
    mock_cursor.fetchall.side_effect = [
        [{"id": chunk_a_id, "text": "QuickSort is a comparison-based sorting algorithm.", "page": 1}],
        [{"id": chunk_b_id, "text": "Divide and conquer breaks down a problem into smaller subproblems.", "page": 1}],
    ]

    # LLM hallucinates a quote not in Topic A's chunk
    mock_llm_output = LLMJudgeRawOutput(
        verdict="accept",
        type="example_of",
        reason="QuickSort demonstrates the divide and conquer paradigm.",
        industry_example="Used in C++ std::sort standard library implementation.",
        strength=4,
        snippet_a="Invented by Tony Hoare in 1959 to sort words efficiently.",  # NOT IN CHUNK!
        chunk_id_a=chunk_a_id,
        snippet_b="Divide and conquer breaks down a problem into smaller subproblems.",  # IN CHUNK
        chunk_id_b=chunk_b_id,
    )

    with patch.object(service, "_call_gemini_judge", return_value=(mock_llm_output, {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200})):
        result, _ = service.judge_candidate(
            candidate_id=candidate_id,
            topic_a_id=topic_a_id,
            topic_b_id=topic_b_id,
            scope="same_subject",
            cursor=mock_cursor,
        )

    # Must be auto-rejected!
    assert result.verdict == "reject"
    assert result.snippets_verified is False
    assert result.verification_error is not None
    assert "Snippet A not found in Topic A chunks" in result.verification_error
    assert result.edge_id is None


def test_judge_candidate_success_same_subject():
    """Verify successful acceptance and edge persistence when snippets are valid."""
    service = LinkJudgeService()
    candidate_id = uuid4()
    topic_a_id = uuid4()
    topic_b_id = uuid4()
    chunk_a_id = str(uuid4())
    chunk_b_id = str(uuid4())
    generated_edge_id = uuid4()

    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        None,  # existing edge check
        {"id": str(topic_a_id), "keyword": "QuickSort", "subject_id": str(uuid4()), "subject_name": "Algorithms"},
        {"id": str(topic_b_id), "keyword": "Divide and Conquer", "subject_id": str(uuid4()), "subject_name": "Algorithms"},
        {"id": generated_edge_id},  # returning id from INSERT INTO edges
    ]
    mock_cursor.fetchall.side_effect = [
        [{"id": chunk_a_id, "text": "QuickSort is a comparison-based sorting algorithm using a pivot.", "page": 1}],
        [{"id": chunk_b_id, "text": "Divide and conquer breaks down a problem into smaller subproblems.", "page": 1}],
    ]

    mock_llm_output = LLMJudgeRawOutput(
        verdict="accept",
        type="example_of",
        reason="QuickSort partitions the array recursively, exemplifying divide and conquer.",
        industry_example="Used in search engines and high-frequency trading data indexing.",
        strength=4,
        snippet_a="QuickSort is a comparison-based sorting algorithm using a pivot.",
        chunk_id_a=chunk_a_id,
        snippet_b="Divide and conquer breaks down a problem into smaller subproblems.",
        chunk_id_b=chunk_b_id,
    )

    with patch.object(service, "_call_gemini_judge", return_value=(mock_llm_output, {"prompt_tokens": 150, "completion_tokens": 60, "total_tokens": 210})):
        result, tokens = service.judge_candidate(
            candidate_id=candidate_id,
            topic_a_id=topic_a_id,
            topic_b_id=topic_b_id,
            scope="same_subject",
            cursor=mock_cursor,
        )

    assert result.verdict == "accept"
    assert result.edge_id == generated_edge_id
    assert result.type == "example_of"
    assert result.strength == 4
    assert result.is_visible is True
    assert result.snippets_verified is True
    assert tokens["total_tokens"] == 210


def test_cross_subject_visibility_rules():
    """
    Verify cross-subject edges need strength >= 3 to be marked visible by default (Rule 13.8).
    Weak cross-subject edge (strength 2) must be saved with is_visible = False.
    Strong cross-subject edge (strength 4) must be saved with is_visible = True.
    """
    service = LinkJudgeService(cross_subject_min_visible_strength=3)
    chunk_a_id = str(uuid4())
    chunk_b_id = str(uuid4())

    # Test strength 2 (weak)
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [
        None,
        {"id": str(uuid4()), "keyword": "A", "subject_id": str(uuid4()), "subject_name": "CS"},
        {"id": str(uuid4()), "keyword": "B", "subject_id": str(uuid4()), "subject_name": "Math"},
        {"id": uuid4()},
    ]
    mock_cursor.fetchall.side_effect = [
        [{"id": chunk_a_id, "text": "Valid source note A text.", "page": 1}],
        [{"id": chunk_b_id, "text": "Valid source note B text.", "page": 1}],
    ]

    mock_llm_output_weak = LLMJudgeRawOutput(
        verdict="accept",
        type="applies_in",
        reason="Minor application of linear algebra concept.",
        industry_example="Game physics math modeling.",
        strength=2,  # < 3
        snippet_a="Valid source note A text.",
        chunk_id_a=chunk_a_id,
        snippet_b="Valid source note B text.",
        chunk_id_b=chunk_b_id,
    )

    with patch.object(service, "_call_gemini_judge", return_value=(mock_llm_output_weak, {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140})):
        res_weak, _ = service.judge_candidate(
            candidate_id=uuid4(),
            topic_a_id=uuid4(),
            topic_b_id=uuid4(),
            scope="cross_subject",
            cursor=mock_cursor,
        )

    # Must be marked not visible by default!
    assert res_weak.verdict == "accept"
    assert res_weak.strength == 2
    assert res_weak.is_visible is False


def test_locked_edge_is_sacred():
    """Verify that an existing edge that has locked=True or status='deleted' is never overwritten."""
    service = LinkJudgeService()
    candidate_id = uuid4()
    topic_a_id = uuid4()
    topic_b_id = uuid4()

    mock_cursor = MagicMock()
    # Existing edge is locked by user
    mock_cursor.fetchone.return_value = {
        "id": uuid4(),
        "locked": True,
        "status": "edited",
    }

    result, tokens = service.judge_candidate(
        candidate_id=candidate_id,
        topic_a_id=topic_a_id,
        topic_b_id=topic_b_id,
        scope="same_subject",
        cursor=mock_cursor,
    )

    assert result.verdict == "reject"
    assert "locked or deleted" in result.rejection_reason
    assert tokens["total_tokens"] == 0  # No LLM API call wasted
    # Candidate status marked dismissed
    mock_cursor.execute.assert_called_with(
        "UPDATE link_candidates SET status = 'dismissed' WHERE id = %s;",
        (str(candidate_id),),
    )

