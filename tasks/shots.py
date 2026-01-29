import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from sqlmodel import Session

from core.database import engine
from core.models import Shot, ShotRender, ShotRenderStatus, Character, CharacterState
from core.pipeline import ShotPipeline
from core.editor import AlignmentStrategy
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "alloy"


def get_reference_image_for_shot(shot: Shot, session: Session) -> str | None:
    """
    根据镜头中的角色状态获取最合适的参考图
    
    优先级：
    1. 如果 shot.character_states 指定了角色状态 -> 使用 CharacterState 的参考图
    2. 否则使用 Character 表的默认参考图
    3. 如果都没有则返回 None
    
    Args:
        shot: 分镜数据
        session: 数据库会话
        
    Returns:
        参考图路径或 None
    """
    if not shot.characters_in_shot:
        return None
    
    # 取第一个角色作为主要参考
    first_character_id = shot.characters_in_shot[0]
    
    # 检查是否有指定的角色状态
    if shot.character_states and first_character_id in shot.character_states:
        state_id = shot.character_states[first_character_id]
        # 查询 CharacterState 表
        char_state = session.get(CharacterState, state_id)
        if char_state and char_state.reference_image_path:
            logger.debug(f"Using character state reference: {char_state.state_name}")
            return char_state.reference_image_path
    
    # 回退到角色默认参考图
    character = session.get(Character, first_character_id)
    if character and character.reference_image_path:
        import os
        if os.path.exists(character.reference_image_path):
            return character.reference_image_path
    
    return None


def get_voice_for_shot(shot: Shot, session: Session) -> str:
    """
    根据镜头中的角色获取合适的 voice_id
    
    逻辑：
    1. 检查 shot.characters_in_shot 列表
    2. 如果有对话角色，查询第一个角色的 voice_id
    3. 如果角色没有设置 voice_id，返回默认值 "alloy"
    4. 如果没有角色，返回默认值 "alloy"
    """
    if not shot.characters_in_shot:
        return DEFAULT_VOICE_ID
    
    first_character_id = shot.characters_in_shot[0]
    character = session.get(Character, first_character_id)
    
    if character and character.voice_id:
        return character.voice_id
    
    return DEFAULT_VOICE_ID


# 初始化全局流水线实例
# 这就是为什么代码可以变短：繁重的逻辑都封装在 ShotPipeline (core/pipeline.py) 里了
pipeline = ShotPipeline(
    enable_vlm_scoring=True,  # 开启 VLM 评分
    min_vlm_score=0.6  # 设置最低分要求
)


def update_render_status(
        render_id: str,
        status: ShotRenderStatus,
        progress: float = 0.0,
        result_paths: Dict[str, str] = None,
        error: str = None
):
    """更新数据库中的渲染状态"""
    try:
        with Session(engine) as session:
            render = session.get(ShotRender, render_id)
            if render:
                render.status = status
                render.progress = progress
                if result_paths:
                    if "video" in result_paths: render.video_path = result_paths["video"]
                    if "audio" in result_paths: render.audio_path = result_paths["audio"]
                    if "image" in result_paths: render.image_path = result_paths["image"]
                if error:
                    render.error_message = error
                render.updated_at = datetime.utcnow()
                session.add(render)
                session.commit()
    except Exception as e:
        logger.error(f"Failed to update render status: {e}")


@celery_app.task(bind=True, name="tasks.shots.render_shot",task_acks_late = False)
def render_shot(self, shot_id: int):
    """
    执行真正的镜头渲染流水线
    逻辑委托给 core.pipeline.ShotPipeline
    """
    logger.info(f"🚀 Starting full pipeline for shot: {shot_id}")
    start_time = datetime.utcnow()

    # 获取 Shot 信息
    with Session(engine) as session:
        shot = session.get(Shot, shot_id)
        # 获取关联的 Render 记录 ID
        render_record = session.query(ShotRender).filter(ShotRender.shot_id == shot_id).first()
        render_id = render_record.id if render_record else None
        
        # 动态获取 voice_id
        voice_id = get_voice_for_shot(shot, session) if shot else DEFAULT_VOICE_ID
        
        # 新增：获取角色状态参考图
        reference_image_path = get_reference_image_for_shot(shot, session) if shot else None

    if not shot:
        logger.error(f"Shot {shot_id} not found!")
        return {"status": "failed", "error": "Shot not found"}

    if render_id:
        update_render_status(render_id, ShotRenderStatus.GENERATING_IMAGE, 0.1)

    try:
        # 调用核心流水线 (Core Pipeline)
        # 这里会真正调用 Google Imagen, VLM, TTS 等模型
        logger.info(f"Processing shot {shot_id} via ShotPipeline...")

        artifact = pipeline.process_shot(
            shot_id=shot.shot_id,
            visual_prompt=shot.visual_prompt,
            dialogue=shot.dialogue,
            reference_image_path=reference_image_path,
            camera_movement=shot.camera_movement,
            voice_id=voice_id,
            target_duration=shot.duration,
            alignment_strategy=AlignmentStrategy.LOOP
        )

        # 记录结果
        result_paths = {
            "video": artifact.video_path,
            "audio": artifact.audio_path
        }

        if render_id:
            update_render_status(render_id, ShotRenderStatus.SUCCESS, 1.0, result_paths)

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"✅ Shot {shot_id} finished in {duration:.2f}s. Video: {artifact.video_path}")

        # 记录使用的厂家信息
        providers_info = {}
        if hasattr(pipeline.keyframe_generator, 'last_used_provider'):
            providers_info["image"] = pipeline.keyframe_generator.last_used_provider
        if hasattr(pipeline.video_generator, 'last_used_provider'):
            providers_info["video"] = pipeline.video_generator.last_used_provider

        # 返回结果给下一个任务
        return {
            "shot_id": shot_id,
            "status": "completed",
            "video_path": artifact.video_path,
            "audio_path": artifact.audio_path,
            "duration": artifact.duration,
            "dialogue": shot.dialogue,
            "providers_used": providers_info
        }

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        if render_id:
            update_render_status(render_id, ShotRenderStatus.FAILURE, error=str(e))
        raise e