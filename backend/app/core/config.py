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
    # Supabase Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Supabase API Credentials
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Google Gemini AI Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # General App Settings
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Vector Configuration (Decision D10)
    VECTOR_DIMENSION: int = 768


settings = Settings()

