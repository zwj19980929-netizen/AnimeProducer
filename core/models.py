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
    prompt_base: str
    reference_image_path: str
    voice_id: str | None = None

    character_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

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
    chapter_id: str | None = Field(default=None, foreign_key="chapters.chapter_id", index=True)

    duration: float
    scene_description: str
    visual_prompt: str
    camera_movement: str

    characters_in_shot: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    character_states: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    dialogue: str | None = None
    action_type: str | None = None

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

    status: ChapterStatus = Field(default=ChapterStatus.PENDING)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)