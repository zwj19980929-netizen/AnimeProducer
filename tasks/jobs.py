import logging
import os
from datetime import datetime
from typing import List, Dict, Optional

from celery import chord
from sqlmodel import Session, select

from core.database import engine
from core.models import Shot, Project, ProjectStatus, Job, JobStatus, JobType, Episode, EpisodeStatus, Chapter, ChapterStatus
from core.editor import assemble_shots, ShotArtifact, AlignmentStrategy
from tasks.celery_app import celery_app
from api.websocket import publish_job_update_sync

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.jobs.render_project_job", task_acks_late=False)
def render_project_job(self, project_id: str, job_id: str):
    """编排整个项目的渲染任务。"""
    logger.info(f"Dispatching render job for project: {project_id}, job: {job_id}")

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.project_id != project_id:
            logger.error(f"Job not found or mismatched. project_id={project_id}, job_id={job_id}")
            return {"status": "failed", "reason": "Job not found"}

        if job.status == JobStatus.REVOKED:
            logger.info(f"Render dispatch skipped - job was cancelled: {job_id}")
            return {"status": "cancelled", "reason": "Job was cancelled"}

        job.status = JobStatus.STARTED
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

        # Publish WebSocket update
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.STARTED.value,
            "progress": 0.0,
        })

        shots = session.exec(select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)).all()
        shot_ids = [shot.shot_id for shot in shots]

    if not shot_ids:
        logger.warning("No shots found!")
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = "No shots found for rendering"
                job.completed_at = datetime.utcnow()
                session.add(job)

                # Publish WebSocket update
                publish_job_update_sync(job.id, project_id, {
                    "status": JobStatus.FAILURE.value,
                    "error_message": "No shots found for rendering",
                })

            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = "No shots found for rendering"
                session.add(project)

            session.commit()
        return {"status": "failed", "reason": "No shots found"}

    from tasks.shots import render_shot, render_shot_seedance
    from config import settings

    # 根据配置选择渲染工作流
    if settings.SEEDANCE_ENABLED and settings.ARK_API_KEY:
        render_task = render_shot_seedance
        logger.info(f"Using Seedance pipeline for project {project_id}")
    else:
        render_task = render_shot

    header = [render_task.s(sid, job_id) for sid in shot_ids]
    callback = compose_project.s(project_id, job_id)

    workflow = chord(header)(callback)
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            result = dict(job.result or {})
            if job.celery_task_id and job.celery_task_id != workflow.id:
                result["root_task_id"] = job.celery_task_id
            result["chord_id"] = workflow.id
            job.result = result
            job.celery_task_id = workflow.id
            session.add(job)
            session.commit()
    logger.info(f"Workflow started. Chord ID: {workflow.id}")
    return {"chord_id": workflow.id}


@celery_app.task(bind=True, name="tasks.jobs.compose_project", task_acks_late=False)
def compose_project(self, shot_results: List[Dict], project_id: str, job_id: str):
    """最终合成任务：收集所有 Shot 结果并拼接。"""
    logger.info(f"Composing project: {project_id}, job: {job_id}")

    # Check if job was cancelled
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job and job.status == JobStatus.REVOKED:
            logger.info(f"Composition skipped - job was cancelled for project: {project_id}")
            return {"status": "cancelled", "reason": "Job was cancelled"}

    valid_results = [r for r in shot_results if r and r.get("status") == "completed"]

    if not valid_results:
        logger.error("No valid shots to compose!")
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = "All shots failed to render"
                session.add(project)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = "All shots failed to render"
                job.completed_at = datetime.utcnow()
                session.add(job)

                # Publish WebSocket update
                publish_job_update_sync(job.id, project_id, {
                    "status": JobStatus.FAILURE.value,
                    "error_message": "All shots failed to render",
                })

            session.commit()
        return {"status": "failed", "reason": "No valid shots"}

    valid_results.sort(key=lambda x: x["shot_id"])

    artifacts = []
    for res in valid_results:
        artifacts.append(ShotArtifact(
            shot_id=res["shot_id"],
            video_path=res["video_path"],
            audio_path=res.get("audio_path"),
            dialogue=res.get("dialogue"),
            start_time=0,
            end_time=res.get("duration", 3.0)
        ))

    try:
        from config import settings
        output_dir = settings.OUTPUT_DIR
        output_filename = f"final_project_{project_id}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        final_video_path = assemble_shots(
            shots=artifacts,
            output_path=output_path,
            alignment_strategy=AlignmentStrategy.LOOP,
            crossfade_duration=0.5
        )

        # 上传到 OSS（如果已配置）
        output_video_url = None
        try:
            from integrations.oss_service import OSSService
            oss = OSSService.get_instance()
            if oss.is_configured():
                logger.info("正在上传最终视频到 OSS...")
                with open(final_video_path, 'rb') as f:
                    video_data = f.read()
                output_video_url = oss.upload_video_bytes(
                    video_data,
                    filename=f"final_project_{project_id}",
                    ext=".mp4"
                )
                logger.info(f"视频已上传到 OSS: {output_video_url}")
        except Exception as oss_err:
            logger.warning(f"OSS 上传失败，视频仅保存在本地: {oss_err}")

        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.DONE
                project.output_video_path = final_video_path
                project.output_video_url = output_video_url
                session.add(project)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.completed_at = datetime.utcnow()
                session.add(job)

                # Publish WebSocket update
                publish_job_update_sync(job.id, project_id, {
                    "status": JobStatus.SUCCESS.value,
                    "progress": 1.0,
                    "output_video_path": final_video_path,
                    "output_video_url": output_video_url,
                })

            session.commit()

        logger.info(f"Project composition complete! Saved to: {final_video_path}")
        return {"status": "success", "path": final_video_path, "url": output_video_url}

    except Exception as e:
        logger.error(f"Composition failed: {e}")
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = str(e)
                session.add(project)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                session.add(job)

                # Publish WebSocket update
                publish_job_update_sync(job.id, project_id, {
                    "status": JobStatus.FAILURE.value,
                    "error_message": str(e),
                })

            session.commit()
        raise e


