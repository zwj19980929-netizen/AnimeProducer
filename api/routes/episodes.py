"""Episode management API routes."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import func, select

from api.deps import DBSession, DirectorDep
from api.schemas import (
    EpisodeBatchCreate,
    EpisodeCreate,
    EpisodeListResponse,
    EpisodePlanRequest,
    EpisodePlanResponse,
    EpisodeResponse,
    EpisodeSuggestion,
    EpisodeUpdate,
    ErrorResponse,
    JobResponse,
    PipelineStartResponse,
    ShotListResponse,
    ShotResponse,
)
from core.models import Chapter, ChapterStatus, Episode, EpisodeStatus, Job, JobStatus, JobType, Project, Shot

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_project_or_404(session: DBSession, project_id: str) -> Project:
    """获取项目，不存在则抛出 404。"""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )
    return project


@router.post(
    "/plan",
    response_model=JobResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def plan_episodes(
    project_id: str,
    plan_request: EpisodePlanRequest,
    session: DBSession,
) -> JobResponse:
    """AI 自动规划集数（异步任务）。

    返回 Job ID，前端可通过 WebSocket 或轮询获取进度和结果。
    """
    logger.info(f"Starting async episode planning for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 检查是否有章节
    chapter_count = session.exec(
        select(func.count()).select_from(Chapter).where(Chapter.project_id == project_id)
    ).one()

    if chapter_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chapters found. Please upload chapters first.",
        )

    # 创建 Job 记录
    job = Job(
        project_id=project_id,
        job_type=JobType.EPISODE_PLAN,
        status=JobStatus.PENDING,
        progress=0.0,
        result={
            "target_episode_duration": plan_request.target_episode_duration,
            "max_episodes": plan_request.max_episodes,
            "style": plan_request.style,
        }
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # 派发 Celery 任务
    from tasks.jobs import plan_episodes_job
    plan_episodes_job.delay(
        project_id=project_id,
        job_id=job.id,
        target_episode_duration=plan_request.target_episode_duration,
        max_episodes=plan_request.max_episodes,
        style=plan_request.style,
    )

    logger.info(f"Episode planning job created: {job.id}")
    return JobResponse.model_validate(job)


@router.get(
    "/plan/{job_id}",
    response_model=EpisodePlanResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def get_plan_result(
    project_id: str,
    job_id: str,
    session: DBSession,
) -> EpisodePlanResponse:
    """获取集数规划结果。

    当任务完成后，返回规划结果。
    """
    logger.debug(f"Getting plan result for job: {job_id}")

    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    if job.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found in project: {project_id}",
        )

    if job.status == JobStatus.PENDING or job.status == JobStatus.STARTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is still running",
        )

    if job.status == JobStatus.FAILURE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job failed: {job.error_message}",
        )

    if job.status == JobStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job was cancelled",
        )

    # 从 job.result 中提取规划结果
    result = job.result or {}
    suggested_episodes = result.get("suggested_episodes", [])

    return EpisodePlanResponse(
        suggested_episodes=[
            EpisodeSuggestion(
                episode_number=ep["episode_number"],
                title=ep["title"],
                start_chapter=ep["start_chapter"],
                end_chapter=ep["end_chapter"],
                synopsis=ep["synopsis"],
                estimated_duration_minutes=ep["estimated_duration_minutes"],
            )
            for ep in suggested_episodes
        ],
        total_estimated_duration=result.get("total_estimated_duration", 0),
        reasoning=result.get("reasoning", ""),
    )


@router.post(
    "",
    response_model=EpisodeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def create_episode(
    project_id: str,
    episode_in: EpisodeCreate,
    session: DBSession,
) -> Episode:
    """创建单个集。"""
    logger.info(f"Creating episode {episode_in.episode_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 检查集数是否已存在
    existing = session.exec(
        select(Episode).where(
            Episode.project_id == project_id,
            Episode.episode_number == episode_in.episode_number
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode {episode_in.episode_number} already exists",
        )

    # 验证章节范围
    if episode_in.start_chapter > episode_in.end_chapter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_chapter must be <= end_chapter",
        )

    # 检查章节是否存在
    chapter_count = session.exec(
        select(func.count()).select_from(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number >= episode_in.start_chapter,
            Chapter.chapter_number <= episode_in.end_chapter
        )
    ).one()

    expected_count = episode_in.end_chapter - episode_in.start_chapter + 1
    if chapter_count < expected_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Some chapters in range {episode_in.start_chapter}-{episode_in.end_chapter} do not exist",
        )

    episode = Episode(
        project_id=project_id,
        episode_number=episode_in.episode_number,
        title=episode_in.title,
        synopsis=episode_in.synopsis,
        start_chapter=episode_in.start_chapter,
        end_chapter=episode_in.end_chapter,
        target_duration_minutes=episode_in.target_duration_minutes,
        status=EpisodeStatus.PLANNED,
    )

    session.add(episode)
    session.commit()
    session.refresh(episode)

    # 更新章节的 suggested_episode 字段
    chapters = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number >= episode_in.start_chapter,
            Chapter.chapter_number <= episode_in.end_chapter
        )
    ).all()

    for chapter in chapters:
        chapter.suggested_episode = episode_in.episode_number
        session.add(chapter)

    session.commit()

    logger.info(f"Created episode: {episode.id}")
    return episode


@router.post(
    "/batch",
    response_model=EpisodeListResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def create_episodes_batch(
    project_id: str,
    batch_in: EpisodeBatchCreate,
    session: DBSession,
) -> EpisodeListResponse:
    """批量创建集（确认 AI 规划）。"""
    logger.info(f"Batch creating {len(batch_in.episodes)} episodes for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 检查集数是否有重复
    episode_numbers = [ep.episode_number for ep in batch_in.episodes]
    if len(episode_numbers) != len(set(episode_numbers)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate episode numbers in batch",
        )

    # 检查是否与现有集冲突
    existing = session.exec(
        select(Episode.episode_number).where(
            Episode.project_id == project_id,
            Episode.episode_number.in_(episode_numbers)
        )
    ).all()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episodes already exist: {existing}",
        )

    # 验证章节范围不重叠
    ranges = [(ep.start_chapter, ep.end_chapter) for ep in batch_in.episodes]
    for i, (s1, e1) in enumerate(ranges):
        for j, (s2, e2) in enumerate(ranges):
            if i < j:
                if not (e1 < s2 or e2 < s1):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Chapter ranges overlap: {s1}-{e1} and {s2}-{e2}",
                    )

    # 创建集
    created_episodes = []
    for episode_in in batch_in.episodes:
        episode = Episode(
            project_id=project_id,
            episode_number=episode_in.episode_number,
            title=episode_in.title,
            synopsis=episode_in.synopsis,
            start_chapter=episode_in.start_chapter,
            end_chapter=episode_in.end_chapter,
            target_duration_minutes=episode_in.target_duration_minutes,
            status=EpisodeStatus.PLANNED,
        )
        session.add(episode)
        created_episodes.append(episode)

    session.commit()

    # 更新章节的 suggested_episode 字段
    for episode in created_episodes:
        chapters = session.exec(
            select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number >= episode.start_chapter,
                Chapter.chapter_number <= episode.end_chapter
            )
        ).all()

        for chapter in chapters:
            chapter.suggested_episode = episode.episode_number
            session.add(chapter)

    session.commit()

    # 刷新所有集
    for episode in created_episodes:
        session.refresh(episode)

    logger.info(f"Batch created {len(created_episodes)} episodes")
    return EpisodeListResponse(
        items=[EpisodeResponse.model_validate(ep) for ep in created_episodes],
        total=len(created_episodes),
    )


@router.get(
    "",
    response_model=EpisodeListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_episodes(
    project_id: str,
    session: DBSession,
    status_filter: Optional[EpisodeStatus] = Query(default=None, alias="status"),
) -> EpisodeListResponse:
    """列出项目所有集。"""
    logger.debug(f"Listing episodes for project: {project_id}")

    _get_project_or_404(session, project_id)

    query = select(Episode).where(Episode.project_id == project_id)

    if status_filter:
        query = query.where(Episode.status == status_filter)

    query = query.order_by(Episode.episode_number)
    episodes = session.exec(query).all()

    return EpisodeListResponse(
        items=[EpisodeResponse.model_validate(ep) for ep in episodes],
        total=len(episodes),
    )


@router.get(
    "/{episode_number}",
    response_model=EpisodeResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_episode(
    project_id: str,
    episode_number: int,
    session: DBSession,
) -> Episode:
    """获取单集详情。"""
    logger.debug(f"Getting episode {episode_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    episode = session.exec(
        select(Episode).where(
            Episode.project_id == project_id,
            Episode.episode_number == episode_number
        )
    ).first()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_number} not found",
        )

    return episode


@router.patch(
    "/{episode_number}",
    response_model=EpisodeResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_episode(
    project_id: str,
    episode_number: int,
    episode_in: EpisodeUpdate,
    session: DBSession,
) -> Episode:
    """更新集信息。"""
    logger.info(f"Updating episode {episode_number} for project: {project_id}")

    _get_project_or_404(session, project_id)

    episode = session.exec(
        select(Episode).where(
            Episode.project_id == project_id,
            Episode.episode_number == episode_number
        )
    ).first()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_number} not found",
        )

    update_data = episode_in.model_dump(exclude_unset=True)

    # 如果更新了章节范围，需要验证
    new_start = update_data.get("start_chapter", episode.start_chapter)
    new_end = update_data.get("end_chapter", episode.end_chapter)

    if new_start > new_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_chapter must be <= end_chapter",
        )

    for field, value in update_data.items():
        setattr(episode, field, value)

    episode.updated_at = datetime.utcnow()

    session.add(episode)
    session.commit()
    session.refresh(episode)

    logger.info(f"Updated episode {episode_number}")
    return episode


@router.delete(
    "/{episode_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_episode(
    project_id: str,
    episode_number: int,
    session: DBSession,
) -> None:
    """删除集。"""
    logger.info(f"Deleting episode {episode_number} from project: {project_id}")

    _get_project_or_404(session, project_id)

    episode = session.exec(
        select(Episode).where(
            Episode.project_id == project_id,
            Episode.episode_number == episode_number
        )
    ).first()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_number} not found",
        )

    # 清除章节的 suggested_episode 字段
    chapters = session.exec(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.suggested_episode == episode_number
        )
    ).all()

    for chapter in chapters:
        chapter.suggested_episode = None
        session.add(chapter)

    session.delete(episode)
    session.commit()

    logger.info(f"Deleted episode {episode_number}")


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_all_episodes(
    project_id: str,
    session: DBSession,
) -> None:
    """删除项目所有集（重新规划时使用）。"""
    logger.info(f"Deleting all episodes for project: {project_id}")

    _get_project_or_404(session, project_id)

    # 清除所有章节的 suggested_episode 字段
    chapters = session.exec(
        select(Chapter).where(Chapter.project_id == project_id)
    ).all()

    for chapter in chapters:
        chapter.suggested_episode = None
        session.add(chapter)

    # 删除所有集
    episodes = session.exec(
        select(Episode).where(Episode.project_id == project_id)
    ).all()

    for episode in episodes:
        session.delete(episode)

    session.commit()

    logger.info(f"Deleted {len(episodes)} episodes")


# ============================================================================
# Episode Action Routes (分镜生成和渲染)
# ============================================================================


@router.post(
    "/{episode_number}/storyboard/generate",
    response_model=ShotListResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def generate_episode_storyboard(
    project_id: str,
    episode_number: int,
    session: DBSession,
    director: DirectorDep,
) -> ShotListResponse:
    """
    为单集生成分镜。

    根据该集包含的章节内容，使用 LLM 生成分镜列表。
    """
    logger.info(f"Generating storyboard for episode {episode_number} in project: {project_id}")

    _get_project_or_404(session, project_id)

    try:
        shots = director.director.generate_episode_storyboard(project_id, episode_number)
        return ShotListResponse(
            items=[ShotResponse.model_validate(s) for s in shots],
            total=len(shots),
        )
    except Exception as e:
        logger.error(f"Storyboard generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{episode_number}/render/start",
    response_model=PipelineStartResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def start_episode_render(
    project_id: str,
    episode_number: int,
    session: DBSession,
    director: DirectorDep,
) -> PipelineStartResponse:
    """
    启动单集渲染。

    将该集的所有分镜渲染为视频片段，然后合成为一集完整视频。
    """
    logger.info(f"Starting render for episode {episode_number} in project: {project_id}")

    _get_project_or_404(session, project_id)

    try:
        job = director.director.start_episode_render_job(project_id, episode_number)
        return PipelineStartResponse(
            job_id=job.id,
            project_id=project_id,
            message=f"Episode {episode_number} render started successfully",
        )
    except Exception as e:
        logger.error(f"Episode render start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/{episode_number}/shots",
    response_model=ShotListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_episode_shots(
    project_id: str,
    episode_number: int,
    session: DBSession,
) -> ShotListResponse:
    """获取单集的所有分镜。"""
    logger.debug(f"Listing shots for episode {episode_number} in project: {project_id}")

    _get_project_or_404(session, project_id)

    episode = session.exec(
        select(Episode).where(
            Episode.project_id == project_id,
            Episode.episode_number == episode_number
        )
    ).first()

    if not episode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode {episode_number} not found",
        )

    shots = session.exec(
        select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.sequence_order)
    ).all()

    return ShotListResponse(
        items=[ShotResponse.model_validate(s) for s in shots],
        total=len(shots),
    )
