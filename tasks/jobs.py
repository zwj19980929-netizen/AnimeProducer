import logging
from datetime import datetime
from typing import Optional

from celery import chord
from sqlmodel import Session, select

from core.database import engine
from core.models import Shot
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


class Job:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.status = "pending"
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def start(self):
        self.status = "running"
        self.started_at = datetime.utcnow()

    def complete(self):
        self.status = "completed"
        self.finished_at = datetime.utcnow()

    def fail(self, error: str):
        self.status = "failed"
        self.finished_at = datetime.utcnow()
        self.error = error


@celery_app.task(bind=True, name="tasks.jobs.render_project_job")
def render_project_job(self, project_id: str):
    """
    创建 Job，构建 chord：
    1. 并行渲染所有 shots
    2. 最终合成整个项目
    """
    logger.info(f"Starting render job for project: {project_id}")
    job = Job(project_id)
    job.start()

    try:
        with Session(engine) as session:
            shots = session.exec(select(Shot)).all()
            shot_ids = [shot.shot_id for shot in shots]

        if not shot_ids:
            logger.warning(f"No shots found for project: {project_id}")
            job.complete()
            return {"project_id": project_id, "status": "completed", "shots": 0}

        logger.info(f"Found {len(shot_ids)} shots, building chord")

        from tasks.shots import render_shot

        workflow = chord(
            [render_shot.s(shot_id) for shot_id in shot_ids],
            compose_project.s(project_id),
        )
        result = workflow.apply_async()

        job.complete()
        logger.info(f"Render job dispatched for project: {project_id}, task_id: {result.id}")

        return {
            "project_id": project_id,
            "status": "dispatched",
            "shots": len(shot_ids),
            "chord_id": result.id,
        }

    except Exception as e:
        job.fail(str(e))
        logger.error(f"Render job failed for project {project_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.jobs.compose_project")
def compose_project(self, shot_results: list, project_id: str):
    """
    最终合成：将所有渲染好的 shots 合并成完整视频
    """
    logger.info(f"Composing project: {project_id}")
    started_at = datetime.utcnow()

    try:
        successful_shots = [r for r in shot_results if r.get("status") == "completed"]
        failed_shots = [r for r in shot_results if r.get("status") != "completed"]

        if failed_shots:
            logger.warning(f"Some shots failed: {len(failed_shots)}/{len(shot_results)}")

        logger.info(f"Composing {len(successful_shots)} shots for project: {project_id}")

        # TODO: 实际的视频合成逻辑
        # 使用 moviepy 或其他工具合并视频片段

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()

        logger.info(f"Project {project_id} composed successfully in {duration:.2f}s")

        return {
            "project_id": project_id,
            "status": "completed",
            "total_shots": len(shot_results),
            "successful_shots": len(successful_shots),
            "failed_shots": len(failed_shots),
            "duration": duration,
        }

    except Exception as e:
        logger.error(f"Project composition failed for {project_id}: {e}")
        raise
