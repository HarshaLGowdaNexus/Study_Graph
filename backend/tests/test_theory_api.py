"""
Automated Integration Tests for Theory View API (Task T12).
Relies on:
  - Feature F10: Theory view per subject with cross-module link chips.
  - Risk R04: UX grounded in bite-sized cards and navigable links.
  - RULEBOOK Section 13 Rule 3: Topic cards are short (max 4 lines + real-world use).
  - RULEBOOK Section 13 Rule 8: Weak links hidden by default.
  - RULEBOOK Section 13 Rule 9: Visible 'unreviewed' markings.
  - RULEBOOK Rule 11: Multi-user privacy isolation.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.app.api.deps import CurrentUser
from backend.app.api.routes.theory import get_subject_theory
from backend.app.schemas.theory import SubjectTheoryResponse

USER_ALEX = "11111111-1111-4111-8111-111111111111"
USER_BOB = "22222222-2222-4222-8222-222222222222"
SUBJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

alex_user = CurrentUser(
    id=USER_ALEX,
    email="alex@university.edu",
    name="Alex Chen",
)


def test_theory_subject_not_found():
    """Accessing non-existent subject raises 404 HTTPException."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # Subject not found

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.api.routes.theory.get_db_cursor", mock_get_db):
        with pytest.raises(HTTPException) as exc_info:
            get_subject_theory(SUBJECT_ID, current_user=alex_user)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


def test_theory_privacy_isolation():
    """Verifies that subject query enforces user_id check (Rule 11)."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.api.routes.theory.get_db_cursor", mock_get_db):
        with pytest.raises(HTTPException):
            get_subject_theory(SUBJECT_ID, current_user=alex_user)

        # Verify SQL query checked user_id = USER_ALEX
        mock_cursor.execute.assert_called()
        args = mock_cursor.execute.call_args_list[0]
        sql_query = args[0][0]
        sql_params = args[0][1]
        assert "user_id = %s" in sql_query
        assert sql_params == (SUBJECT_ID, USER_ALEX)


def test_theory_empty_subject():
    """Subject with no topics returns empty modules list."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": SUBJECT_ID, "name": "Computer Networks"}
    mock_cursor.fetchall.return_value = []  # No topics

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.api.routes.theory.get_db_cursor", mock_get_db):
        res: SubjectTheoryResponse = get_subject_theory(SUBJECT_ID, current_user=alex_user)
        assert res.subject_id == SUBJECT_ID
        assert res.subject_name == "Computer Networks"
        assert res.total_topics == 0
        assert res.modules == []


