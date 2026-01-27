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


@celery_app.task(bind=True, name="tasks.jobs.render_project_job")
def render_project_job(self, project_id: str):
    """
    编排整个项目的渲染任务
    """
    logger.info(f"🎬 Dispatching render job for project: {project_id}")

    # 1. 更新 Job 状态
    with Session(engine) as session:
        job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

        # 2. 获取所有镜头
        shots = session.exec(select(Shot).where(Shot.project_id == project_id).order_by(Shot.sequence_order)).all()
        shot_ids = [shot.shot_id for shot in shots]

    if not shot_ids:
        logger.warning("No shots found!")
        return

    # 3. 构建 Chord (并行渲染 -> 串行合成)
    from tasks.shots import render_shot

    # 创建任务组
    header = [render_shot.s(sid) for sid in shot_ids]
    # 回调任务
    callback = compose_project.s(project_id)

    # 启动
    workflow = chord(header)(callback)
    logger.info(f"Workflow started. Chord ID: {workflow.id}")
    return {"chord_id": workflow.id}


@celery_app.task(bind=True, name="tasks.jobs.compose_project")
def compose_project(self, shot_results: List[Dict], project_id: str):
    """
    最终合成任务：收集所有 Shot 结果并拼接
    """
    logger.info(f"🎞️ Composing project: {project_id}")

    # 过滤掉失败的镜头
    valid_results = [r for r in shot_results if r and r.get("status") == "completed"]

    if not valid_results:
        logger.error("No valid shots to compose!")
        return {"status": "failed", "reason": "No valid shots"}

    # 按 sequence_order 排序 (假设 shot_results 顺序可能乱，最好根据 shot_id 或数据库重新查顺序)
    # 这里简单按 shot_id 排序作为演示
    valid_results.sort(key=lambda x: x["shot_id"])

    # 转换为 Editor 需要的 ShotArtifact 对象
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
        # 定义输出路径
        from config import settings
        output_dir = settings.OUTPUT_DIR
        output_filename = f"final_project_{project_id}.mp4"
        output_path = os.path.join(output_dir, output_filename)

        # 调用 Editor 进行拼接
        final_video_path = assemble_shots(
            shots=artifacts,
            output_path=output_path,
            alignment_strategy=AlignmentStrategy.LOOP,
            crossfade_duration=0.5
        )

        # 更新项目状态
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.DONE
                project.output_video_path = final_video_path
                session.add(project)

            # 更新 Job 状态
            job = session.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).first()
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.completed_at = datetime.utcnow()
                session.add(job)

            session.commit()

        logger.info(f"🎉 Project composition complete! Saved to: {final_video_path}")
        return {"status": "success", "path": final_video_path}

    except Exception as e:
        logger.error(f"Composition failed: {e}")
        # 更新失败状态...
        raise e