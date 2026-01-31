import logging
import traceback
import os
from datetime import datetime
from typing import Dict, Any, Optional

from sqlmodel import Session

from core.database import engine
from core.models import Shot, ShotRender, ShotRenderStatus, Character
from core.pipeline import ShotPipeline
from core.editor import AlignmentStrategy
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

pipeline = ShotPipeline(
    enable_vlm_scoring=True,
    min_vlm_score=0.6
)


def get_reference_image_for_shot(shot: Shot, session: Session) -> Optional[str]:
    """获取镜头中角色的参考图片路径。"""
    if not shot.characters_in_shot:
        return None

    first_character_id = shot.characters_in_shot[0]
    character = session.get(Character, first_character_id)

    if character and character.reference_image_path:
        if os.path.exists(character.reference_image_path):
            return character.reference_image_path

    return None


def update_render_status(
        render_id: str,
        status: ShotRenderStatus,
        progress: float = 0.0,
        result_paths: Dict[str, str] = None,
        error: str = None
):
    """更新数据库中的渲染状态。"""
    try:
        with Session(engine) as session:
            render = session.get(ShotRender, render_id)
            if render:
                render.status = status
                render.progress = progress
                if result_paths:
                    if "video" in result_paths:
                        render.video_path = result_paths["video"]
                    if "audio" in result_paths:
                        render.audio_path = result_paths["audio"]
                    if "image" in result_paths:
                        render.image_path = result_paths["image"]
                if error:
                    render.error_message = error
                render.updated_at = datetime.utcnow()
                session.add(render)
                session.commit()
    except Exception as e:
        logger.error(f"Failed to update render status: {e}")


@celery_app.task(bind=True, name="tasks.shots.render_shot")
def render_shot(self, shot_id: int):
    """执行镜头渲染流水线。"""
    logger.info(f"Starting full pipeline for shot: {shot_id}")
    start_time = datetime.utcnow()

    with Session(engine) as session:
        shot = session.get(Shot, shot_id)
        if not shot:
            logger.error(f"Shot {shot_id} not found!")
            return {"status": "failed", "error": "Shot not found"}

        shot_data = {
            "shot_id": shot.shot_id,
            "visual_prompt": shot.visual_prompt,
            "dialogue": shot.dialogue,
            "camera_movement": shot.camera_movement,
            "duration": shot.duration,
            "project_id": shot.project_id,
        }

        reference_image_path = get_reference_image_for_shot(shot, session)

        render_record = session.query(ShotRender).filter(ShotRender.shot_id == shot_id).first()
        render_id = render_record.id if render_record else None

    if render_id:
        update_render_status(render_id, ShotRenderStatus.GENERATING_IMAGE, 0.1)

    try:
        logger.info(f"Processing shot {shot_id} via ShotPipeline...")

        artifact = pipeline.process_shot(
            shot_id=shot_data["shot_id"],
            visual_prompt=shot_data["visual_prompt"],
            dialogue=shot_data["dialogue"],
            reference_image_path=reference_image_path,
            camera_movement=shot_data["camera_movement"],
            voice_id="alloy",
            target_duration=shot_data["duration"],
            alignment_strategy=AlignmentStrategy.LOOP
        )

        result_paths = {
            "video": artifact.video_path,
            "audio": artifact.audio_path
        }

        if render_id:
            update_render_status(render_id, ShotRenderStatus.SUCCESS, 1.0, result_paths)

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Shot {shot_id} finished in {duration:.2f}s. Video: {artifact.video_path}")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "video_path": artifact.video_path,
            "audio_path": artifact.audio_path,
            "duration": artifact.duration,
            "dialogue": shot_data["dialogue"]
        }

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        if render_id:
            update_render_status(render_id, ShotRenderStatus.FAILURE, error=str(e))
        raise e