"""Schemas for the stage-based production workbench."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionLink(BaseModel):
    """Recommended next action."""

    label: str
    target: str


class StageSummary(BaseModel):
    """A single stage card on the dashboard."""

    key: str
    label: str
    status: str
    progress: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    primary_action: ActionLink | None = None


class OperationSummary(BaseModel):
    """Normalized operation/job summary."""

    id: str
    type: str
    label: str
    status: str
    progress: float
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class ProjectCardSummary(BaseModel):
    """Project card used on the redesigned project list."""

    id: str
    name: str
    description: str | None = None
    style_preset: str | None = None
    status: str
    current_stage: str
    current_stage_label: str
    completion_rate: float
    updated_at: datetime
    next_action: ActionLink | None = None
    blockers: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ProjectCardListResponse(BaseModel):
    items: list[ProjectCardSummary]
    total: int


class ProjectHeaderSummary(BaseModel):
    """Project header data shared across workbench pages."""

    id: str
    name: str
    description: str | None = None
    style_preset: str | None = None
    status: str
    current_stage: str
    current_stage_label: str
    completion_rate: float
    updated_at: datetime
    next_action: ActionLink | None = None


class DashboardResponse(BaseModel):
    project: ProjectHeaderSummary
    metrics: dict[str, Any] = Field(default_factory=dict)
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recent_operations: list[OperationSummary] = Field(default_factory=list)


class BookWorkspaceItem(BaseModel):
    id: str | None = None
    title: str | None = None
    author: str | None = None
    genre: str | None = None
    source_type: str = "TXT"
    upload_status: str = "EMPTY"
    total_chapters: int = 0
    uploaded_chapters: int = 0
    total_words: int = 0
    ai_summary: str | None = None
    suggested_episodes: int | None = None


class ChapterWorkspaceItem(BaseModel):
    chapter_id: str
    chapter_number: int
    title: str | None = None
    word_count: int
    status: str
    emotional_arc: str | None = None
    importance_score: float = 0.0
    key_events: list[str] = Field(default_factory=list)
    characters_appeared: list[str] = Field(default_factory=list)
    suggested_episode: int | None = None


class CharacterWorkspaceItem(BaseModel):
    character_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    bio: str = ""
    appearance_prompt: str = ""
    first_appearance_chapter: int = 0
    voice_id: str | None = None
    anchor_image_url: str | None = None
    reference_image_url: str | None = None
    asset_status: str
    review_status: str
    source_chapters: list[int] = Field(default_factory=list)
    image_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class EpisodePlanSuggestionSummary(BaseModel):
    episode_number: int
    title: str
    start_chapter: int
    end_chapter: int
    synopsis: str
    estimated_duration_minutes: float


class EpisodePlanDraftSummary(BaseModel):
    job_id: str
    status: str
    updated_at: datetime
    reasoning: str | None = None
    total_estimated_duration: float | None = None
    suggestions: list[EpisodePlanSuggestionSummary] = Field(default_factory=list)


class EpisodeWorkspaceItem(BaseModel):
    id: str
    episode_number: int
    title: str | None = None
    synopsis: str | None = None
    start_chapter: int
    end_chapter: int
    target_duration_minutes: float
    actual_duration_minutes: float | None = None
    status: str
    shot_count: int = 0
    has_delivery: bool = False
    output_video_url: str | None = None
    updated_at: datetime


class DeliveryAssetSummary(BaseModel):
    episode_id: str
    episode_number: int
    title: str | None = None
    version_label: str
    duration_minutes: float | None = None
    video_url: str | None = None
    updated_at: datetime


class WorkspaceResponse(BaseModel):
    project: ProjectHeaderSummary
    metrics: dict[str, Any] = Field(default_factory=dict)
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recent_operations: list[OperationSummary] = Field(default_factory=list)
    active_operations: list[OperationSummary] = Field(default_factory=list)
    book: BookWorkspaceItem | None = None
    chapters: list[ChapterWorkspaceItem] = Field(default_factory=list)
    characters: list[CharacterWorkspaceItem] = Field(default_factory=list)
    episode_plan_draft: EpisodePlanDraftSummary | None = None
    episodes: list[EpisodeWorkspaceItem] = Field(default_factory=list)
    deliveries: list[DeliveryAssetSummary] = Field(default_factory=list)


class ShotUpdateRequest(BaseModel):
    """Editable shot fields from the storyboard workbench."""

    duration: float | None = Field(default=None, gt=0)
    scene_description: str | None = None
    visual_prompt: str | None = None
    camera_movement: str | None = None
    characters_in_shot: list[str] | None = None
    dialogue: str | None = None
    action_type: str | None = None
