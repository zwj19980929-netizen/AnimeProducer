"""Pydantic request/response schemas for API endpoints.

These schemas are separate from SQLModel tables to allow
independent evolution of API contracts and database schema.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.models import (
    BookUploadStatus,
    ChapterStatus,
    EpisodeStatus,
    JobStatus,
    JobType,
    ProjectStatus,
    ShotRenderStatus,
)


# ============================================================================
# Project Schemas
# ============================================================================


class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    script_content: str | None = None
    style_preset: str | None = None
    project_metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    script_content: str | None = None
    style_preset: str | None = None
    status: ProjectStatus | None = None
    project_metadata: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    """Response schema for project data."""
    id: str
    name: str
    description: str | None
    status: ProjectStatus
    script_content: str | None
    style_preset: str | None
    output_video_path: str | None
    output_video_url: str | None  # OSS URL，用于前端播放/下载
    error_message: str | None
    project_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Response schema for listing projects."""
    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int


class ProjectStatusUpdate(BaseModel):
    """Request schema for updating project status."""
    status: ProjectStatus
    error_message: str | None = None


# ============================================================================
# Character/Asset Schemas
# ============================================================================


class CharacterCreate(BaseModel):
    """Request schema for creating a character."""
    character_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    prompt_base: str
    reference_image_path: str
    voice_id: str | None = None
    character_metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterUpdate(BaseModel):
    """Request schema for updating a character."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_base: str | None = None
    reference_image_path: str | None = None
    voice_id: str | None = None
    character_metadata: dict[str, Any] | None = None


class VoiceConfig(BaseModel):
    """角色语音配置"""
    voice_id: str = Field(..., description="语音 ID，如 'alloy', 'nova', 'longxiaochun' 等")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速，0.5-2.0")
    pitch: float = Field(default=0.0, ge=-12.0, le=12.0, description="音调，-12 到 12（仅部分提供商支持）")
    emotion: str | None = Field(default=None, description="情感，如 'neutral', 'happy', 'sad', 'angry'")


class VoicePreviewRequest(BaseModel):
    """语音预览请求"""
    text: str = Field(
        default="你好，我是这个角色的声音。",
        description="预览文本"
    )
    voice_id: str = Field(..., description="语音 ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="语速")


class VoicePreviewResponse(BaseModel):
    """语音预览响应"""
    audio_url: str = Field(..., description="音频 URL（OSS）")
    duration: float = Field(..., description="音频时长（秒）")
    voice_id: str
    text: str


class AvailableVoicesResponse(BaseModel):
    """可用语音列表响应"""
    provider: str
    voices: list[dict[str, Any]]


class GenerateReferenceRequest(BaseModel):
    """Request schema for generating character reference image."""
    custom_prompt: str | None = Field(
        default=None,
        description="自定义提示词，会追加到角色的 prompt_base 后面"
    )
    style_preset: str | None = Field(
        default=None,
        description="风格预设，如 'anime style', 'realistic', 'watercolor' 等"
    )
    num_candidates: int = Field(
        default=4,
        ge=1,
        le=8,
        description="生成候选图片数量"
    )


class CharacterResponse(BaseModel):
    """Response schema for character data."""
    character_id: str
    project_id: str | None
    name: str
    prompt_base: str
    reference_image_path: str
    reference_image_url: str | None = None
    voice_id: str | None
    character_metadata: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class CharacterListResponse(BaseModel):
    """Response schema for listing characters."""
    items: list[CharacterResponse]
    total: int


# ============================================================================
# Shot Schemas
# ============================================================================


class ShotCreate(BaseModel):
    """Request schema for creating a shot."""
    shot_id: int
    duration: float = Field(..., gt=0)
    scene_description: str
    visual_prompt: str
    camera_movement: str
    characters_in_shot: list[str] = Field(default_factory=list)
    dialogue: str | None = None
    action_type: str | None = None
    sequence_order: int = 0


class ShotResponse(BaseModel):
    """Response schema for shot data."""
    shot_id: int
    project_id: str | None
    duration: float
    scene_description: str
    visual_prompt: str
    camera_movement: str
    characters_in_shot: list[str]
    dialogue: str | None
    action_type: str | None
    sequence_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShotListResponse(BaseModel):
    """Response schema for listing shots."""
    items: list[ShotResponse]
    total: int


# ============================================================================
# Job Schemas
# ============================================================================


class JobCreate(BaseModel):
    """Request schema for creating a job."""
    project_id: str
    job_type: JobType


class JobResponse(BaseModel):
    """Response schema for job data."""
    id: str
    project_id: str
    job_type: JobType
    celery_task_id: str | None
    status: JobStatus
    progress: float
    result: dict[str, Any] | None
    error_message: str | None
    error_traceback: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Response schema for listing jobs."""
    items: list[JobResponse]
    total: int


class JobProgressUpdate(BaseModel):
    """Request schema for updating job progress."""
    progress: float = Field(..., ge=0.0, le=1.0)
    status: JobStatus | None = None


class JobStatusUpdate(BaseModel):
    """Request schema for updating job status."""
    status: JobStatus
    error_message: str | None = None
    error_traceback: str | None = None
    result: dict[str, Any] | None = None


# ============================================================================
# Shot Render Schemas
# ============================================================================


