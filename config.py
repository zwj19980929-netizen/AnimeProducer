import re
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class Settings(BaseSettings):
    # Core Settings
    PROJECT_NAME: str = "AnimeMatrix"
    DEBUG: bool = False
    API_VERSION: str = "v1"
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Authentication Settings
    AUTH_DISABLED: bool = True  # Set to False to enable authentication
    SECRET_KEY: str = ""  # JWT secret key (auto-generated if empty)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    API_KEY: str = ""  # Optional API key for service-to-service auth
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""  # Set to enable default admin user
    ALLOW_REGISTRATION: bool = True  # Allow new user registration

    # Database
    DATABASE_URL: str = "sqlite:///./animematrix.db"

    # LLM API Keys
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-pro"

    # Image Generation
    NANO_BANANA_API_KEY: str = ""
    NANO_BANANA_API_URL: str = "https://api.nanobanana.com/v1"

    # Video Generation
    VIDEO_GEN_API_KEY: str = ""
    VIDEO_GEN_API_URL: str = "https://api.videogen.com/v1"

    # TTS Settings
    TTS_BACKEND: str = "openai"  # openai, edge, google
    TTS_API_KEY: str = ""
    TTS_MODEL: str = "tts-1"
    TTS_DEFAULT_VOICE: str = "alloy"
    TTS_PROVIDER: str = "openai"  # openai, doubao, aliyun, minimax, zhipu
    
    # 豆包 Seed-TTS (火山引擎)
    DOUBAO_TTS_API_KEY: str = ""
    DOUBAO_TTS_ENDPOINT: str = "https://openspeech.bytedance.com"
    DOUBAO_TTS_APP_ID: str = ""
    
    # 阿里云 CosyVoice / Qwen3-TTS
    ALIYUN_TTS_API_KEY: str = ""
    ALIYUN_TTS_MODEL: str = "cosyvoice-v1"  # cosyvoice-v1, qwen3-tts
    
    # MiniMax Speech-02
    MINIMAX_API_KEY: str = ""
    MINIMAX_GROUP_ID: str = ""
    
    # 智谱 GLM-4-Voice
    ZHIPU_API_KEY: str = ""

    # VLM Settings
    VLM_BACKEND: str = "gemini"  # gemini, openai
    VLM_MODEL: str = "gemini-1.5-flash"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_EXPIRES: int = 3600

    # Paths (absolute paths computed from base)
    BASE_DIR: Path = Path(__file__).parent.resolve()

    @property
    def ASSETS_DIR(self) -> Path:
        return self.BASE_DIR / "assets"

    @property
    def CHARACTERS_DIR(self) -> Path:
        return self.BASE_DIR / "assets" / "characters"

    @property
    def RAW_MATERIALS_DIR(self) -> Path:
        return self.BASE_DIR / "assets" / "raw_materials"

    @property
    def OUTPUT_DIR(self) -> Path:
        return self.BASE_DIR / "assets" / "output"

    @property
    def PROJECTS_DIR(self) -> Path:
        return self.BASE_DIR / "assets" / "projects"

    # Generation Settings
    KEYFRAME_CANDIDATES: int = 4
    DEFAULT_SHOT_DURATION: float = 3.0
    VIDEO_FPS: int = 24
    MAX_PARALLEL_SHOTS: int = 4

    # Retry Settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # ========== Multi-Provider Settings ==========
    
    # Replicate
    REPLICATE_API_TOKEN: str = ""
    
    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_ENDPOINT: str = "https://api.deepseek.com/v1"
    
    # 豆包 (Doubao / 火山方舟)
    DOUBAO_API_KEY: str = ""
    DOUBAO_MODEL: str = "doubao-pro-4k"
    DOUBAO_ENDPOINT: str = "https://ark.cn-beijing.volces.com/api/v3"
    
    # 阿里云万相 (DashScope)
    DASHSCOPE_API_KEY: str = ""  # 灵积 API Key (从 dashscope.console.aliyun.com 获取)
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_REGION: str = "cn-shanghai"
    ALIYUN_WANX_MODEL: str = "wanx-v1"

    # 阿里云 OSS (用于图生视频上传图片)
    ALIYUN_OSS_BUCKET: str = ""
    ALIYUN_OSS_ENDPOINT: str = "oss-cn-shanghai.aliyuncs.com"  # 例如: oss-cn-shanghai.aliyuncs.com
    
    # 火山引擎
    VOLCENGINE_ACCESS_KEY: str = ""
    VOLCENGINE_SECRET_KEY: str = ""
    VOLCENGINE_REGION: str = "cn-north-1"
    
    # 默认 Provider 选择
    IMAGE_PROVIDER: str = "google"  # google, aliyun, replicate
    VIDEO_PROVIDER: str = "google"  # google, replicate, volcengine, aliyun
    LLM_PROVIDER: str = "google"    # google, deepseek, doubao, openai

    # 备用 Provider 列表
    BACKUP_IMAGE_PROVIDERS: str = "aliyun,replicate"
    BACKUP_VIDEO_PROVIDERS: str = "volcengine,replicate,aliyun"
    BACKUP_LLM_PROVIDERS: str = "deepseek,doubao"

    # ========== Lip-Sync Settings ==========
    LIPSYNC_ENABLED: bool = True  # 是否启用口型同步
    LIPSYNC_PROVIDER: str = "sadtalker"  # sadtalker, musetalk, liveportrait, wav2lip
    SADTALKER_API_URL: str = ""  # SadTalker API URL (如果不使用 Replicate)
    MUSETALK_API_URL: str = ""  # MuseTalk API URL
    LIVEPORTRAIT_API_URL: str = ""  # LivePortrait API URL
    WAV2LIP_API_URL: str = ""  # Wav2Lip API URL

    # ========== Frame Interpolation Settings ==========
    FRAME_INTERPOLATION_ENABLED: bool = True  # 是否启用帧插值
    FRAME_INTERPOLATION_METHOD: str = "rife"  # rife, film, simple
    RIFE_API_URL: str = ""  # RIFE API URL (如果不使用 Replicate)
    FILM_API_URL: str = ""  # FILM API URL

    # ========== Alignment Strategy Settings ==========
    DEFAULT_ALIGNMENT_STRATEGY: str = "smooth_slow_motion"  # slow_motion, loop, smooth_slow_motion, freeze_frame, extend

    # ========== LoRA Training Settings ==========
    LORA_TRAINING_ENABLED: bool = True  # 是否启用 LoRA 训练
    LORA_TRAINING_PROVIDER: str = "fal"  # fal, replicate
    FAL_KEY: str = ""  # Fal.ai API Key
    REPLICATE_USERNAME: str = ""  # Replicate 用户名（用于存储训练好的模型）
    LORA_DEFAULT_STEPS: int = 1000  # 默认训练步数
    LORA_DEFAULT_RANK: int = 16  # 默认 LoRA rank
    LORA_DATASET_SIZE: int = 20  # 默认数据集大小

    # ========== SFX (Sound Effects) Settings ==========
    SFX_ENABLED: bool = True  # 是否启用 AI 拟音
    SFX_PROVIDER: str = "audioldm"  # audioldm, elevenlabs
    ELEVENLABS_API_KEY: str = ""  # ElevenLabs API Key
    SFX_DEFAULT_VOLUME: float = 0.3  # 音效默认音量（相对于对白）

    # ========== AI Critic (Video Quality Check) Settings ==========
    CRITIC_ENABLED: bool = True  # 是否启用 AI 影评人质量检查
    CRITIC_PROVIDER: str = "gemini"  # gemini, openai (推荐 gemini，视频理解能力更强)
    CRITIC_MODEL: str = "gemini-1.5-pro"  # 评估模型
    CRITIC_MIN_SCORE: int = 8  # 最低通过分数 (0-10)
    CRITIC_MAX_RETRIES: int = 2  # 质量不达标时最大重试次数

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_project_dir(self, project_id: str) -> Path:
        """Get the directory for a specific project."""
        if not _SAFE_SEGMENT_RE.match(project_id):
            raise ValueError(f"Invalid project_id: {project_id!r}")
        result = self.PROJECTS_DIR / project_id
        result.resolve().relative_to(self.PROJECTS_DIR.resolve())
        return result

    def get_character_dir(self, project_id: str, character_id: str) -> Path:
        """Get the directory for a specific character."""
        if not _SAFE_SEGMENT_RE.match(character_id):
            raise ValueError(f"Invalid character_id: {character_id!r}")
        project_dir = self.get_project_dir(project_id)
        result = project_dir / "characters" / character_id
        result.resolve().relative_to(self.PROJECTS_DIR.resolve())
        return result

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
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()