@celery_app.task(bind=True, name="tasks.jobs.render_episode_job", task_acks_late=False)
def render_episode_job(self, project_id: str, episode_id: str, job_id: str):
    """编排单集的渲染任务。"""
    logger.info(f"Dispatching render job for episode: {episode_id} in project: {project_id}, job: {job_id}")

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.project_id != project_id:
            logger.error(f"Job not found or mismatched. project_id={project_id}, job_id={job_id}")
            return {"status": "failed", "reason": "Job not found"}

        if job.status == JobStatus.REVOKED:
            logger.info(f"Episode render dispatch skipped - job was cancelled: {job_id}")
            return {"status": "cancelled", "reason": "Job was cancelled"}

        # 获取集信息
        episode = session.get(Episode, episode_id)
        if not episode:
            logger.error(f"Episode not found: {episode_id}")
            return {"status": "failed", "reason": "Episode not found"}

        # 更新任务状态
        job.status = JobStatus.STARTED
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

        # 获取该集的分镜
        shots = session.exec(
            select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.sequence_order)
        ).all()
        shot_ids = [shot.shot_id for shot in shots]

    if not shot_ids:
        logger.warning(f"No shots found for episode {episode_id}!")
        with Session(engine) as session:
            episode = session.get(Episode, episode_id)
            if episode:
                episode.status = EpisodeStatus.FAILED
                session.add(episode)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = "No shots found for rendering"
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()
        return {"status": "failed", "reason": "No shots found"}

    from tasks.shots import render_shot, render_shot_seedance
    from config import settings

    # 根据配置选择渲染工作流
    if settings.SEEDANCE_ENABLED and settings.ARK_API_KEY:
        render_task = render_shot_seedance
        logger.info(f"Using Seedance pipeline for episode {episode_id}")
    else:
        render_task = render_shot

    header = [render_task.s(sid, job_id) for sid in shot_ids]
    callback = compose_episode.s(project_id, episode_id, job_id)

    workflow = chord(header)(callback)
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            result = dict(job.result or {})
            if job.celery_task_id and job.celery_task_id != workflow.id:
                result["root_task_id"] = job.celery_task_id
            result["chord_id"] = workflow.id
            job.result = result
            job.celery_task_id = workflow.id
            session.add(job)
            session.commit()
    logger.info(f"Episode workflow started. Chord ID: {workflow.id}")
    return {"chord_id": workflow.id, "episode_id": episode_id}


