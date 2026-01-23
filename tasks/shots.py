import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from core.database import engine
from core.models import Shot
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def update_shot_status(
    shot_id: int,
    status: str,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    error: Optional[str] = None,
):
    """更新 shot 状态到数据库（辅助函数）"""
    logger.info(f"Shot {shot_id} status: {status}")
    # 注意：当前 Shot 模型没有 status 字段
    # 实际项目中需要扩展模型或使用单独的状态表


@celery_app.task(bind=True, name="tasks.shots.generate_keyframes")
def generate_keyframes(self, shot_id: int, k: int = 4):
    """
    生成关键帧
    :param shot_id: 镜头 ID
    :param k: 生成的关键帧数量
    """
    logger.info(f"Generating {k} keyframes for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "generating_keyframes", started_at=started_at)

    try:
        with Session(engine) as session:
            shot = session.get(Shot, shot_id)
            if not shot:
                raise ValueError(f"Shot {shot_id} not found")

            # TODO: 调用图像生成 API
            # 使用 shot.visual_prompt 生成关键帧
            keyframes = [f"keyframe_{shot_id}_{i}.png" for i in range(k)]

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "keyframes_generated", finished_at=finished_at)

        logger.info(f"Generated {k} keyframes for shot {shot_id} in {duration:.2f}s")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "keyframes": keyframes,
            "duration": duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "keyframes_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Keyframe generation failed for shot {shot_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.shots.score_keyframes")
def score_keyframes(self, shot_id: int):
    """
    VLM 评分关键帧（可选）
    """
    logger.info(f"Scoring keyframes for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "scoring_keyframes", started_at=started_at)

    try:
        # TODO: 调用 VLM API 评分关键帧
        # 选择最佳关键帧用于视频生成
        scores = {"keyframe_0": 0.95, "keyframe_1": 0.85, "keyframe_2": 0.90, "keyframe_3": 0.88}
        best_keyframe = max(scores, key=scores.get)

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "keyframes_scored", finished_at=finished_at)

        logger.info(f"Scored keyframes for shot {shot_id}, best: {best_keyframe}")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "scores": scores,
            "best_keyframe": best_keyframe,
            "duration": duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "scoring_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Keyframe scoring failed for shot {shot_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.shots.generate_video")
def generate_video(self, shot_id: int):
    """
    I2V: 从关键帧生成视频
    """
    logger.info(f"Generating video for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "generating_video", started_at=started_at)

    try:
        with Session(engine) as session:
            shot = session.get(Shot, shot_id)
            if not shot:
                raise ValueError(f"Shot {shot_id} not found")

            # TODO: 调用 I2V API
            # 使用最佳关键帧生成视频
            video_path = f"output/shot_{shot_id}_video.mp4"

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "video_generated", finished_at=finished_at)

        logger.info(f"Generated video for shot {shot_id} in {duration:.2f}s")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "video_path": video_path,
            "duration": duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "video_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Video generation failed for shot {shot_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.shots.generate_audio")
def generate_audio(self, shot_id: int):
    """
    TTS: 生成对话音频
    """
    logger.info(f"Generating audio for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "generating_audio", started_at=started_at)

    try:
        with Session(engine) as session:
            shot = session.get(Shot, shot_id)
            if not shot:
                raise ValueError(f"Shot {shot_id} not found")

            if not shot.dialogue:
                logger.info(f"No dialogue for shot {shot_id}, skipping audio")
                return {
                    "shot_id": shot_id,
                    "status": "skipped",
                    "audio_path": None,
                    "duration": 0,
                }

            # TODO: 调用 TTS API
            # 使用 shot.dialogue 生成音频
            audio_path = f"output/shot_{shot_id}_audio.wav"

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "audio_generated", finished_at=finished_at)

        logger.info(f"Generated audio for shot {shot_id} in {duration:.2f}s")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "audio_path": audio_path,
            "duration": duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "audio_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Audio generation failed for shot {shot_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.shots.align_shot")
def align_shot(self, shot_id: int):
    """
    音视频对齐
    """
    logger.info(f"Aligning audio/video for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "aligning", started_at=started_at)

    try:
        # TODO: 使用 moviepy 或其他工具对齐音视频
        # 调整视频时长以匹配音频，或反之
        aligned_path = f"output/shot_{shot_id}_aligned.mp4"

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "aligned", finished_at=finished_at)

        logger.info(f"Aligned shot {shot_id} in {duration:.2f}s")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "aligned_path": aligned_path,
            "duration": duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "align_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Shot alignment failed for shot {shot_id}: {e}")
        raise


@celery_app.task(bind=True, name="tasks.shots.render_shot")
def render_shot(self, shot_id: int):
    """
    串行执行完整的单镜头渲染流程：
    1. generate_keyframes
    2. score_keyframes (可选)
    3. generate_video
    4. generate_audio
    5. align_shot
    """
    logger.info(f"Starting full render pipeline for shot: {shot_id}")
    started_at = datetime.utcnow()
    update_shot_status(shot_id, "rendering", started_at=started_at)

    results = {}

    try:
        # Step 1: 生成关键帧
        keyframe_result = generate_keyframes(shot_id, k=4)
        results["keyframes"] = keyframe_result

        # Step 2: 评分关键帧（可选）
        score_result = score_keyframes(shot_id)
        results["scores"] = score_result

        # Step 3: 生成视频
        video_result = generate_video(shot_id)
        results["video"] = video_result

        # Step 4: 生成音频
        audio_result = generate_audio(shot_id)
        results["audio"] = audio_result

        # Step 5: 音视频对齐
        align_result = align_shot(shot_id)
        results["align"] = align_result

        finished_at = datetime.utcnow()
        total_duration = (finished_at - started_at).total_seconds()
        update_shot_status(shot_id, "render_completed", finished_at=finished_at)

        logger.info(f"Completed full render for shot {shot_id} in {total_duration:.2f}s")

        return {
            "shot_id": shot_id,
            "status": "completed",
            "results": results,
            "total_duration": total_duration,
        }

    except Exception as e:
        update_shot_status(shot_id, "render_failed", finished_at=datetime.utcnow(), error=str(e))
        logger.error(f"Full render failed for shot {shot_id}: {e}")
        raise
