"""Pydantic request/response schemas for API endpoints.

These schemas are separate from SQLModel tables to allow
independent evolution of API contracts and database schema.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.models import JobStatus, JobType, ProjectStatus, ShotRenderStatus


# ============================================================================
# Project Schemas
# ============================================================================


class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    script_content: str | None = None
    style_preset: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    script_content: str | None = None
    style_preset: str | None = None
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    """Response schema for project data."""
    id: str
    name: str
    description: str | None
    status: ProjectStatus
    script_content: str | None
    style_preset: str | None
    output_video_path: str | None
    error_message: str | None
    metadata: dict[str, Any]
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterUpdate(BaseModel):
    """Request schema for updating a character."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_base: str | None = None
    reference_image_path: str | None = None
    voice_id: str | None = None
    metadata: dict[str, Any] | None = None


class CharacterResponse(BaseModel):
    """Response schema for character data."""
    character_id: str
    project_id: str | None
    name: str
    prompt_base: str
    reference_image_path: str
    voice_id: str | None
    metadata: dict[str, Any]
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
    project_id: str
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
