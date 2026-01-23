import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Core Settings
    PROJECT_NAME: str = "AnimeMatrix"
    DEBUG: bool = True
    API_VERSION: str = "v1"

    # Database
    DATABASE_URL: str = "sqlite:///./animematrix.db"

    # LLM API Keys
    GOOGLE_API_KEY: str = ""

    # Image Generation
    NANO_BANANA_API_KEY: str = ""
    NANO_BANANA_API_URL: str = "https://api.nanobanana.com/v1"

    # Video Generation
    VIDEO_GEN_API_KEY: str = ""
    VIDEO_GEN_API_URL: str = "https://api.videogen.com/v1"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Paths
    ASSETS_DIR: str = "./assets"
    CHARACTERS_DIR: str = "./assets/characters"
    RAW_MATERIALS_DIR: str = "./assets/raw_materials"
    OUTPUT_DIR: str = "./assets/output"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
