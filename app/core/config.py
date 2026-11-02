# Copyright (c) 2026 Lekkalu
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    # Optional so the app boots without them; providers fail loudly when called without a key.
    meta_api_key: str | None = None
    meta_api_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    meta_stt_model: str = "muse-voice-transcribe-1.0"
    sarvam_api_key: str | None = None

    # Off by default: on the Phase 0 clips keywords made customer names worse (spikes/RESULTS.md).
    stt_keywords: bool = False
    audio_dir: Path = Path("var/audio")  # git-ignored

    model_timeout_s: float = 30
    business_tz: str = "Asia/Kolkata"


@lru_cache
def get_settings() -> Settings:
    return Settings()
