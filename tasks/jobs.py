import logging
import os
from datetime import datetime
from typing import List, Dict

from celery import chord
from sqlmodel import Session, select

from core.database import engine
from core.models import Shot, Project, ProjectStatus, Job, JobStatus
from core.editor import assemble_shots, ShotArtifact, AlignmentStrategy
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.jobs.render_project_job", task_acks_late=False)
def render_project_job(self, project_id: str):
    """编排整个项目的渲染任务。"""
    logger.info(f"Dispatching render job for project: {project_id}")

    with Session(engine) as session:
        job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

        shots = session.exec(select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)).all()
        shot_ids = [shot.shot_id for shot in shots]

    if not shot_ids:
        logger.warning("No shots found!")
        with Session(engine) as session:
            job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = "No shots found for rendering"
                job.completed_at = datetime.utcnow()
                session.add(job)

            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = "No shots found for rendering"
                session.add(project)

            session.commit()
        return {"status": "failed", "reason": "No shots found"}

    from tasks.shots import render_shot

    header = [render_shot.s(sid) for sid in shot_ids]
    callback = compose_project.s(project_id)

    workflow = chord(header)(callback)
    logger.info(f"Workflow started. Chord ID: {workflow.id}")
    return {"chord_id": workflow.id}


@celery_app.task(bind=True, name="tasks.jobs.compose_project", task_acks_late=False)
def compose_project(self, shot_results: List[Dict], project_id: str):
    """最终合成任务：收集所有 Shot 结果并拼接。"""
    logger.info(f"Composing project: {project_id}")

    # Check if job was cancelled
    with Session(engine) as session:
        job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
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

            job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
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

            job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.completed_at = datetime.utcnow()
                session.add(job)

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

            job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
            if job:
                job.status = JobStatus.FAILURE
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()
        raise e