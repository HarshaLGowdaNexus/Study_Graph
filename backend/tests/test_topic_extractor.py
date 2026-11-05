"""
Automated unit and integration tests for Topic Extraction Service (T05).
Relies on:
  - Decision D14: pytest.
  - RULEBOOK Section 13:
      - Rule 1: No evidence, no link/topic (source chunk IDs strictly required).
      - Rule 3: Topic cards are short (keyword plus at most 4 lines, plus real-world use).
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from backend.app.schemas.topic import TopicExtractionItem, TopicExtractionResponse
from backend.app.services.topic_extractor import TopicExtractorService


def test_schema_valid_topic():
    """Verify that a compliant topic card parses cleanly."""
    valid_data = {
        "keyword": "Virtual Memory",
        "explanation": "Virtual memory is a memory management technique.\nIt provides an idealized abstraction of storage resources.\nIt uses page tables to translate virtual to physical addresses.\nIt enables processes to use more memory than physically present.",
        "real_world_use": "Used in modern operating systems like Linux and Windows to isolate process memory spaces.",
        "source_chunk_ids": ["11111111-1111-1111-1111-111111111111"],
    }
    item = TopicExtractionItem.model_validate(valid_data)
    assert item.keyword == "Virtual Memory"
    assert len(item.explanation.splitlines()) == 4
    assert len(item.source_chunk_ids) == 1


def test_schema_rejects_explanation_exceeding_4_lines():
    """Rulebook Section 13 Rule 3: Reject any topic whose explanation exceeds 4 lines."""
    invalid_data = {
        "keyword": "Virtual Memory",
        "explanation": "Line 1: Concept definition.\nLine 2: How it works.\nLine 3: Key trade-off.\nLine 4: Architecture implication.\nLine 5: Extra disallowed text.",
        "real_world_use": "Operating system memory paging.",
        "source_chunk_ids": ["11111111-1111-1111-1111-111111111111"],
    }
    with pytest.raises(ValidationError) as exc_info:
        TopicExtractionItem.model_validate(invalid_data)
    assert "exceeds 4 lines" in str(exc_info.value)


def test_schema_rejects_empty_keyword():
    """Verify that empty or whitespace-only keywords are rejected."""
    invalid_data = {
        "keyword": "   ",
        "explanation": "Valid explanation line 1.",
        "source_chunk_ids": ["11111111-1111-1111-1111-111111111111"],
    }
    with pytest.raises(ValidationError) as exc_info:
        TopicExtractionItem.model_validate(invalid_data)
    assert "cannot be empty" in str(exc_info.value)


def test_schema_rejects_missing_source_chunks():
    """Rulebook Section 13 Rule 1: No evidence, no topic. source_chunk_ids cannot be empty."""
    invalid_data = {
        "keyword": "Process Scheduling",
        "explanation": "Schedules processes in CPU queues.",
        "source_chunk_ids": [],
    }
    with pytest.raises(ValidationError) as exc_info:
        TopicExtractionItem.model_validate(invalid_data)
    assert "cite at least one valid source chunk ID" in str(exc_info.value)


def test_service_filters_out_fake_chunk_ids():
    """
    Verify that if the LLM hallucinates a chunk ID that was not provided,
    the topic extractor catches it, rejects the topic, and records the rejection reason.
    """
    service = TopicExtractorService()

    # Suppose we provide chunk ID 'chunk-real-123'
    chunks = [
        {
            "id": "chunk-real-123",
            "page": 1,
            "text": "Virtual memory maps virtual addresses to physical pages.",
        }
    ]

    # LLM hallucinates and cites 'chunk-fake-999'
    fake_response = TopicExtractionResponse(
        topics=[
            TopicExtractionItem(
                keyword="Virtual Memory",
                explanation="Paging mechanism for OS memory.\nTranslates addresses.",
                real_world_use="Linux page fault handling.",
                source_chunk_ids=["chunk-fake-999"],  # NOT IN INPUT!
            ),
            TopicExtractionItem(
                keyword="Page Tables",
                explanation="Data structure storing virtual-to-physical address mappings.",
                real_world_use="Hardware MMU lookups.",
                source_chunk_ids=["chunk-real-123"],  # REAL CHUNK
            ),
        ]
    )

    with patch.object(service, "_call_gemini_structured", return_value=(fake_response, {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100})):
        valid_topics, rejected, tokens = service.extract_topics_from_chunk_group(
            chunks=chunks,
            subject_id="sub-123",
            module_no=1,
        )

    # The hallucinated topic must be filtered out
    assert len(valid_topics) == 1
    assert valid_topics[0].keyword == "Page Tables"

    # The rejected topic must be tracked with reason
    assert len(rejected) == 1
    assert rejected[0]["keyword"] == "Virtual Memory"
    assert "Cited non-existent chunk IDs" in rejected[0]["reason"]


def test_service_retries_on_invalid_output():
    """Verify that the extractor retries once when an initial call fails."""
    service = TopicExtractorService()

    mock_client = MagicMock()
    # First attempt raises Exception, second attempt succeeds
    valid_mock_resp = MagicMock()
    valid_mock_resp.text = json.dumps({
        "topics": [
            {
                "keyword": "Semaphore",
                "explanation": "A synchronization variable used to control access to shared resources.",
                "real_world_use": "Prevents race conditions in multi-threaded database servers.",
                "source_chunk_ids": ["chunk-sem-1"],
            }
        ]
    })
    valid_mock_resp.usage_metadata.prompt_token_count = 80
    valid_mock_resp.usage_metadata.candidates_token_count = 40
    valid_mock_resp.usage_metadata.total_token_count = 120

    mock_client.models.generate_content.side_effect = [
        Exception("Malformed response from API"),
        valid_mock_resp,
    ]

    with patch.object(service, "_get_client", return_value=mock_client):
        parsed, tokens = service._call_gemini_structured("Test prompt")
        assert len(parsed.topics) == 1
        assert parsed.topics[0].keyword == "Semaphore"
        assert tokens["total_tokens"] == 120
        # Check that it tried twice
        assert mock_client.models.generate_content.call_count == 2


def test_empty_chunks_returns_empty_result():
    """Verify that empty chunk lists return cleanly without calling Gemini."""
    service = TopicExtractorService()
    valid_topics, rejected, tokens = service.extract_topics_from_chunk_group(
        chunks=[],
        subject_id="sub-123",
        module_no=1,
    )
    assert valid_topics == []
    assert rejected == []
    assert tokens["total_tokens"] == 0

