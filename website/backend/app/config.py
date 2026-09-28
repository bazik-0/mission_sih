"""
Configuration settings for the application.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve base directory at module level so it can be used
# both as a class default and inside the nested Config class.
BASE_DIR = Path(__file__).parent.parent.parent.parent

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/mission_sih"

    # NASA FIRMS API
    NASA_FIRMS_MAP_KEY: str
    FIRMS_SOURCE: str = "VIIRS_NOAA20_SP"
    FIRMS_AREA: str = "68,6,97.5,37.5"  # India bbox: west,south,east,north
    FIRMS_MAX_DATE: str = "2026-06-30"  # SP data only available through this date

    # Hugging Face
    HUGGING_FACE_API: str = ""

    # Ingestion settings
    INGEST_INTERVAL_MINUTES: int = 1440  # 24 hours
    INITIAL_BACKFILL_DAYS: int = 30

    # Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    MODEL_DIR: Path = BASE_DIR / "model" / "hf_model"
    CACHE_DIR: Path = BASE_DIR / "website" / "backend" / ".cache"

    class Config:
        env_file = BASE_DIR / ".env"  # BASE_DIR is the module-level variable
        case_sensitive = True

settings = Settings()

# Ensure cache directory exists
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
