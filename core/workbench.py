"""Aggregations that power the stage-based production workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from api.workbench_schemas import (
    ActionLink,
    BookWorkspaceItem,
    CharacterWorkspaceItem,
    DashboardResponse,
    DeliveryAssetSummary,
    EpisodePlanDraftSummary,
    EpisodePlanSuggestionSummary,
    EpisodeWorkspaceItem,
    OperationSummary,
    ProjectCardListResponse,
    ProjectCardSummary,
    ProjectHeaderSummary,
    StageSummary,
    WorkspaceResponse,
)
from config import settings
from core.models import (
    Book,
    Chapter,
    ChapterStatus,
    Character,
    CharacterImage,
    CharacterImageType,
    Episode,
    Job,
    JobStatus,
    JobType,
    Project,
    Shot,
)

STAGE_CONFIG = [
    ("SOURCE_IMPORT", "书源导入", "source"),
    ("CHAPTER_ANALYSIS", "章节分析", "source"),
    ("CHARACTER_BIBLE", "角色圣经", "characters"),
    ("EPISODE_PLANNING", "分集规划", "episodes"),
    ("STORYBOARD_WORKBENCH", "分镜工作台", "storyboard"),
    ("RENDER_CENTER", "渲染中心", "renders"),
    ("DELIVERY_OUTPUT", "交付输出", "delivery"),
]


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return max(0.0, min(1.0, float(numerator) / float(denominator)))


def _public_asset_url(path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None
    if path_or_url.startswith(("http://", "https://", "/assets/")):
        return path_or_url

    try:
        relative = Path(path_or_url).resolve().relative_to(settings.ASSETS_DIR.resolve())
        return f"/assets/{relative.as_posix()}"
    except Exception:
        return path_or_url


def _job_label(job: Job) -> str:
    labels = {
        JobType.ASSET_GENERATION: "角色资产生成",
        JobType.STORYBOARD_GENERATION: "分镜生成",
        JobType.SHOT_RENDER: "镜头渲染",
        JobType.VIDEO_COMPOSITION: "视频合成",
        JobType.FULL_PIPELINE: "全流程渲染",
        JobType.EPISODE_PLAN: "分集规划",
    }
    label = labels.get(job.job_type, job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type))
    if job.job_type == JobType.ASSET_GENERATION and isinstance(job.result, dict):
        character_id = job.result.get("character_id")
        if isinstance(character_id, str) and character_id:
            return f"{label} · {character_id}"
    return label


def _serialize_job(job: Job) -> OperationSummary:
    return OperationSummary(
        id=job.id,
        type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        label=_job_label(job),
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        progress=job.progress,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


def _load_project_bundle(session: Session, project_id: str) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    book = session.exec(
        select(Book).where(Book.project_id == project_id)
    ).first()
    chapters = session.exec(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
    ).all()
    characters = session.exec(
        select(Character).where(Character.project_id == project_id).order_by(Character.created_at)
    ).all()
    episodes = session.exec(
        select(Episode).where(Episode.project_id == project_id).order_by(Episode.episode_number)
    ).all()
    shots = session.exec(
        select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)
    ).all()
    jobs = session.exec(
        select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc())
    ).all()

    character_ids = [character.character_id for character in characters]
    images = []
    if character_ids:
        images = session.exec(
            select(CharacterImage).where(CharacterImage.character_id.in_(character_ids))
        ).all()

    return {
        "project": project,
        "book": book,
        "chapters": chapters,
        "characters": characters,
        "episodes": episodes,
        "shots": shots,
        "jobs": jobs,
        "images": images,
    }


def _build_snapshot(bundle: dict[str, Any]) -> dict[str, Any]:
    book: Book | None = bundle["book"]
    chapters: list[Chapter] = bundle["chapters"]
    characters: list[Character] = bundle["characters"]
    episodes: list[Episode] = bundle["episodes"]
    shots: list[Shot] = bundle["shots"]
    jobs: list[Job] = bundle["jobs"]
    images: list[CharacterImage] = bundle["images"]

    total_chapters = len(chapters)
    analyzed_chapters = sum(1 for chapter in chapters if chapter.status == ChapterStatus.READY)

    image_counts: dict[str, dict[str, int]] = {}
    for image in images:
        bucket = image_counts.setdefault(image.character_id, {})
        key = image.image_type.value if hasattr(image.image_type, "value") else str(image.image_type)
        bucket[key] = bucket.get(key, 0) + 1

    anchor_ready = sum(
        1
        for character in characters
        if character.anchor_image_id or character.anchor_image_path or character.anchor_image_url
    )

    shots_by_episode: dict[str, int] = {}
    for shot in shots:
        if shot.episode_id:
            shots_by_episode[shot.episode_id] = shots_by_episode.get(shot.episode_id, 0) + 1

    episodes_with_shots = sum(1 for episode in episodes if shots_by_episode.get(episode.id, 0) > 0)
    deliveries_count = sum(1 for episode in episodes if episode.output_video_path or episode.output_video_url)

    latest_plan_job = next((job for job in jobs if job.job_type == JobType.EPISODE_PLAN), None)
    running_jobs = [job for job in jobs if job.status in {JobStatus.PENDING, JobStatus.STARTED}]
    running_render_jobs = [
        job
        for job in running_jobs
        if job.job_type in {JobType.FULL_PIPELINE, JobType.SHOT_RENDER, JobType.VIDEO_COMPOSITION}
    ]
    failed_render_jobs = [
        job
        for job in jobs
        if job.status == JobStatus.FAILURE
        and job.job_type in {JobType.FULL_PIPELINE, JobType.SHOT_RENDER, JobType.VIDEO_COMPOSITION}
    ]

    source_progress = (
        _safe_ratio(book.uploaded_chapters, max(book.total_chapters, 1)) if book and book.uploaded_chapters else 0.0
    )
    analysis_progress = _safe_ratio(analyzed_chapters, total_chapters)
    if not characters:
        character_progress = 0.0
    elif anchor_ready == 0:
        character_progress = 0.45
    else:
        character_progress = min(1.0, 0.45 + 0.55 * _safe_ratio(anchor_ready, len(characters)))

    if episodes:
        episode_progress = 1.0
    elif latest_plan_job and latest_plan_job.status == JobStatus.SUCCESS:
        episode_progress = 0.75
    elif latest_plan_job and latest_plan_job.status in {JobStatus.PENDING, JobStatus.STARTED}:
        episode_progress = 0.35
    else:
        episode_progress = 0.0

    storyboard_progress = _safe_ratio(episodes_with_shots, len(episodes))
    render_progress = _safe_ratio(deliveries_count, len(episodes))
    if running_render_jobs:
        render_progress = max(
            render_progress,
            sum(job.progress for job in running_render_jobs) / max(len(running_render_jobs), 1),
        )
    delivery_progress = _safe_ratio(deliveries_count, len(episodes))

    stage_map = {
        "SOURCE_IMPORT": {
            "progress": 1.0 if total_chapters > 0 else source_progress,
            "status": "COMPLETED" if total_chapters > 0 else "NOT_STARTED",
            "metrics": {
                "book_title": book.original_title if book else None,
                "chapters_uploaded": total_chapters,
            },
            "blockers": [] if total_chapters > 0 else ["还没有导入原著文本"],
            "primary_action": ActionLink(label="导入书源", target=f"/projects/{bundle['project'].id}/source"),
        },
        "CHAPTER_ANALYSIS": {
            "progress": analysis_progress,
            "status": (
                "BLOCKED" if total_chapters == 0 else
                "NOT_STARTED" if analyzed_chapters == 0 else
                "IN_PROGRESS" if analyzed_chapters < total_chapters else
                "COMPLETED"
            ),
            "metrics": {
                "chapters_total": total_chapters,
                "chapters_analyzed": analyzed_chapters,
            },
            "blockers": (
                ["请先导入章节"] if total_chapters == 0 else
                [f"{total_chapters - analyzed_chapters} 章待分析"] if analyzed_chapters < total_chapters else
                []
            ),
            "primary_action": ActionLink(label="继续章节分析", target=f"/projects/{bundle['project'].id}/source"),
        },
        "CHARACTER_BIBLE": {
            "progress": character_progress,
            "status": (
                "BLOCKED" if total_chapters == 0 else
                "NOT_STARTED" if not characters else
                "IN_PROGRESS" if anchor_ready < len(characters) else
                "COMPLETED"
            ),
            "metrics": {
                "characters_total": len(characters),
                "anchors_ready": anchor_ready,
            },
            "blockers": (
                ["请先完成章节分析并扫描角色"] if total_chapters == 0 else
                ["尚未扫描角色"] if not characters else
                [f"{len(characters) - anchor_ready} 个角色未设置锚点图"] if anchor_ready < len(characters) else
                []
            ),
            "primary_action": ActionLink(label="维护角色圣经", target=f"/projects/{bundle['project'].id}/characters"),
        },
        "EPISODE_PLANNING": {
            "progress": episode_progress,
            "status": (
                "BLOCKED" if analyzed_chapters < total_chapters or total_chapters == 0 else
                "COMPLETED" if episodes else
                "READY_FOR_REVIEW" if latest_plan_job and latest_plan_job.status == JobStatus.SUCCESS else
                "FAILED" if latest_plan_job and latest_plan_job.status == JobStatus.FAILURE else
                "IN_PROGRESS" if latest_plan_job and latest_plan_job.status in {JobStatus.PENDING, JobStatus.STARTED} else
                "NOT_STARTED"
            ),
            "metrics": {
                "episodes_total": len(episodes),
                "draft_available": bool(latest_plan_job and latest_plan_job.status == JobStatus.SUCCESS),
            },
            "blockers": (
                ["请先完成全部章节分析"] if total_chapters == 0 or analyzed_chapters < total_chapters else
                ["尚未生成分集草案"] if not episodes and latest_plan_job is None else
                []
            ),
            "primary_action": ActionLink(label="规划分集", target=f"/projects/{bundle['project'].id}/episodes"),
        },
        "STORYBOARD_WORKBENCH": {
            "progress": storyboard_progress,
            "status": (
                "BLOCKED" if not episodes else
                "NOT_STARTED" if episodes_with_shots == 0 else
                "IN_PROGRESS" if episodes_with_shots < len(episodes) else
                "COMPLETED"
            ),
            "metrics": {
                "episodes_ready": episodes_with_shots,
                "shots_total": len(shots),
            },
            "blockers": (
                ["请先确认分集"] if not episodes else
                [f"{len(episodes) - episodes_with_shots} 集尚未生成分镜"] if episodes_with_shots < len(episodes) else
                []
            ),
            "primary_action": ActionLink(label="进入分镜工作台", target=f"/projects/{bundle['project'].id}/storyboard"),
        },
        "RENDER_CENTER": {
            "progress": render_progress,
            "status": (
                "BLOCKED" if not episodes else
                "FAILED" if failed_render_jobs and not running_render_jobs else
                "IN_PROGRESS" if running_render_jobs else
                "COMPLETED" if deliveries_count == len(episodes) and episodes else
                "NOT_STARTED"
            ),
            "metrics": {
                "active_batches": len(running_render_jobs),
                "deliveries_ready": deliveries_count,
            },
            "blockers": (
                ["请先完成分镜"] if not episodes or episodes_with_shots == 0 else
                [f"{len(failed_render_jobs)} 个渲染任务失败"] if failed_render_jobs else
                []
            ),
            "primary_action": ActionLink(label="查看渲染中心", target=f"/projects/{bundle['project'].id}/renders"),
        },
        "DELIVERY_OUTPUT": {
            "progress": delivery_progress,
            "status": (
                "BLOCKED" if not episodes else
                "NOT_STARTED" if deliveries_count == 0 else
                "IN_PROGRESS" if deliveries_count < len(episodes) else
                "COMPLETED"
            ),
            "metrics": {
                "deliveries_total": deliveries_count,
                "episodes_total": len(episodes),
            },
            "blockers": (
                ["还没有可预览的成片"] if episodes and deliveries_count == 0 else
                [f"{len(episodes) - deliveries_count} 集尚未交付"] if episodes and deliveries_count < len(episodes) else
                []
            ),
            "primary_action": ActionLink(label="查看交付输出", target=f"/projects/{bundle['project'].id}/delivery"),
        },
    }

    stage_summaries = [
        StageSummary(
            key=stage_key,
            label=stage_label,
            status=stage_map[stage_key]["status"],
            progress=stage_map[stage_key]["progress"],
            metrics=stage_map[stage_key]["metrics"],
            blockers=stage_map[stage_key]["blockers"],
            primary_action=stage_map[stage_key]["primary_action"],
        )
        for stage_key, stage_label, _route_key in STAGE_CONFIG
    ]

    current_stage = next(
        (stage for stage in stage_summaries if stage.status != "COMPLETED"),
        stage_summaries[-1],
    )

    blockers: list[str] = []
    for stage in stage_summaries:
        for blocker in stage.blockers:
            if blocker not in blockers:
                blockers.append(blocker)

    metrics = {
        "chapters_total": total_chapters,
        "chapters_analyzed": analyzed_chapters,
        "characters_total": len(characters),
        "anchors_ready": anchor_ready,
        "episodes_total": len(episodes),
        "episodes_storyboarded": episodes_with_shots,
        "deliveries_total": deliveries_count,
    }

    completion_rate = round(sum(stage.progress for stage in stage_summaries) / len(stage_summaries), 3)

    return {
        "book": book,
        "chapters": chapters,
        "characters": characters,
        "episodes": episodes,
        "jobs": jobs,
        "shots": shots,
        "images": images,
        "image_counts": image_counts,
        "shots_by_episode": shots_by_episode,
        "latest_plan_job": latest_plan_job,
        "recent_operations": [_serialize_job(job) for job in jobs[:8]],
        "active_operations": [_serialize_job(job) for job in running_jobs[:8]],
        "stage_summaries": stage_summaries,
        "current_stage": current_stage,
        "completion_rate": completion_rate,
        "blockers": blockers,
        "metrics": metrics,
    }


def build_project_card(session: Session, project: Project) -> ProjectCardSummary:
    bundle = _load_project_bundle(session, project.id)
    snapshot = _build_snapshot(bundle)
    current_stage: StageSummary = snapshot["current_stage"]

    return ProjectCardSummary(
        id=project.id,
        name=project.name,
        description=project.description,
        style_preset=project.style_preset,
        status=project.status.value if hasattr(project.status, "value") else str(project.status),
        current_stage=current_stage.key,
        current_stage_label=current_stage.label,
        completion_rate=snapshot["completion_rate"],
        updated_at=project.updated_at,
        next_action=current_stage.primary_action,
        blockers=snapshot["blockers"][:2],
        metrics=snapshot["metrics"],
    )


def list_project_cards(session: Session) -> ProjectCardListResponse:
    projects = session.exec(select(Project).order_by(Project.updated_at.desc())).all()
    items = [build_project_card(session, project) for project in projects]
    return ProjectCardListResponse(items=items, total=len(items))


def _project_header(project: Project, snapshot: dict[str, Any]) -> ProjectHeaderSummary:
    current_stage: StageSummary = snapshot["current_stage"]
    return ProjectHeaderSummary(
        id=project.id,
        name=project.name,
        description=project.description,
        style_preset=project.style_preset,
        status=project.status.value if hasattr(project.status, "value") else str(project.status),
        current_stage=current_stage.key,
        current_stage_label=current_stage.label,
        completion_rate=snapshot["completion_rate"],
        updated_at=project.updated_at,
        next_action=current_stage.primary_action,
    )


def build_dashboard(session: Session, project_id: str) -> DashboardResponse:
    bundle = _load_project_bundle(session, project_id)
    snapshot = _build_snapshot(bundle)
    project = bundle["project"]
    return DashboardResponse(
        project=_project_header(project, snapshot),
        metrics=snapshot["metrics"],
        stage_summaries=snapshot["stage_summaries"],
        blockers=snapshot["blockers"],
        recent_operations=snapshot["recent_operations"],
    )


def _build_book_item(book: Book | None) -> BookWorkspaceItem | None:
    if book is None:
        return None
    return BookWorkspaceItem(
        id=book.id,
        title=book.original_title,
        author=book.author,
        genre=book.genre,
        upload_status=book.upload_status.value if hasattr(book.upload_status, "value") else str(book.upload_status),
        total_chapters=book.total_chapters,
        uploaded_chapters=book.uploaded_chapters,
        total_words=book.total_words,
        ai_summary=book.ai_summary,
        suggested_episodes=book.suggested_episodes,
    )


def _build_characters(characters: list[Character], image_counts: dict[str, dict[str, int]]) -> list[CharacterWorkspaceItem]:
    items: list[CharacterWorkspaceItem] = []
    for character in characters:
        counts = image_counts.get(character.character_id, {})
        anchor_url = _public_asset_url(character.anchor_image_url or character.anchor_image_path)
        reference_url = _public_asset_url(character.reference_image_url or character.reference_image_path)
        has_anchor = bool(anchor_url)
        candidate_count = counts.get(CharacterImageType.CANDIDATE.value, 0)
        variant_count = counts.get(CharacterImageType.VARIANT.value, 0)

        issues: list[str] = []
        if not has_anchor and candidate_count == 0:
            issues.append("尚未生成候选图")
        elif not has_anchor:
            issues.append("候选图已生成，但未设为锚点图")
        if not character.voice_id:
            issues.append("未配置语音")

        if has_anchor and variant_count > 0:
            asset_status = "VARIANTS_READY"
        elif has_anchor:
            asset_status = "ANCHOR_READY"
        elif candidate_count > 0:
            asset_status = "CANDIDATES_READY"
        else:
            asset_status = "EMPTY"

        items.append(
            CharacterWorkspaceItem(
                character_id=character.character_id,
                name=character.name,
                aliases=list(character.aliases or []),
                bio=character.bio or "",
                appearance_prompt=character.appearance_prompt or character.prompt_base or "",
                first_appearance_chapter=character.first_appearance_chapter,
                voice_id=character.voice_id,
                anchor_image_url=anchor_url,
                reference_image_url=reference_url,
                asset_status=asset_status,
                review_status="APPROVED" if has_anchor else "PENDING",
                source_chapters=[character.first_appearance_chapter] if character.first_appearance_chapter else [],
                image_counts=counts,
                issues=issues,
            )
        )
    return items


def _build_plan_draft(job: Job | None) -> EpisodePlanDraftSummary | None:
    if job is None:
        return None

    result = job.result or {}
    suggestions = [
        EpisodePlanSuggestionSummary(
            episode_number=item["episode_number"],
            title=item["title"],
            start_chapter=item["start_chapter"],
            end_chapter=item["end_chapter"],
            synopsis=item["synopsis"],
            estimated_duration_minutes=item["estimated_duration_minutes"],
        )
        for item in result.get("suggested_episodes", [])
        if isinstance(item, dict)
    ]

    return EpisodePlanDraftSummary(
        job_id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        updated_at=job.completed_at or job.created_at,
        reasoning=result.get("reasoning"),
        total_estimated_duration=result.get("total_estimated_duration"),
        suggestions=suggestions,
    )


def _build_episodes(episodes: list[Episode], shots_by_episode: dict[str, int]) -> list[EpisodeWorkspaceItem]:
    items: list[EpisodeWorkspaceItem] = []
    for episode in episodes:
        items.append(
            EpisodeWorkspaceItem(
                id=episode.id,
                episode_number=episode.episode_number,
                title=episode.title,
                synopsis=episode.synopsis,
                start_chapter=episode.start_chapter,
                end_chapter=episode.end_chapter,
                target_duration_minutes=episode.target_duration_minutes,
                actual_duration_minutes=episode.actual_duration_minutes,
                status=episode.status.value if hasattr(episode.status, "value") else str(episode.status),
                shot_count=shots_by_episode.get(episode.id, 0),
                has_delivery=bool(episode.output_video_path or episode.output_video_url),
                output_video_url=_public_asset_url(episode.output_video_url or episode.output_video_path),
                updated_at=episode.updated_at,
            )
        )
    return items


def _build_deliveries(episodes: list[Episode]) -> list[DeliveryAssetSummary]:
    items: list[DeliveryAssetSummary] = []
    completed = [episode for episode in episodes if episode.output_video_path or episode.output_video_url]
    completed.sort(key=lambda episode: episode.updated_at, reverse=True)
    for episode in completed:
        items.append(
            DeliveryAssetSummary(
                episode_id=episode.id,
                episode_number=episode.episode_number,
                title=episode.title,
                version_label=f"EP{episode.episode_number:02d}_MASTER",
                duration_minutes=episode.actual_duration_minutes,
                video_url=_public_asset_url(episode.output_video_url or episode.output_video_path),
                updated_at=episode.updated_at,
            )
        )
    return items


def build_workspace(session: Session, project_id: str) -> WorkspaceResponse:
    bundle = _load_project_bundle(session, project_id)
    snapshot = _build_snapshot(bundle)
    project = bundle["project"]

    chapters = bundle["chapters"]
    characters = bundle["characters"]
    episodes = bundle["episodes"]

    return WorkspaceResponse(
        project=_project_header(project, snapshot),
        metrics=snapshot["metrics"],
        stage_summaries=snapshot["stage_summaries"],
        blockers=snapshot["blockers"],
        recent_operations=snapshot["recent_operations"],
        active_operations=snapshot["active_operations"],
        book=_build_book_item(bundle["book"]),
        chapters=[
            {
                "chapter_id": chapter.chapter_id,
                "chapter_number": chapter.chapter_number,
                "title": chapter.title,
                "word_count": chapter.word_count,
                "status": chapter.status.value if hasattr(chapter.status, "value") else str(chapter.status),
                "emotional_arc": chapter.emotional_arc,
                "importance_score": chapter.importance_score,
                "key_events": list(chapter.key_events or []),
                "characters_appeared": list(chapter.characters_appeared or []),
                "suggested_episode": chapter.suggested_episode,
            }
            for chapter in chapters
        ],
        characters=_build_characters(characters, snapshot["image_counts"]),
        episode_plan_draft=_build_plan_draft(snapshot["latest_plan_job"]),
        episodes=_build_episodes(episodes, snapshot["shots_by_episode"]),
        deliveries=_build_deliveries(episodes),
    )