@celery_app.task(bind=True, name="tasks.jobs.compose_episode", task_acks_late=False)
def compose_episode(self, shot_results: List[Dict], project_id: str, episode_id: str, job_id: str):
    """单集合成任务：收集所有 Shot 结果并拼接为一集视频。"""
    logger.info(f"Composing episode: {episode_id} for project: {project_id}, job: {job_id}")

    # 检查任务是否被取消
    with Session(engine) as session:
        job = session.get(Job, job_id)

        if job and job.status == JobStatus.REVOKED:
            logger.info(f"Composition skipped - job was cancelled for episode: {episode_id}")
            return {"status": "cancelled", "reason": "Job was cancelled"}

        episode = session.get(Episode, episode_id)
        episode_number = episode.episode_number if episode else 0

    valid_results = [r for r in shot_results if r and r.get("status") == "completed"]

    if not valid_results:
        logger.error(f"No valid shots to compose for episode {episode_id}!")
        with Session(engine) as session:
            episode = session.get(Episode, episode_id)
            if episode:
                episode.status = EpisodeStatus.FAILED
                session.add(episode)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = "All shots failed to render"
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()
        return {"status": "failed", "reason": "No valid shots"}

    valid_results.sort(key=lambda x: x["shot_id"])

    artifacts = []
    for res in valid_results:
        artifacts.append(ShotArtifact(
            shot_id=res["shot_id"],
            video_path=res["video_path"],
            audio_path=res.get("audio_path"),
            dialogue=res.get("dialogue"),
            start_time=0,
            end_time=res.get("duration", 3.0)
        ))

    try:
        from config import settings
        output_dir = settings.OUTPUT_DIR
        output_filename = f"episode_{episode_number}_project_{project_id}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        final_video_path = assemble_shots(
            shots=artifacts,
            output_path=output_path,
            alignment_strategy=AlignmentStrategy.LOOP,
            crossfade_duration=0.5
        )

        # 计算实际时长
        actual_duration = sum(res.get("duration", 3.0) for res in valid_results)

        # 上传到 OSS（如果已配置）
        output_video_url = None
        try:
            from integrations.oss_service import OSSService
            oss = OSSService.get_instance()
            if oss.is_configured():
                logger.info(f"正在上传第 {episode_number} 集视频到 OSS...")
                with open(final_video_path, 'rb') as f:
                    video_data = f.read()
                output_video_url = oss.upload_video_bytes(
                    video_data,
                    filename=f"episode_{episode_number}_project_{project_id}",
                    ext=".mp4"
                )
                logger.info(f"视频已上传到 OSS: {output_video_url}")
        except Exception as oss_err:
            logger.warning(f"OSS 上传失败，视频仅保存在本地: {oss_err}")

        with Session(engine) as session:
            episode = session.get(Episode, episode_id)
            if episode:
                episode.status = EpisodeStatus.DONE
                episode.output_video_path = final_video_path
                episode.output_video_url = output_video_url
                episode.actual_duration_minutes = actual_duration / 60.0
                episode.updated_at = datetime.utcnow()
                session.add(episode)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()

        logger.info(f"Episode {episode_number} composition complete! Saved to: {final_video_path}")
        return {
            "status": "success",
            "path": final_video_path,
            "url": output_video_url,
            "episode_number": episode_number,
            "duration_minutes": actual_duration / 60.0
        }

    except Exception as e:
        logger.error(f"Episode composition failed: {e}")
        with Session(engine) as session:
            episode = session.get(Episode, episode_id)
            if episode:
                episode.status = EpisodeStatus.FAILED
                session.add(episode)

            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()
        raise e


@celery_app.task(bind=True, name="tasks.jobs.plan_episodes_job", task_acks_late=False)
def plan_episodes_job(
    self,
    project_id: str,
    job_id: str,
    target_episode_duration: Optional[int] = None,
    max_episodes: Optional[int] = None,
    style: Optional[str] = None
):
    """异步执行集数规划任务。"""
    logger.info(f"Starting episode planning for project: {project_id}")

    with Session(engine) as session:
        # 更新任务状态为开始
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": 0.1,
                "message": "正在加载章节数据..."
            })

    try:
        with Session(engine) as session:
            # 获取所有章节
            chapters = session.exec(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.chapter_number)
            ).all()

            if not chapters:
                raise ValueError("No chapters found. Please upload chapters first.")

            # 准备章节数据
            chapter_data = [
                {
                    "chapter_number": ch.chapter_number,
                    "title": ch.title,
                    "content": ch.content,
                    "word_count": ch.word_count,
                }
                for ch in chapters
            ]

            # 准备分析结果（如果有）
            from core.chapter_analyzer import ChapterAnalysis
            chapter_analyses = None
            if all(ch.status == ChapterStatus.READY for ch in chapters):
                chapter_analyses = [
                    ChapterAnalysis(
                        key_events=ch.key_events or [],
                        emotional_arc=ch.emotional_arc or "neutral",
                        importance_score=ch.importance_score or 0.5,
                        characters_appeared=ch.characters_appeared or [],
                        is_good_break_point=False,
                    )
                    for ch in chapters
                ]

        # 更新进度
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.progress = 0.3
                session.add(job)
                session.commit()

        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.STARTED.value,
            "progress": 0.3,
            "message": "正在调用 AI 规划集数..."
        })

        # 调用规划服务
        from core.episode_planner import EpisodePlanner, EpisodePlannerConfig
        planner = EpisodePlanner()
        config = EpisodePlannerConfig(
            target_duration_minutes=target_episode_duration,
            style=style,
        )

        plan = planner.plan_episodes(
            chapters=chapter_data,
            chapter_analyses=chapter_analyses,
            config=config,
        )

        # 转换为可序列化的结果
        result = {
            "suggested_episodes": [
                {
                    "episode_number": ep.episode_number,
                    "title": ep.title,
                    "start_chapter": ep.start_chapter,
                    "end_chapter": ep.end_chapter,
                    "synopsis": ep.synopsis,
                    "estimated_duration_minutes": ep.estimated_duration_minutes,
                }
                for ep in plan.episodes
            ],
            "total_estimated_duration": plan.total_estimated_duration,
            "reasoning": plan.reasoning,
        }

        # 更新任务为成功
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.result = result
                job.completed_at = datetime.utcnow()
                session.add(job)
                session.commit()

        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.SUCCESS.value,
            "progress": 1.0,
            "result": result,
            "message": f"规划完成，建议分为 {len(result['suggested_episodes'])} 集"
        })

        logger.info(f"Episode planning completed: {len(result['suggested_episodes'])} episodes")
        return result

    except Exception as e:
        logger.error(f"Episode planning failed: {e}")
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                session.add(job)
                session.commit()

        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.FAILURE.value,
            "error_message": str(e),
        })
        raise e
