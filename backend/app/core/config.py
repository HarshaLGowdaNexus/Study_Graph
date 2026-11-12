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
    GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-flash-lite-latest")

    # Topic Extraction Settings (Task T05, Decision D09)
    TOPIC_EXTRACTION_MODEL: str = os.getenv("TOPIC_EXTRACTION_MODEL", "gemini-flash-lite-latest")
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
    DEDUPE_CONFIRMATION_MODEL: str = os.getenv("DEDUPE_CONFIRMATION_MODEL", "gemini-flash-lite-latest")
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
    LINK_JUDGE_MODEL: str = os.getenv("LINK_JUDGE_MODEL", "gemini-flash-lite-latest")
    LINK_JUDGE_TEMPERATURE: float = float(os.getenv("LINK_JUDGE_TEMPERATURE", "0.1"))
    # Cross-subject links need strength >= 3 to be visible by default (Risk R19, Rule 13.8)
    CROSS_SUBJECT_MIN_VISIBLE_STRENGTH: int = int(os.getenv("CROSS_SUBJECT_MIN_VISIBLE_STRENGTH", "3"))
    LINK_JUDGE_MAX_CANDIDATES_PER_BATCH: int = int(os.getenv("LINK_JUDGE_MAX_CANDIDATES_PER_BATCH", "10"))

    # Chatbot RAG Settings (Task T13, Decisions D09, D10, RULEBOOK 13.4, Feature F14, Risk R10)
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "gemini-flash-lite-latest")
    CHAT_TEMPERATURE: float = float(os.getenv("CHAT_TEMPERATURE", "0.2"))
    # Minimum retrieval cosine similarity (0.0 to 1.0) below which question is flagged "Not found in your notes"
    CHAT_CONFIDENCE_THRESHOLD: float = float(os.getenv("CHAT_CONFIDENCE_THRESHOLD", "0.60"))
    # Top-K chunks retrieved from student notes per query
    CHAT_TOP_K: int = int(os.getenv("CHAT_TOP_K", "5"))

    # Graph Visualization Settings (Task T14, Decisions D03, D11, Feature F11, Risks R09, R14)
    # Default node visibility cap to prevent canvas rendering lag on weak devices (R14)
    GRAPH_MAX_VISIBLE_NODES: int = int(os.getenv("GRAPH_MAX_VISIBLE_NODES", "150"))
    # Minimum strength (1-5) required for edges to be visible when 'hide weak edges' is active (R09, Rule 13.8)
    GRAPH_WEAK_LINK_THRESHOLD: int = int(os.getenv("GRAPH_WEAK_LINK_THRESHOLD", "3"))

    # Topic Search, Focused Subgraph & 2D Performance Fallback Settings (Task T16, Features F13, F15, Risks R09, R14, G08)
    # FPS below this limit triggers automatic fallback from 3D WebGL to 2D Canvas
    GRAPH_FPS_FALLBACK_THRESHOLD: int = int(os.getenv("GRAPH_FPS_FALLBACK_THRESHOLD", "25"))
    # Consecutive 500ms measurement windows below threshold required before switching (4 windows = 2.0s)
    GRAPH_FPS_LOW_STREAK_COUNT: int = int(os.getenv("GRAPH_FPS_LOW_STREAK_COUNT", "4"))
    # Default and allowed hop radius when focusing on a searched topic (2-3 hops per Feature F13)
    GRAPH_SEARCH_DEFAULT_HOPS: int = int(os.getenv("GRAPH_SEARCH_DEFAULT_HOPS", "2"))
    GRAPH_SEARCH_MIN_HOPS: int = int(os.getenv("GRAPH_SEARCH_MIN_HOPS", "1"))
    GRAPH_SEARCH_MAX_HOPS: int = int(os.getenv("GRAPH_SEARCH_MAX_HOPS", "3"))
    # Maximum autocomplete suggestions returned by topic search
    GRAPH_SEARCH_MAX_SUGGESTIONS: int = int(os.getenv("GRAPH_SEARCH_MAX_SUGGESTIONS", "10"))

    # Exam Mode Settings (Task T17, Decisions D09, D10, D11, Features F18-F20, Risks R05, R10)
    EXAM_QUESTION_MODEL: str = os.getenv("EXAM_QUESTION_MODEL", "gemini-flash-lite-latest")
    EXAM_CLUSTER_CONFIRM_MODEL: str = os.getenv("EXAM_CLUSTER_CONFIRM_MODEL", "gemini-flash-lite-latest")
    EXAM_QUESTION_TEMPERATURE: float = float(os.getenv("EXAM_QUESTION_TEMPERATURE", "0.1"))
    # Cosine similarity threshold for candidate same-question pairs across uploaded papers
    EXAM_QUESTION_SIMILARITY_THRESHOLD: float = float(os.getenv("EXAM_QUESTION_SIMILARITY_THRESHOLD", "0.75"))
    # Default max important concepts returned in Exam Mode
    EXAM_IMPORTANT_CONCEPTS_LIMIT: int = int(os.getenv("EXAM_IMPORTANT_CONCEPTS_LIMIT", "15"))

    # Syllabus Ghost Nodes & Source Preference Settings (Task T18, Decisions D09, D10, Features F16, F17)
    SYLLABUS_PARSE_MODEL: str = os.getenv("SYLLABUS_PARSE_MODEL", "gemini-flash-lite-latest")
    SYLLABUS_MATCH_CONFIRM_MODEL: str = os.getenv("SYLLABUS_MATCH_CONFIRM_MODEL", "gemini-flash-lite-latest")
    SYLLABUS_PARSE_TEMPERATURE: float = float(os.getenv("SYLLABUS_PARSE_TEMPERATURE", "0.1"))
    # Minimum cosine similarity for a syllabus topic to be considered a match candidate for a note topic
    SYLLABUS_MATCH_THRESHOLD: float = float(os.getenv("SYLLABUS_MATCH_THRESHOLD", "0.62"))
    # Similarity at or above which exact/near-identical normalized topics confirm without extra LLM cost
    SYLLABUS_AUTO_EXACT_THRESHOLD: float = float(os.getenv("SYLLABUS_AUTO_EXACT_THRESHOLD", "0.92"))
    # Tie-breaker boost applied to chunks matching the subject's preferred source_kind ('notes' or 'textbook')
    SOURCE_PREFERENCE_BOOST: float = float(os.getenv("SOURCE_PREFERENCE_BOOST", "0.08"))

    # Offline Demo Mode Settings (Task T21, Risk R17, Quality Gate G10)
    # When enabled, serves pre-cached local snapshots without external network/API dependencies.
    # Strictly for presentation safety during live demos; defaults to False for normal study use.
    OFFLINE_DEMO_MODE: bool = os.getenv("OFFLINE_DEMO_MODE", "false").lower() in ("true", "1", "yes")
    DEMO_DATA_DIR: Path = ROOT_DIR / "demo_data"



settings = Settings()
