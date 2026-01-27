"""SQLModel table definitions for AnimeMatrix."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Column, Field, SQLModel, JSON


def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid4())


class ProjectStatus(str, Enum):
    """Project lifecycle states."""
    DRAFT = "DRAFT"
    ASSETS_READY = "ASSETS_READY"
    STORYBOARD_READY = "STORYBOARD_READY"
    RENDERING = "RENDERING"
    COMPOSITED = "COMPOSITED"
    DONE = "DONE"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    """Async job states."""
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"


class JobType(str, Enum):
    """Types of async jobs."""
    ASSET_GENERATION = "ASSET_GENERATION"
    STORYBOARD_GENERATION = "STORYBOARD_GENERATION"
    SHOT_RENDER = "SHOT_RENDER"
    VIDEO_COMPOSITION = "VIDEO_COMPOSITION"
    FULL_PIPELINE = "FULL_PIPELINE"


class ShotRenderStatus(str, Enum):
    """Individual shot render states."""
    PENDING = "PENDING"
    GENERATING_IMAGE = "GENERATING_IMAGE"
    GENERATING_VIDEO = "GENERATING_VIDEO"
    GENERATING_AUDIO = "GENERATING_AUDIO"
    COMPOSITING = "COMPOSITING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


# ============================================================================
# Project and Job Tables
# ============================================================================


class Project(SQLModel, table=True):
    """Project metadata and state."""
    __tablename__ = "projects"

    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT)

    script_content: str | None = None
    style_preset: str | None = None

    output_video_path: str | None = None

    error_message: str | None = None
    project_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    """Async task record for Celery jobs."""
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

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ShotRender(SQLModel, table=True):
    """Render state and artifacts for each shot."""
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
    """Character definition with visual and voice references."""
    __tablename__ = "characters"

    character_id: str = Field(primary_key=True)
    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)

    name: str
    prompt_base: str
    reference_image_path: str
    voice_id: str | None = None

    character_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Shot(SQLModel, table=True):
    """Shot definition from storyboard."""
    __tablename__ = "shots"

    # [核心修复] 改为 Optional 并设置 default=None，允许数据库自动生成自增 ID
    shot_id: Optional[int] = Field(default=None, primary_key=True)

    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)

    duration: float
    scene_description: str
    visual_prompt: str
    camera_movement: str

    characters_in_shot: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    dialogue: str | None = None
    action_type: str | None = None

    sequence_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)