class ShotRenderResponse(BaseModel):
    """Response schema for shot render data."""
    id: str
    project_id: str
    shot_id: int
    job_id: str | None
    status: ShotRenderStatus
    progress: float
    image_path: str | None
    video_path: str | None
    audio_path: str | None
    composited_path: str | None
    render_settings: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShotRenderListResponse(BaseModel):
    """Response schema for listing shot renders."""
    items: list[ShotRenderResponse]
    total: int


# ============================================================================
# Pipeline Schemas
# ============================================================================


class PipelineStartRequest(BaseModel):
    """Request schema for starting the full pipeline."""
    project_id: str | None = None
    skip_asset_generation: bool = False
    parallel_renders: int = Field(default=3, ge=1, le=10)


class PipelineStartResponse(BaseModel):
    """Response schema for pipeline start."""
    job_id: str
    project_id: str
    message: str


# ============================================================================
# Error Schemas
# ============================================================================


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationErrorResponse(BaseModel):
    """Validation error response schema."""
    error: str = "validation_error"
    message: str = "Request validation failed"
    details: list[dict[str, Any]]


# ============================================================================
# Chapter Schemas
# ============================================================================


class ChapterCreate(BaseModel):
    """Request schema for creating a chapter."""
    chapter_number: int = Field(..., ge=1)
    title: str | None = None
    content: str = Field(..., min_length=1)


class ChapterBatchCreate(BaseModel):
    """Request schema for batch creating chapters."""
    chapters: list[ChapterCreate] = Field(..., min_length=1)


class ChapterUpdate(BaseModel):
    """Request schema for updating a chapter."""
    title: str | None = None
    content: str | None = None


class ChapterResponse(BaseModel):
    """Response schema for chapter data."""
    chapter_id: str
    project_id: str
    chapter_number: int
    title: str | None = None
    content: str
    word_count: int = 0
    key_events: list[str] = []
    emotional_arc: str | None = None
    importance_score: float = 0.5
    suggested_episode: int | None = None
    characters_appeared: list[str] = []
    status: ChapterStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChapterListResponse(BaseModel):
    """Response schema for listing chapters."""
    items: list[ChapterResponse]
    total: int
    page: int
    page_size: int


class ChapterAnalysisResult(BaseModel):
    """Response schema for chapter analysis."""
    chapter_id: str
    chapter_number: int
    key_events: list[str]
    emotional_arc: str
    importance_score: float
    characters_appeared: list[str]
    suggested_episode: int | None


class ChapterBatchAnalysisResponse(BaseModel):
    """Response schema for batch chapter analysis."""
    analyzed_count: int
    results: list[ChapterAnalysisResult]


# ============================================================================
# Book Schemas
# ============================================================================


class BookCreate(BaseModel):
    """Request schema for creating book metadata."""
    original_title: str | None = None
    author: str | None = None
    genre: str | None = None
    total_chapters: int = Field(default=0, ge=0)


class BookUpdate(BaseModel):
    """Request schema for updating book metadata."""
    original_title: str | None = None
    author: str | None = None
    genre: str | None = None
    total_chapters: int | None = Field(default=None, ge=0)


class BookResponse(BaseModel):
    """Response schema for book data."""
    id: str
    project_id: str
    original_title: str | None
    author: str | None
    genre: str | None
    total_chapters: int
    uploaded_chapters: int
    total_words: int
    upload_status: BookUploadStatus
    ai_summary: str | None
    main_plot_points: list[str]
    suggested_episodes: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Episode Schemas
# ============================================================================


class EpisodePlanRequest(BaseModel):
    """Request schema for AI episode planning."""
    target_episode_duration: float = Field(default=24.0, gt=0, le=120)
    max_episodes: int | None = Field(default=None, ge=1, le=100)
    style: str = Field(default="standard")  # standard/movie/short


class EpisodeSuggestion(BaseModel):
    """Suggested episode from AI planning."""
    episode_number: int
    title: str
    start_chapter: int
    end_chapter: int
    synopsis: str
    estimated_duration_minutes: float


class EpisodePlanResponse(BaseModel):
    """Response schema for AI episode planning."""
    suggested_episodes: list[EpisodeSuggestion]
    total_estimated_duration: float
    reasoning: str


class EpisodeCreate(BaseModel):
    """Request schema for creating an episode."""
    episode_number: int = Field(..., ge=1)
    title: str | None = None
    synopsis: str | None = None
    start_chapter: int = Field(..., ge=1)
    end_chapter: int = Field(..., ge=1)
    target_duration_minutes: float = Field(default=24.0, gt=0)


class EpisodeBatchCreate(BaseModel):
    """Request schema for batch creating episodes."""
    episodes: list[EpisodeCreate] = Field(..., min_length=1)


class EpisodeUpdate(BaseModel):
    """Request schema for updating an episode."""
    title: str | None = None
    synopsis: str | None = None
    start_chapter: int | None = Field(default=None, ge=1)
    end_chapter: int | None = Field(default=None, ge=1)
    target_duration_minutes: float | None = Field(default=None, gt=0)


class EpisodeResponse(BaseModel):
    """Response schema for episode data."""
    id: str
    project_id: str
    episode_number: int
    title: str | None
    synopsis: str | None
    start_chapter: int
    end_chapter: int
    target_duration_minutes: float
    actual_duration_minutes: float | None
    status: EpisodeStatus
    output_video_path: str | None
    output_video_url: str | None
    episode_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EpisodeListResponse(BaseModel):
    """Response schema for listing episodes."""
    items: list[EpisodeResponse]
    total: int

