import logging
import traceback
import os
from datetime import datetime
from typing import Dict, Any, Optional

from sqlmodel import Session

from core.database import engine
from core.models import Shot, ShotRender, ShotRenderStatus, Character, Job, JobStatus
from core.pipeline import ShotPipeline
from core.editor import AlignmentStrategy
from core.cache import cache, is_job_cancelled_cached
from core.lora_manager import lora_manager
from integrations.lipsync_client import LipSyncClientFactory, LipSyncRequest
from integrations.sfx_generator import sfx_generator, sfx_mixer, SFXLayer
from tasks.celery_app import celery_app
from api.websocket import publish_job_update_sync, publish_shot_render_update_sync

logger = logging.getLogger(__name__)

pipeline = ShotPipeline(
    enable_vlm_scoring=True,
    min_vlm_score=0.6
)


def is_job_cancelled(project_id: str) -> bool:
    """检查项目的渲染任务是否已被取消（使用缓存优化）。"""
    return is_job_cancelled_cached(project_id)


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
        error: str = None,
        project_id: str = None,
        job_id: str = None
):
    """更新数据库中的渲染状态，并发布 WebSocket 更新。"""
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

                # Publish WebSocket update
                if project_id and job_id:
                    publish_shot_render_update_sync(
                        render_id=render_id,
                        job_id=job_id,
                        project_id=project_id,
                        data={
                            "status": status.value if hasattr(status, 'value') else status,
                            "progress": progress,
                            "error_message": error,
                            "result_paths": result_paths,
                        }
                    )
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

        project_id = shot.project_id

        # Check if job was cancelled before starting
        if is_job_cancelled(project_id):
            logger.info(f"Shot {shot_id} skipped - job was cancelled")
            return {"status": "cancelled", "shot_id": shot_id}

        shot_data = {
            "shot_id": shot.shot_id,
            "visual_prompt": shot.visual_prompt,
            "dialogue": shot.dialogue,
            "camera_movement": shot.camera_movement,
            "duration": shot.duration,
            "project_id": project_id,
            "scene_description": shot.visual_prompt,  # 用于 SFX 提取
            "sfx_tags": getattr(shot, 'sfx_tags', None),  # 音效标签
            "characters_in_shot": shot.characters_in_shot,
        }

        reference_image_path = get_reference_image_for_shot(shot, session)

        render_record = session.query(ShotRender).filter(ShotRender.shot_id == shot_id).first()
        render_id = render_record.id if render_record else None
        job_id = render_record.job_id if render_record else None

        # Step 1: 获取角色 LoRA
        lora_url = None
        if shot.characters_in_shot:
            char_id = shot.characters_in_shot[0]
            active_lora = lora_manager.get_character_lora(char_id, session)
            if active_lora:
                lora_url = active_lora.lora_url
                logger.info(f"Using LoRA for character {char_id}: {lora_url}")

    if render_id:
        update_render_status(
            render_id, ShotRenderStatus.GENERATING_IMAGE, 0.1,
            project_id=project_id, job_id=job_id
        )

    try:
        logger.info(f"Processing shot {shot_id} via ShotPipeline...")

        # Step 2: 调用 Pipeline 生成视频和音频
        artifact = pipeline.process_shot(
            shot_id=shot_data["shot_id"],
            visual_prompt=shot_data["visual_prompt"],
            dialogue=shot_data["dialogue"],
            reference_image_path=reference_image_path,
            camera_movement=shot_data["camera_movement"],
            voice_id="alloy",
            target_duration=shot_data["duration"],
            alignment_strategy=AlignmentStrategy.LOOP,
            lora_url=lora_url  # 传递 LoRA URL
        )

        current_video = artifact.video_path
        current_audio = artifact.audio_path

        # Step 3: Lip-Sync 处理
        if shot_data["dialogue"] and current_video and current_audio:
            if render_id:
                update_render_status(
                    render_id, ShotRenderStatus.GENERATING_VIDEO, 0.7,
                    error="Lip-Syncing...",
                    project_id=project_id, job_id=job_id
                )
            try:
                logger.info(f"Applying lip-sync for shot {shot_id}...")
                client = LipSyncClientFactory.get_default_client()
                lip_sync_result = client.process(LipSyncRequest(
                    video_path=current_video,
                    audio_path=current_audio
                ))
                current_video = lip_sync_result.video_path
                logger.info(f"Lip-sync completed for shot {shot_id}")
            except Exception as e:
                logger.error(f"LipSync failed for shot {shot_id}: {e}")
                # 降级：使用原始视频，不中断流程

        # Step 4: SFX 音效处理
        sfx_tags = shot_data.get("sfx_tags")
        if sfx_tags:
            if render_id:
                update_render_status(
                    render_id, ShotRenderStatus.GENERATING_AUDIO, 0.9,
                    error="Generating SFX...",
                    project_id=project_id, job_id=job_id
                )
            try:
                logger.info(f"Generating SFX for shot {shot_id} with tags: {sfx_tags}")
                sfx_list = sfx_generator.generate_sfx_for_shot(
                    scene_description=shot_data["scene_description"],
                    shot_duration=artifact.duration,
                    sfx_tags=sfx_tags
                )
                if sfx_list and current_audio:
                    layers = [SFXLayer(audio_path=sfx.audio_path, volume=0.3) for sfx in sfx_list]
                    current_audio = sfx_mixer.mix_with_dialogue(current_audio, layers)
                    logger.info(f"SFX mixed for shot {shot_id}")
            except Exception as e:
                logger.error(f"SFX generation failed for shot {shot_id}: {e}")
                # 降级：使用原始音频，不中断流程

        # Step 5: 最终结果
        result_paths = {
            "video": current_video,
            "audio": current_audio
        }

        if render_id:
            update_render_status(
                render_id, ShotRenderStatus.SUCCESS, 1.0, result_paths,
                project_id=project_id, job_id=job_id
            )

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Shot {shot_id} finished in {duration:.2f}s. Video: {current_video}")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "video_path": current_video,
            "audio_path": current_audio,
            "duration": artifact.duration,
            "dialogue": shot_data["dialogue"]
        }

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        if render_id:
            update_render_status(
                render_id, ShotRenderStatus.FAILURE, error=str(e),
                project_id=project_id, job_id=job_id
            )
        raise e
