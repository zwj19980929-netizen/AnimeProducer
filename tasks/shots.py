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
from core.critic import get_video_critic, VideoReview
from integrations.lipsync_client import LipSyncClientFactory, LipSyncRequest
from integrations.sfx_generator import sfx_generator, sfx_mixer, SFXLayer
from tasks.celery_app import celery_app
from api.websocket import publish_job_update_sync, publish_shot_render_update_sync
from config import settings

logger = logging.getLogger(__name__)

# 从配置读取 Critic 相关设置
CRITIC_ENABLED = getattr(settings, 'CRITIC_ENABLED', True)
CRITIC_MIN_SCORE = getattr(settings, 'CRITIC_MIN_SCORE', 8)
CRITIC_MAX_RETRIES = getattr(settings, 'CRITIC_MAX_RETRIES', 2)

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


def get_previous_shot_last_frame(current_shot: Shot, session: Session) -> Optional[str]:
    """
    获取同一场景下，前一个镜头的最后一帧路径。

    用于空间连贯性：将上一镜头的最后一帧作为当前镜头的首帧参考，
    保持同一场景内的光影、位置连贯性。

    注意：此功能要求同一场景内的镜头按顺序渲染（串行）。
    如果使用并行渲染，前一个镜头可能尚未完成，此时会返回 None。
    建议在任务调度时实现"混合调度"：不同场景并行，同一场景串行。

    Args:
        current_shot: 当前镜头
        session: 数据库会话

    Returns:
        上一镜头最后一帧的路径（OSS URL 或本地路径），如果不存在则返回 None
    """
    # 如果没有 scene_id，无法进行场景连贯性处理
    if not current_shot.scene_id:
        logger.debug(f"Shot {current_shot.shot_id} has no scene_id, skipping context lookup")
        return None

    # 查询同一场景下的前一个镜头
    prev_shot = session.query(Shot).filter(
        Shot.project_id == current_shot.project_id,
        Shot.scene_id == current_shot.scene_id,
        Shot.sequence_order == current_shot.sequence_order - 1
    ).first()

    if not prev_shot:
        logger.debug(
            f"No previous shot found for scene {current_shot.scene_id} "
            f"(current order={current_shot.sequence_order})"
        )
        return None

    # 查询前一个镜头的渲染结果
    prev_render = session.query(ShotRender).filter(
        ShotRender.shot_id == prev_shot.shot_id,
        ShotRender.status == ShotRenderStatus.SUCCESS
    ).first()

    if not prev_render or not prev_render.video_path:
        logger.info(
            f"Previous shot {prev_shot.shot_id} not rendered yet, "
            f"context continuity unavailable (parallel rendering?)"
        )
        return None

    # 从视频中提取最后一帧
    try:
        frame_path = extract_last_frame(prev_render.video_path, prev_shot.shot_id)
        logger.info(f"Extracted last frame from shot {prev_shot.shot_id}: {frame_path}")
        return frame_path
    except Exception as e:
        logger.warning(f"Failed to extract last frame from shot {prev_shot.shot_id}: {e}")
        return None


def extract_last_frame(video_path: str, shot_id: int) -> Optional[str]:
    """
    从视频中提取最后一帧。

    Args:
        video_path: 视频路径或 URL
        shot_id: 镜头 ID（用于命名）

    Returns:
        最后一帧的路径（OSS URL）
    """
    from moviepy import VideoFileClip
    import tempfile

    # 解析视频路径
    local_path = video_path
    temp_video_downloaded = False
    if video_path.startswith("http://") or video_path.startswith("https://"):
        from integrations.oss_service import OSSService
        local_path = OSSService.get_instance().download_to_temp(video_path)
        temp_video_downloaded = True

    clip = None
    temp_frame_path = None
    try:
        clip = VideoFileClip(local_path)

        # 提取最后一帧（稍微提前一点避免边界问题）
        temp_frame = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_frame.close()
        temp_frame_path = temp_frame.name

        last_time = max(0, clip.duration - 0.05)
        clip.save_frame(temp_frame_path, t=last_time)

        # 上传到 OSS
        from integrations.oss_service import is_oss_configured, require_oss
        if is_oss_configured():
            oss = require_oss()
            frame_url = oss.upload_file(temp_frame_path, folder="frames")
            return frame_url
        else:
            # 不清理临时文件，返回本地路径
            result_path = temp_frame_path
            temp_frame_path = None  # 防止 finally 中清理
            return result_path
    finally:
        if clip:
            clip.close()
        # 清理临时帧文件
        if temp_frame_path and os.path.exists(temp_frame_path):
            try:
                os.unlink(temp_frame_path)
            except Exception:
                pass
        # 清理下载的临时视频文件
        if temp_video_downloaded and local_path and os.path.exists(local_path):
            try:
                os.unlink(local_path)
            except Exception:
                pass


