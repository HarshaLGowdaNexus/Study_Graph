"""
Automated tests for Database Connection and Schema verification.
Relies on Decision D14: pytest.
"""

import pytest
from backend.app.core.config import settings
from backend.scripts.test_db_connection import check_database, EXPECTED_TABLES


def test_expected_tables_list_count():
    """Verify that our expected tables list strictly matches the 20 tables in docs/DATA_MODEL.md."""
    assert len(EXPECTED_TABLES) == 20
    assert "universities" in EXPECTED_TABLES
    assert "topics" in EXPECTED_TABLES
    assert "edges" in EXPECTED_TABLES
    assert "edge_evidence" in EXPECTED_TABLES
    assert "chunks" in EXPECTED_TABLES
    assert "chat_messages" in EXPECTED_TABLES


def test_settings_load_env():
    """Verify that settings module initializes and reads attributes."""
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "VECTOR_DIMENSION")
    assert settings.VECTOR_DIMENSION == 768


def test_database_connection():
    """
    Test live database connection and schema if DATABASE_URL is set.
    If DATABASE_URL is not set yet by the user, verify it reports failure gracefully.
    """
    if not settings.DATABASE_URL or "your_password_here" in settings.DATABASE_URL:
        result = check_database()
        assert result is False, "Should report False when DATABASE_URL is placeholder or empty"
    else:
        result = check_database()
        assert result is True, "Database connection and 20 tables should be verified"

