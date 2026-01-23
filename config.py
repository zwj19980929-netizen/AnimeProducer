from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core Settings
    PROJECT_NAME: str = "AnimeMatrix"
    DEBUG: bool = True
    API_VERSION: str = "v1"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite:///./animematrix.db"

    # LLM API Keys
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Image Generation
    NANO_BANANA_API_KEY: str = ""
    NANO_BANANA_API_URL: str = "https://api.nanobanana.com/v1"

    # Video Generation
    VIDEO_GEN_API_KEY: str = ""
    VIDEO_GEN_API_URL: str = "https://api.videogen.com/v1"

    # TTS Settings
    TTS_BACKEND: str = "openai"  # openai, edge, google
    TTS_API_KEY: str = ""
    TTS_DEFAULT_VOICE: str = "alloy"

    # VLM Settings
    VLM_BACKEND: str = "gemini"  # gemini, openai
    VLM_MODEL: str = "gemini-1.5-flash"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_EXPIRES: int = 3600

    # Paths (absolute paths computed from base)
    BASE_DIR: Path = Path(__file__).parent.resolve()
    ASSETS_DIR: str = "./assets"
    CHARACTERS_DIR: str = "./assets/characters"
    RAW_MATERIALS_DIR: str = "./assets/raw_materials"
    OUTPUT_DIR: str = "./assets/output"
    PROJECTS_DIR: str = "./assets/projects"

    # Generation Settings
    KEYFRAME_CANDIDATES: int = 4
    DEFAULT_SHOT_DURATION: float = 3.0
    VIDEO_FPS: int = 24
    MAX_PARALLEL_SHOTS: int = 4

    # Retry Settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_project_dir(self, project_id: str) -> Path:
        """Get the directory for a specific project."""
        return self.BASE_DIR / self.PROJECTS_DIR / project_id

    def get_character_dir(self, project_id: str, character_id: str) -> Path:
        """Get the directory for a specific character."""
        return self.get_project_dir(project_id) / "characters" / character_id

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""
        dirs = [
            self.ASSETS_DIR,
            self.CHARACTERS_DIR,
            self.RAW_MATERIALS_DIR,
            self.OUTPUT_DIR,
            self.PROJECTS_DIR,
        ]
        for d in dirs:
            (self.BASE_DIR / d).mkdir(parents=True, exist_ok=True)


settings = Settings()