def test_theory_modules_grouping_and_cross_module_chips():
    """
    Verifies that:
    1. Topics are grouped by module (Module 1, Module 5).
    2. Cross-module links have is_cross_module=True.
    3. Weak links (strength < 3) have is_weak=True.
    4. Unreviewed topics have reviewed=False and are counted in unreviewed_count.
    """
    mock_topics = [
        {
            "id": "11111111-0000-0000-0000-000000000001",
            "subject_id": SUBJECT_ID,
            "keyword": "OSI 7-Layer Model",
            "explanation": "Standard abstraction for network communications.\nDivided into 7 distinct layers.\nPhysical to Application layer.\nPrevents vendor lock-in.",
            "real_world_use": "Network protocol stack design and troubleshooting.",
            "module_no": 1,
            "reviewed": True,
            "cluster_label": "Architecture",
        },
        {
            "id": "11111111-0000-0000-0000-000000000002",
            "subject_id": SUBJECT_ID,
            "keyword": "Packet Switching",
            "explanation": "Data broken into packets routed independently.\nMaximizes network link utilization.",
            "real_world_use": "Core foundation of Internet IP packet forwarding.",
            "module_no": 1,
            "reviewed": False,  # Unreviewed topic
            "cluster_label": "Routing",
        },
        {
            "id": "11111111-0000-0000-0000-000000000005",
            "subject_id": SUBJECT_ID,
            "keyword": "TCP Congestion Control",
            "explanation": "AIMD mechanism to prevent network buffer overflows.\nAdapts sending rate to bandwidth.",
            "real_world_use": "Prevents global Internet collapse under high traffic.",
            "module_no": 5,
            "reviewed": True,
            "cluster_label": "Transport",
        },
    ]

    mock_edges = [
        # Link 1: Module 1 -> Module 5 (Cross-module, strong link)
        {
            "id": "eeeeeeee-0000-0000-0000-000000000001",
            "topic_a": "11111111-0000-0000-0000-000000000001",
            "topic_b": "11111111-0000-0000-0000-000000000005",
            "type": "prerequisite_of",
            "reason": "Transport layer protocols build directly upon layered architecture.",
            "industry_example": "TCP socket implementation in Linux kernel.",
            "strength": 5,
            "scope": "same_subject",
            "a_id": "11111111-0000-0000-0000-000000000001",
            "a_keyword": "OSI 7-Layer Model",
            "a_module_no": 1,
            "a_subject_name": "Computer Networks",
            "b_id": "11111111-0000-0000-0000-000000000005",
            "b_keyword": "TCP Congestion Control",
            "b_module_no": 5,
            "b_subject_name": "Computer Networks",
        },
        # Link 2: Module 1 -> Module 1 (Same module, weak link strength=2)
        {
            "id": "eeeeeeee-0000-0000-0000-000000000002",
            "topic_a": "11111111-0000-0000-0000-000000000001",
            "topic_b": "11111111-0000-0000-0000-000000000002",
            "type": "part_of",
            "reason": "Packet switching operates within the lower layers of network models.",
            "industry_example": "Ethernet frame switching.",
            "strength": 2,  # Weak link!
            "scope": "same_subject",
            "a_id": "11111111-0000-0000-0000-000000000001",
            "a_keyword": "OSI 7-Layer Model",
            "a_module_no": 1,
            "a_subject_name": "Computer Networks",
            "b_id": "11111111-0000-0000-0000-000000000002",
            "b_keyword": "Packet Switching",
            "b_module_no": 1,
            "b_subject_name": "Computer Networks",
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {"id": SUBJECT_ID, "name": "Computer Networks"}
    mock_cursor.fetchall.side_effect = [mock_topics, mock_edges]

    @contextmanager
    def mock_get_db(*args, **kwargs):
        yield mock_cursor

    with patch("backend.app.api.routes.theory.get_db_cursor", mock_get_db):
        res: SubjectTheoryResponse = get_subject_theory(SUBJECT_ID, current_user=alex_user)

        assert res.total_topics == 3
        assert res.total_links == 2
        assert res.unreviewed_count == 1  # 1 unreviewed topic

        modules = res.modules
        assert len(modules) == 2  # Module 1 and Module 5

        # Check Module 1
        mod1 = modules[0]
        assert mod1.module_no == 1
        assert mod1.topic_count == 2

        # Check OSI card
        osi_card = next(t for t in mod1.topics if t.keyword == "OSI 7-Layer Model")
        assert osi_card.reviewed is True
        assert len(osi_card.links) == 2

        # Link to Module 5 (cross-module check)
        cross_mod_chip = next(l for l in osi_card.links if l.target_keyword == "TCP Congestion Control")
        assert cross_mod_chip.is_cross_module is True
        assert cross_mod_chip.target_module_no == 5
        assert cross_mod_chip.is_weak is False
        assert cross_mod_chip.strength == 5
        assert cross_mod_chip.type == "prerequisite_of"

        # Link to Packet Switching (weak link check)
        weak_chip = next(l for l in osi_card.links if l.target_keyword == "Packet Switching")
        assert weak_chip.is_cross_module is False
        assert weak_chip.is_weak is True
        assert weak_chip.strength == 2

        # Check Packet Switching card (unreviewed check)
        packet_card = next(t for t in mod1.topics if t.keyword == "Packet Switching")
        assert packet_card.reviewed is False

        # Check Module 5 (incoming link to OSI)
        mod5 = modules[1]
        assert mod5.module_no == 5
        tcp_card = mod5.topics[0]
        assert tcp_card.keyword == "TCP Congestion Control"
        assert len(tcp_card.links) == 1
        assert tcp_card.links[0].target_keyword == "OSI 7-Layer Model"
        assert tcp_card.links[0].direction == "incoming"
        assert tcp_card.links[0].is_cross_module is True