@celery_app.task(bind=True, name="tasks.shots.render_shot")
def render_shot(self, shot_id: int, job_id: str | None = None):
    """
    执行镜头渲染流水线。

    流程：
    1. 获取镜头数据和角色 LoRA
    2. 获取前一镜头的最后一帧（空间连贯性）
    3. 调用 Pipeline 生成视频和音频
    4. AI 影评人评分（如启用）
    5. 质量不达标则重绘视频（最多重试 CRITIC_MAX_RETRIES 次，音频不重复生成）
    6. Lip-Sync 处理
    7. SFX 音效处理
    8. 更新渲染状态
    """
    logger.info(f"Starting full pipeline for shot: {shot_id}")
    start_time = datetime.utcnow()

    with Session(engine) as session:
        shot = session.get(Shot, shot_id)
        if not shot:
            logger.error(f"Shot {shot_id} not found!")
            return {"status": "failed", "error": "Shot not found"}

        project_id = shot.project_id

        shot_data = {
            "shot_id": shot.shot_id,
            "visual_prompt": shot.visual_prompt,
            "dialogue": shot.dialogue,
            "camera_movement": shot.camera_movement,
            "duration": shot.duration,
            "project_id": project_id,
            "scene_description": shot.visual_prompt,
            "sfx_tags": getattr(shot, 'sfx_tags', None),
            "characters_in_shot": shot.characters_in_shot,
            "scene_id": getattr(shot, 'scene_id', None),
        }

        reference_image_path = get_reference_image_for_shot(shot, session)

        render_query = session.query(ShotRender).filter(ShotRender.shot_id == shot_id)
        if job_id:
            render_query = render_query.filter(ShotRender.job_id == job_id)
        render_record = render_query.first()
        render_id = render_record.id if render_record else None
        current_job_id = render_record.job_id if render_record else job_id

        # Check if job was cancelled before starting
        if current_job_id:
            job = session.get(Job, current_job_id)
            if job and job.status == JobStatus.REVOKED:
                logger.info(f"Shot {shot_id} skipped - job was cancelled: {current_job_id}")
                return {"status": "cancelled", "shot_id": shot_id}
        elif is_job_cancelled(project_id):
            logger.info(f"Shot {shot_id} skipped - project latest job was cancelled")
            return {"status": "cancelled", "shot_id": shot_id}

        # Step 1: 获取角色 LoRA
        lora_url = None
        if shot.characters_in_shot:
            char_id = shot.characters_in_shot[0]
            active_lora = lora_manager.get_character_lora(char_id, session)
            if active_lora:
                lora_url = active_lora.lora_url
                logger.info(f"Using LoRA for character {char_id}: {lora_url}")

        # Step 2: 获取前一镜头的最后一帧（空间连贯性）
        context_image = get_previous_shot_last_frame(shot, session)
        if context_image:
            logger.info(f"Using context image from previous shot: {context_image}")

    if render_id:
        update_render_status(
            render_id, ShotRenderStatus.GENERATING_IMAGE, 0.1,
            project_id=project_id, job_id=current_job_id
        )

    try:
        logger.info(f"Processing shot {shot_id} via ShotPipeline...")

        # Step 3: 首次调用 Pipeline 生成视频和音频
        current_prompt = shot_data["visual_prompt"]
        artifact = pipeline.process_shot(
            shot_id=shot_data["shot_id"],
            visual_prompt=current_prompt,
            dialogue=shot_data["dialogue"],
            reference_image_path=context_image or reference_image_path,
            camera_movement=shot_data["camera_movement"],
            voice_id="alloy",
            target_duration=shot_data["duration"],
            alignment_strategy=AlignmentStrategy.LOOP,
            lora_url=lora_url,
            scene_id=shot_data.get("scene_id"),
        )

        current_video = artifact.video_path
        current_audio = artifact.audio_path  # 音频只生成一次，后续重试不再生成

        # Step 4: AI 影评人评分（带重试循环）
        retry_count = 0
        while CRITIC_ENABLED and retry_count <= CRITIC_MAX_RETRIES:
            try:
                critic = get_video_critic()
                review = critic.evaluate_shot(
                    video_path=current_video,
                    original_prompt=current_prompt,
                    characters=shot_data.get("characters_in_shot"),
                )

                logger.info(
                    f"Critic Score: {review.score}/10 - "
                    f"has_glitches={review.has_glitches} - {review.feedback}"
                )

                # 质量达标，跳出循环
                if critic.is_acceptable(review):
                    logger.info(f"Shot {shot_id} passed quality check (score={review.score})")
                    break

                # Step 5: 质量不达标，准备重绘
                retry_count += 1
                if retry_count > CRITIC_MAX_RETRIES:
                    logger.warning(
                        f"Shot {shot_id} failed quality check after {CRITIC_MAX_RETRIES} retries, "
                        f"using last result (score={review.score})"
                    )
                    break

                logger.warning(
                    f"Quality check failed for shot {shot_id}. "
                    f"Retrying ({retry_count}/{CRITIC_MAX_RETRIES})..."
                )

                # 动态修正 Prompt
                if review.feedback:
                    current_prompt = f"{shot_data['visual_prompt']}, {review.feedback}"
                    logger.info(f"Enhanced prompt: {current_prompt[:100]}...")

                if render_id:
                    update_render_status(
                        render_id, ShotRenderStatus.GENERATING_IMAGE, 0.1 + (retry_count * 0.1),
                        error=f"Re-generating (attempt {retry_count + 1})...",
                        project_id=project_id, job_id=current_job_id
                    )

                # 重新生成视频（不重新生成音频）
                # 使用 enable_lipsync=False 因为 Lip-Sync 会在后面统一处理
                retry_artifact = pipeline.process_shot(
                    shot_id=shot_data["shot_id"],
                    visual_prompt=current_prompt,
                    dialogue=None,  # 不传对白，避免重新生成音频
                    reference_image_path=context_image or reference_image_path,
                    camera_movement=shot_data["camera_movement"],
                    voice_id="alloy",
                    target_duration=shot_data["duration"],
                    alignment_strategy=AlignmentStrategy.LOOP,
                    lora_url=lora_url,
                    scene_id=shot_data.get("scene_id"),
                    enable_lipsync=False,
                )
                current_video = retry_artifact.video_path

            except Exception as e:
                logger.error(f"Critic evaluation failed: {e}")
                # 评估失败时继续使用当前结果
                break

        # Step 6: Lip-Sync 处理
        if shot_data["dialogue"] and current_video and current_audio:
            if render_id:
                update_render_status(
                    render_id, ShotRenderStatus.GENERATING_VIDEO, 0.7,
                    error="Lip-Syncing...",
                    project_id=project_id, job_id=current_job_id
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

        # Step 7: SFX 音效处理
        sfx_tags = shot_data.get("sfx_tags")
        if sfx_tags:
            if render_id:
                update_render_status(
                    render_id, ShotRenderStatus.GENERATING_AUDIO, 0.9,
                    error="Generating SFX...",
                    project_id=project_id, job_id=current_job_id
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

        # Step 8: 最终结果
        result_paths = {
            "video": current_video,
            "audio": current_audio
        }

        if render_id:
            update_render_status(
                render_id, ShotRenderStatus.SUCCESS, 1.0, result_paths,
                project_id=project_id, job_id=current_job_id
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
                project_id=project_id, job_id=current_job_id
            )
        raise e
