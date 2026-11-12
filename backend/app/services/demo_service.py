"""
Demo Service for StudyGraph (Task T21).
Manages offline demo fallback, frozen graph snapshot retrieval,
scripted ground-truth chat citations, and fast pre-computed upload results.

Relies on:
  - Decision D12: Local-first architecture.
  - Risk R17: Zero-glitch presentation fallback during live demos.
  - Quality Gate G10: 3 successful offline dry runs.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.schemas.chat import ChatAnswerResponse, CitationItem
from backend.app.schemas.exam import (
    ExamOverviewResponse,
    ImportantConceptItem,
    RepeatedQuestionCluster,
)
from backend.app.services.synthetic_graph_service import synthetic_graph_service

logger = logging.getLogger(__name__)

DEMO_DATA_DIR = settings.ROOT_DIR / "demo_data"


class DemoService:
    """
    Provides isolated offline responses for live demos to protect against
    venue Wi-Fi dropouts and external API latency spikes (R17).
    """

    def is_demo_mode(self) -> bool:
        """
        Returns True if OFFLINE_DEMO_MODE environment variable is set to true.
        """
        return settings.OFFLINE_DEMO_MODE

    def get_frozen_graph(self) -> Dict[str, Any]:
        """
        Loads the frozen multi-subject graph snapshot from local disk.
        Falls back to the synthetic cross-subject benchmark if snapshot is missing.
        """
        graph_file = DEMO_DATA_DIR / "frozen_demo_graph.json"
        if graph_file.exists():
            try:
                with open(graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info("[DemoService] Serving frozen demo graph snapshot from disk.")
                    return data
            except Exception as e:
                logger.warning(f"[DemoService] Failed to parse frozen graph: {e}. Using benchmark generator.")

        return synthetic_graph_service.generate_cross_subject_benchmark()

    def get_scripted_chat_answer(self, question: str, subject_id: Optional[str] = None) -> Optional[ChatAnswerResponse]:
        """
        Matches a question against verified ground-truth questions in scripted_chat_answers.json.
        Returns a ChatAnswerResponse with real citations, or None if no match is found.
        """
        answers_file = DEMO_DATA_DIR / "scripted_chat_answers.json"
        if not answers_file.exists():
            return None

        try:
            with open(answers_file, "r", encoding="utf-8") as f:
                qa_list: List[Dict[str, Any]] = json.load(f)
        except Exception as e:
            logger.error(f"[DemoService] Failed reading scripted answers: {e}")
            return None

        clean_q = question.strip().lower()
        norm_q = re.sub(r"[^a-z0-9\s]", "", clean_q)

        # 1. Exact or substring match (normalized without punctuation)
        matched_item = None
        for item in qa_list:
            stored_q = item.get("question", "").strip().lower()
            norm_stored = re.sub(r"[^a-z0-9\s]", "", stored_q)
            if norm_q == norm_stored or norm_q in norm_stored or norm_stored in norm_q:
                matched_item = item
                break

        # 2. Key-phrase heuristic for common demo questions
        if not matched_item:
            # TCP 3-way handshake
            if "handshake" in clean_q or "tcp" in clean_q:
                matched_item = next((i for i in qa_list if "handshake" in i.get("question", "").lower()), None)
            # Deadlock
            elif "deadlock" in clean_q:
                matched_item = next((i for i in qa_list if "deadlock" in i.get("question", "").lower()), None)
            # OSI model
            elif "osi" in clean_q:
                matched_item = next((i for i in qa_list if "osi" in i.get("question", "").lower()), None)
            # Out of notes / quantum / art history / etc.
            elif any(k in clean_q for k in ["quantum", "art", "shor", "renaissance", "baroque", "photosynthesis"]):
                matched_item = next((i for i in qa_list if not i.get("grounded", True)), None)

        if not matched_item:
            # If in offline mode and no specific match, provide an honest offline notice
            if self.is_demo_mode():
                return ChatAnswerResponse(
                    id="msg-demo-unscripted",
                    subject_id=subject_id or "sub-demo-cn",
                    role="assistant",
                    text=(
                        "Offline Demo Mode: This question was not pre-scripted in your offline snapshot. "
                        "In live mode with an active internet connection, StudyGraph searches your vector notes."
                    ),
                    answered_from="general",
                    confidence=0.1,
                    citations=[],
                )
            return None

        citations = []
        for c in matched_item.get("citations", []):
            citations.append(
                CitationItem(
                    document_id=c.get("document_id", "doc-demo-notes"),
                    filename=c.get("document_filename", c.get("filename", "cn_mod2_transport_layer.pdf")),
                    page=c.get("page_number", c.get("page", 4)),
                    snippet=c.get("verbatim_snippet", c.get("snippet", "SYN sent by client, SYN-ACK returned by server.")),
                    similarity=c.get("similarity", 0.95),
                    source_kind=c.get("source_kind", "notes"),
                )
            )

        is_grounded = matched_item.get("grounded", True)
        return ChatAnswerResponse(
            id=f"msg-demo-{matched_item.get('id', 'q')}",
            subject_id=subject_id or "sub-demo-cn",
            role="assistant",
            text=matched_item.get("answer", ""),
            answered_from="notes" if is_grounded else "general",
            confidence=0.96 if is_grounded else 0.25,
            citations=citations,
        )

    def get_scripted_exam_overview(self, subject_id: Optional[str] = None) -> Optional[ExamOverviewResponse]:
        """
        Loads scripted exam data (important concepts, repeated questions, marks answers).
        """
        exam_file = DEMO_DATA_DIR / "scripted_exam_data.json"
        if not exam_file.exists():
            return None

        try:
            with open(exam_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[DemoService] Failed reading exam data: {e}")
            return None

        concepts = [
            ImportantConceptItem(
                topic_id=c.get("topic_id", "demo-t1"),
                keyword=c.get("topic_name", "Core Concept"),
                explanation=c.get("reason", "Important core concept for exams."),
                real_world_use="Applied in industry engineering architectures.",
                importance_score=c.get("importance_score", 0.9),
                degree=4,
                weighted_degree=12,
                modules_covered=2,
                source_count=3,
                cross_subject_links=1,
            )
            for c in data.get("important_concepts", [])
        ]

        questions = [
            RepeatedQuestionCluster(
                cluster_key=f"cluster-{idx}",
                canonical_question=q.get("canonical_question", "Explain concept"),
                repeat_count=q.get("frequency", 2),
                total_papers=len(q.get("years_asked", [2023, 2024])),
                typical_marks=q.get("marks_typical", 5),
                matched_topic_keyword=q.get("canonical_question", "")[:30],
                label="from your uploaded papers",
            )
            for idx, q in enumerate(data.get("repeated_questions", []))
        ]

        return ExamOverviewResponse(
            subject_id=subject_id or "sub-demo-cn",
            subject_name="Computer Networks (Demo)",
            important_concepts_label="by graph importance",
            important_concepts=concepts,
            repeated_questions_label="from your uploaded papers",
            has_uploaded_papers=True,
            total_papers=2,
            total_questions=len(questions),
            honest_notice=None,
            papers=[],
            repeated_questions=questions,
        )

    def is_demo_upload_file(self, filename: str) -> bool:
        """
        Checks if the uploaded file is the designated demo sample note.
        """
        name_lower = filename.lower()
        return "demo_upload" in name_lower or "november" in name_lower or "tls13" in name_lower

    def get_demo_upload_result(self) -> Dict[str, Any]:
        """
        Returns pre-computed incremental update result for live demo upload.
        """
        res_file = DEMO_DATA_DIR / "demo_upload_result.json"
        if res_file.exists():
            with open(res_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "status": "success",
            "message": "Incremental upload completed instantly in offline demo mode.",
            "topics_extracted": 1,
        }


demo_service = DemoService()
