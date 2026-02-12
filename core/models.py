"""SQLModel table definitions for AnimeMatrix."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Column, Field, SQLModel, JSON


def generate_uuid() -> str:
    """生成 UUID4 字符串。"""
    return str(uuid4())


class ProjectStatus(str, Enum):
    """项目生命周期状态。"""
    DRAFT = "DRAFT"
    ASSETS_READY = "ASSETS_READY"
    STORYBOARD_READY = "STORYBOARD_READY"
    RENDERING = "RENDERING"
    COMPOSITED = "COMPOSITED"
    DONE = "DONE"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    """异步任务状态。"""
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"


class JobType(str, Enum):
    """异步任务类型。"""
    ASSET_GENERATION = "ASSET_GENERATION"
    STORYBOARD_GENERATION = "STORYBOARD_GENERATION"
    SHOT_RENDER = "SHOT_RENDER"
    VIDEO_COMPOSITION = "VIDEO_COMPOSITION"
    FULL_PIPELINE = "FULL_PIPELINE"
    EPISODE_PLAN = "EPISODE_PLAN"


class ShotRenderStatus(str, Enum):
    """镜头渲染状态。"""
    PENDING = "PENDING"
    GENERATING_IMAGE = "GENERATING_IMAGE"
    GENERATING_VIDEO = "GENERATING_VIDEO"
    GENERATING_AUDIO = "GENERATING_AUDIO"
    COMPOSITING = "COMPOSITING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ChapterStatus(str, Enum):
    """章节处理状态。"""
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    READY = "READY"
    FAILED = "FAILED"


class BookUploadStatus(str, Enum):
    """书籍上传状态。"""
    EMPTY = "EMPTY"          # 未上传
    PARTIAL = "PARTIAL"      # 部分上传
    COMPLETE = "COMPLETE"    # 全部上传


class EpisodeStatus(str, Enum):
    """集状态。"""
    PLANNED = "PLANNED"                    # 已规划
    STORYBOARD_READY = "STORYBOARD_READY"  # 分镜就绪
    RENDERING = "RENDERING"                # 渲染中
    DONE = "DONE"                          # 完成
    FAILED = "FAILED"                      # 失败


# ============================================================================
# Project and Job Tables
# ============================================================================


class Project(SQLModel, table=True):
    """项目元数据和状态。"""
    __tablename__ = "projects"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT)

    script_content: str | None = None
    style_preset: str | None = None
    genre: str | None = None

    output_video_path: str | None = None
    output_video_url: str | None = None  # OSS URL，用于前端播放/下载

    error_message: str | None = None
    project_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    """Celery 异步任务记录。"""
    __tablename__ = "jobs"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)

    job_type: JobType
    celery_task_id: str | None = Field(default=None, index=True)

    status: JobStatus = Field(default=JobStatus.PENDING)
    progress: float = Field(default=0.0)  # 0.0 to 1.0

    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error_message: str | None = None
    error_traceback: str | None = None
    providers_used: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ShotRender(SQLModel, table=True):
    """镜头渲染状态和产出物。"""
    __tablename__ = "shot_renders"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    shot_id: int = Field(foreign_key="shots.shot_id", index=True)
    job_id: str | None = Field(default=None, foreign_key="jobs.id")

    status: ShotRenderStatus = Field(default=ShotRenderStatus.PENDING)
    progress: float = Field(default=0.0)

    image_path: str | None = None
    video_path: str | None = None
    audio_path: str | None = None
    composited_path: str | None = None

    render_settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    error_message: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Existing Tables (Character and Shot)
# ============================================================================


class Character(SQLModel, table=True):
    """角色定义，包含视觉和语音参考。"""
    __tablename__ = "characters"

    character_id: str = Field(primary_key=True)
    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)

    name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # 角色别名列表
    appearance_prompt: str = Field(default="")  # 角色外貌描述，用于生成图片
    bio: str = Field(default="")  # 角色简介/背景故事
    prompt_base: str = Field(default="")  # 保留兼容，可用于额外的生成提示
    first_appearance_chapter: int = Field(default=0)  # 首次出场章节

    # 参考图（候选图中选择的）
    reference_image_path: str = Field(default="")
    reference_image_url: str | None = None  # OSS URL

    # 锚定图（确定形象后的底稿，所有后续生成都基于此）
    anchor_image_id: str | None = Field(default=None, foreign_key="character_images.id")
    anchor_image_path: str | None = None
    anchor_image_url: str | None = None

    voice_id: str | None = None

    character_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CharacterImageType(str, Enum):
    """角色图片类型。"""
    CANDIDATE = "CANDIDATE"      # 候选图（初次生成的参考图）
    ANCHOR = "ANCHOR"            # 锚定图（确定的角色形象底稿）
    VARIANT = "VARIANT"          # 变体图（基于锚定图生成的不同姿态/表情）
    TRAINING = "TRAINING"        # 训练图（标记用于 LoRA 训练）
    CUSTOM = "CUSTOM"            # 自定义生成图


class CharacterImage(SQLModel, table=True):
    """角色图片库，存储角色的所有生成图片。"""
    __tablename__ = "character_images"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    character_id: str = Field(foreign_key="characters.character_id", index=True)

    # 图片类型
    image_type: CharacterImageType = Field(default=CharacterImageType.CANDIDATE)

    # 图片路径
    image_path: str | None = None  # 本地路径（使用 OSS 时可为空）
    image_url: str | None = None  # OSS URL
    thumbnail_path: str | None = None  # 缩略图路径
    thumbnail_url: str | None = None  # 缩略图 OSS URL

    # 生成参数
    prompt: str = Field(default="")  # 生成时使用的完整 prompt
    pose: str | None = None  # 姿态描述
    expression: str | None = None  # 表情描述
    angle: str | None = None  # 角度描述
    style_preset: str | None = None  # 风格预设

    # 标记
    is_selected_for_training: bool = Field(default=False)  # 是否选中用于训练
    is_anchor: bool = Field(default=False)  # 是否为锚定图
    quality_score: float | None = None  # 质量评分（可选）

    # 元数据
    generation_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class CharacterState(SQLModel, table=True):
    """角色状态，用于跟踪角色在章节间的视觉演变。"""
    __tablename__ = "character_states"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    character_id: str = Field(foreign_key="characters.character_id", index=True)

    state_name: str  # e.g., "transformation", "costume_change", "dark_form"
    trigger_chapter: int = Field(default=0)  # Chapter where this state is triggered

    visual_changes: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    prompt_override: str | None = None  # New prompt for this state
    reference_image_path: str | None = None

    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Shot(SQLModel, table=True):
    """分镜定义。"""
    __tablename__ = "shots"

    shot_id: Optional[int] = Field(default=None, primary_key=True)

    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)
    episode_id: str | None = Field(default=None, foreign_key="episodes.id", index=True)
    chapter_id: str | None = Field(default=None, foreign_key="chapters.chapter_id", index=True)

    duration: float
    scene_description: str
    visual_prompt: str
    camera_movement: str

    characters_in_shot: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    character_states: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    dialogue: str | None = None
    action_type: str | None = None

    # 情感相关字段
    emotion: str | None = Field(
        default=None,
        description="镜头情感: happy, sad, angry, fearful, surprised, excited, tense, neutral"
    )
    emotion_intensity: float = Field(
        default=0.5,
        description="情感强度 0-1，0为最弱，1为最强"
    )
    emotion_context: str | None = Field(
        default=None,
        description="情感上下文描述，用于更精确的情感表达"
    )

    # 音效相关字段
    sfx_tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="音效标签列表，如 ['rain', 'thunder', 'footsteps']"
    )

    sequence_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Chapter and CharacterState Tables
# ============================================================================


class Chapter(SQLModel, table=True):
    """章节，支持多章节小说。"""
    __tablename__ = "chapters"

    chapter_id: str = Field(default_factory=generate_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)

    chapter_number: int = Field(index=True)
    title: str | None = None
    content: str

    # 统计信息
    word_count: int = Field(default=0)

    # AI 分析结果
    key_events: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    emotional_arc: str | None = None  # rising/falling/climax/resolution
    importance_score: float = Field(default=0.5)  # 0-1, 章节重要性
    suggested_episode: int | None = None  # AI 建议归属哪一集

    # 角色出场
    characters_appeared: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    status: ChapterStatus = Field(default=ChapterStatus.PENDING)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Book(SQLModel, table=True):
    """书籍元数据，一个项目对应一本书。"""
    __tablename__ = "books"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", unique=True, index=True)

    # 书籍信息
    original_title: str | None = None
    author: str | None = None
    genre: str | None = None

    # 统计信息
    total_chapters: int = Field(default=0)
    uploaded_chapters: int = Field(default=0)
    total_words: int = Field(default=0)

    # 上传状态
    upload_status: BookUploadStatus = Field(default=BookUploadStatus.EMPTY)

    # AI 分析结果
    ai_summary: str | None = None
    main_plot_points: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    suggested_episodes: int | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Episode(SQLModel, table=True):
    """集，一个项目可以有多集动漫。"""
    __tablename__ = "episodes"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)

    # 集信息
    episode_number: int = Field(index=True)
    title: str | None = None
    synopsis: str | None = None

    # 章节范围
    start_chapter: int
    end_chapter: int

    # 时长规划
    target_duration_minutes: float = Field(default=24.0)
    actual_duration_minutes: float | None = None

    # 状态
    status: EpisodeStatus = Field(default=EpisodeStatus.PLANNED)

    # 产出物
    output_video_path: str | None = None
    output_video_url: str | None = None

    # 元数据
    episode_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# LoRA Training Tables
# ============================================================================


class LoRATrainingStatus(str, Enum):
    """LoRA 训练状态。"""
    PENDING = "PENDING"              # 等待训练
    GENERATING_DATASET = "GENERATING_DATASET"  # 生成数据集中
    DATASET_READY = "DATASET_READY"  # 数据集就绪
    UPLOADING = "UPLOADING"          # 上传数据集中
    TRAINING = "TRAINING"            # 训练中
    READY = "READY"                  # 训练完成，可用
    FAILED = "FAILED"                # 训练失败


class CharacterLoRA(SQLModel, table=True):
    """角色 LoRA 模型，用于保持角色一致性。"""
    __tablename__ = "character_loras"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    character_id: str = Field(foreign_key="characters.character_id", index=True)

    # 训练配置
    base_model: str = Field(default="flux")  # flux, sdxl, sd15
    trigger_word: str  # 触发词，如 "ohwx_character_name"
    training_provider: str = Field(default="fal")  # fal, replicate

    # 训练状态
    status: LoRATrainingStatus = Field(default=LoRATrainingStatus.PENDING)
    progress: float = Field(default=0.0)  # 0.0 - 1.0

    # 数据集信息
    dataset_size: int = Field(default=0)  # 训练图片数量
    dataset_url: str | None = None  # 数据集 ZIP 的 OSS URL

    # 训练结果
    lora_url: str | None = None  # 训练完成的 LoRA 权重 URL
    lora_local_path: str | None = None  # 本地缓存路径
    training_job_id: str | None = None  # 云端训练任务 ID

    # 训练参数
    training_steps: int = Field(default=1000)
    learning_rate: float = Field(default=1e-4)
    lora_rank: int = Field(default=16)

    # 元数据
    training_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_message: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)