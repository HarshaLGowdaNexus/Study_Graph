"""
Central Configuration for StudyGraph Backend.
Rule 5: Keep configuration values in one config file, not scattered in code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Path to the root directory where .env lives
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"

# Load variables from .env file if it exists
load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    ROOT_DIR: Path = ROOT_DIR

    # Supabase Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Supabase API Credentials
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

    # Storage Settings (Decision D06)
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "study-documents")

    # Upload Constraints (Task T03)
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf", ".ppt", ".pptx", ".png", ".jpg", ".jpeg")

    # Google Gemini AI Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # General App Settings
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Vector Configuration (Decision D10)
    VECTOR_DIMENSION: int = 768

    # Ingestion & Extraction Settings (Task T04, Decisions D08, D15)
    EXTRACTION_MIN_TEXT_CHARS: int = int(os.getenv("EXTRACTION_MIN_TEXT_CHARS", "50"))
    # 0 means process all pages; set a positive integer to cap test runs
    EXTRACTION_MAX_TEST_PAGES: int = int(os.getenv("EXTRACTION_MAX_TEST_PAGES", "0"))
    GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-3.5-flash")

    # Topic Extraction Settings (Task T05, Decision D09)
    TOPIC_EXTRACTION_MODEL: str = os.getenv("TOPIC_EXTRACTION_MODEL", "gemini-3.5-flash")
    TOPIC_EXTRACTION_TEMPERATURE: float = float(os.getenv("TOPIC_EXTRACTION_TEMPERATURE", "0.1"))
    MAX_TOPICS_PER_PAGE: int = int(os.getenv("MAX_TOPICS_PER_PAGE", "4"))

    # Embedding Settings (Task T07, Decision D10)
    # Default model is gemini-embedding-001 with output_dimensionality=768 (fits vector(768))
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # Duplicate Topic Detection Settings (Task T07, Decisions D09, D10)
    # Cosine similarity threshold (0.0 to 1.0) above which same-subject topics are flagged as candidates
    # Default 0.85: higher threshold prevents false merges; lower threshold catches looser phrasing
    DEDUPE_SIMILARITY_THRESHOLD: float = float(os.getenv("DEDUPE_SIMILARITY_THRESHOLD", "0.85"))
    DEDUPE_CONFIRMATION_MODEL: str = os.getenv("DEDUPE_CONFIRMATION_MODEL", "gemini-3.5-flash-lite")
    DEDUPE_CONFIRMATION_TEMPERATURE: float = float(os.getenv("DEDUPE_CONFIRMATION_TEMPERATURE", "0.0"))

    # Link Candidate Finder Settings (Task T08, Decisions D05, D10)
    # k: maximum raw nearest neighbors queried per scope via pgvector HNSW index
    CANDIDATE_K_NEIGHBORS: int = int(os.getenv("CANDIDATE_K_NEIGHBORS", "10"))
    # Minimum cosine similarity for same-subject topics (empirically calibrated: 0.55 catches module-related topics)
    CANDIDATE_SAME_SUBJECT_THRESHOLD: float = float(os.getenv("CANDIDATE_SAME_SUBJECT_THRESHOLD", "0.55"))
    # Stricter minimum cosine similarity for cross-subject topics (empirically calibrated: 0.68 prevents forced links per R19)
    CANDIDATE_CROSS_SUBJECT_THRESHOLD: float = float(os.getenv("CANDIDATE_CROSS_SUBJECT_THRESHOLD", "0.68"))
    # Hard cap on candidates kept per topic to bound downstream LLM judge costs (R07)
    CANDIDATE_MAX_PER_TOPIC: int = int(os.getenv("CANDIDATE_MAX_PER_TOPIC", "8"))

    # LLM Link Judge Settings (Task T09, Decisions D05, D09, RULEBOOK 13.1, 13.8)
    LINK_JUDGE_MODEL: str = os.getenv("LINK_JUDGE_MODEL", "gemini-3.5-flash-lite")
    LINK_JUDGE_TEMPERATURE: float = float(os.getenv("LINK_JUDGE_TEMPERATURE", "0.1"))
    # Cross-subject links need strength >= 3 to be visible by default (Risk R19, Rule 13.8)
    CROSS_SUBJECT_MIN_VISIBLE_STRENGTH: int = int(os.getenv("CROSS_SUBJECT_MIN_VISIBLE_STRENGTH", "3"))
    LINK_JUDGE_MAX_CANDIDATES_PER_BATCH: int = int(os.getenv("LINK_JUDGE_MAX_CANDIDATES_PER_BATCH", "10"))


settings = Settings()
