"""Celery tasks for character asset generation."""

import logging
from datetime import datetime
from typing import Optional, List

from sqlmodel import Session, select

from core.database import engine
from core.models import (
    Character,
    CharacterImage,
    CharacterImageType,
    CharacterLoRA,
    LoRATrainingStatus,
    Job,
    JobStatus,
    JobType,
)
from tasks.celery_app import celery_app
from api.websocket import publish_job_update_sync

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.assets.generate_character_images", max_retries=0)
def generate_character_images_task(
    self,
    job_id: str,
    character_id: str,
    project_id: str,
    num_candidates: int = 4,
    style_preset: str = "anime style",
    custom_prompt: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    seed: Optional[int] = None,
    image_provider: Optional[str] = None,
):
    """
    异步生成角色候选图片。

    逐张生成图片，每张完成后更新进度并通过 WebSocket 推送。

    Args:
        job_id: Job ID for tracking
        character_id: Character ID to generate images for
        project_id: Project ID
        num_candidates: Number of candidate images to generate
        style_preset: Style preset for generation
        custom_prompt: Optional custom prompt to append
        negative_prompt: Optional negative prompt
        seed: Optional random seed
        image_provider: Optional image provider (google, aliyun)
    """
    provider_info = f", provider={image_provider}" if image_provider else ""
    logger.info(f"Starting character image generation task for {character_id}, job_id={job_id}{provider_info}")

    # 更新 Job 状态为 STARTED
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": 0.0,
                "message": f"开始生成角色图片...{' (使用 ' + image_provider + ')' if image_provider else ''}",
            })

    # 获取角色信息（单独的 session，提取需要的数据）
    with Session(engine) as session:
        character = session.get(Character, character_id)
        if not character:
            _fail_job(job_id, project_id, f"Character not found: {character_id}")
            return {"status": "failed", "error": f"Character not found: {character_id}"}

        # 提取需要的数据，避免 detached 对象问题
        base_prompt = character.appearance_prompt or character.prompt_base or character.name

    # 构建完整的 prompt
    if custom_prompt:
        full_prompt = f"{base_prompt}, {custom_prompt}"
    else:
        full_prompt = base_prompt

    # 导入必要的模块
    from integrations.provider_factory import ProviderFactory
    from integrations.oss_service import is_oss_configured, OSSService

    use_oss = is_oss_configured()
    # 使用指定的 provider 或默认 provider
    image_client = ProviderFactory.get_image_client(image_provider)
    actual_provider = image_provider or "default"

    generated_images = []
    failed_count = 0

    for i in range(num_candidates):
        # 检查任务是否被取消
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job and job.status == JobStatus.REVOKED:
                logger.info(f"Job {job_id} was cancelled, stopping generation")
                # 推送取消通知
                publish_job_update_sync(job_id, project_id, {
                    "status": JobStatus.REVOKED.value,
                    "progress": i / num_candidates,
                    "message": "生成任务已取消",
                    "generated_count": len(generated_images),
                })
                return {"status": "cancelled", "generated": len(generated_images)}

        current_seed = (seed + i) if seed is not None else int(datetime.now().timestamp() * 1000) + i
        progress = i / num_candidates

        # 推送进度更新
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.STARTED.value,
            "progress": progress,
            "message": f"正在生成第 {i + 1}/{num_candidates} 张图片...",
            "current_image": i + 1,
            "total_images": num_candidates,
        })

        try:
            # 生成图片
            generation_prompt = f"{full_prompt}, {style_preset}, character reference sheet, best quality"
            image_bytes = image_client.generate_image(
                generation_prompt,
                style_preset=style_preset,
                negative_prompt=negative_prompt,
                seed=current_seed,
            )

            if not image_bytes:
                logger.warning(f"Failed to generate image {i + 1}")
                failed_count += 1
                continue

            # 保存图片
            image_path = None
            image_url = None

            if use_oss:
                oss = OSSService.get_instance()
                filename = f"char_{character_id}_candidate_{i+1}_seed{current_seed}"
                image_url = oss.upload_image_bytes(image_bytes, filename=filename)
                logger.info(f"Image {i + 1} uploaded to OSS: {image_url}")
            else:
                # 保存到本地
                from pathlib import Path
                from config import settings

                assets_dir = Path(settings.ASSETS_DIR)
                character_dir = assets_dir / "projects" / project_id / "characters" / character_id
                character_dir.mkdir(parents=True, exist_ok=True)

                image_path = str(character_dir / f"candidate_{i+1}_seed{current_seed}.png")
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Image {i + 1} saved to: {image_path}")

            # 存入数据库
            with Session(engine) as session:
                image = CharacterImage(
                    character_id=character_id,
                    image_type=CharacterImageType.CANDIDATE,
                    image_path=image_path,
                    image_url=image_url,
                    prompt=generation_prompt,
                    style_preset=style_preset,
                    generation_metadata={
                        "custom_prompt": custom_prompt,
                        "negative_prompt": negative_prompt,
                        "seed": current_seed,
                        "job_id": job_id,
                    }
                )
                session.add(image)
                session.commit()
                session.refresh(image)

                image_data = {
                    "id": image.id,
                    "character_id": image.character_id,
                    "image_type": image.image_type.value,
                    "image_path": image.image_path,
                    "image_url": image.image_url,
                    "prompt": image.prompt,
                    "style_preset": image.style_preset,
                    "is_selected_for_training": image.is_selected_for_training,
                    "is_anchor": image.is_anchor,
                    "created_at": image.created_at.isoformat(),
                }
                generated_images.append(image_data)

            # 推送单张图片完成的更新
            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": (i + 1) / num_candidates,
                "message": f"第 {i + 1}/{num_candidates} 张图片生成完成",
                "current_image": i + 1,
                "total_images": num_candidates,
                "image_generated": image_data,
            })

        except Exception as e:
            logger.error(f"Error generating image {i + 1}: {e}")
            failed_count += 1
            continue

    # 完成任务
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            if len(generated_images) > 0:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.result = {
                    "generated_count": len(generated_images),
                    "failed_count": failed_count,
                    "images": generated_images,
                }
            else:
                job.status = JobStatus.FAILURE
                job.error_message = "All image generations failed"
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()

    # 推送最终状态
    if len(generated_images) > 0:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.SUCCESS.value,
            "progress": 1.0,
            "message": f"生成完成，共 {len(generated_images)} 张图片",
            "result": {
                "generated_count": len(generated_images),
                "failed_count": failed_count,
                "images": generated_images,
            },
        })
    else:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.FAILURE.value,
            "error_message": "All image generations failed",
        })

    logger.info(f"Character image generation completed: {len(generated_images)} images, {failed_count} failed")
    return {
        "status": "success" if generated_images else "failed",
        "generated_count": len(generated_images),
        "failed_count": failed_count,
        "images": generated_images,
    }


def _fail_job(job_id: str, project_id: str, error_message: str):
    """Helper to mark a job as failed."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILURE
            job.error_message = error_message
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()

    publish_job_update_sync(job_id, project_id, {
        "status": JobStatus.FAILURE.value,
        "error_message": error_message,
    })


@celery_app.task(bind=True, name="tasks.assets.generate_character_variants", max_retries=0)
def generate_character_variants_task(
    self,
    job_id: str,
    character_id: str,
    project_id: str,
    num_images: int = 1,
    style_preset: str = "anime style",
    pose: Optional[str] = None,
    expression: Optional[str] = None,
    angle: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    seed: Optional[int] = None,
    image_provider: Optional[str] = None,
):
    """
    异步生成角色变体图片（不同姿态/表情/角度）。

    Args:
        job_id: Job ID for tracking
        character_id: Character ID to generate images for
        project_id: Project ID
        num_images: Number of images to generate
        style_preset: Style preset for generation
        pose: Pose description
        expression: Expression description
        angle: Angle description
        custom_prompt: Optional custom prompt to append
        negative_prompt: Optional negative prompt
        seed: Optional random seed
        image_provider: Optional image provider (google, aliyun)
    """
    provider_info = f", provider={image_provider}" if image_provider else ""
    logger.info(f"Starting character variant generation task for {character_id}, job_id={job_id}{provider_info}")

    # 更新 Job 状态为 STARTED
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": 0.0,
                "message": f"开始生成变体图片...{' (使用 ' + image_provider + ')' if image_provider else ''}",
            })

    # 获取角色信息
    with Session(engine) as session:
        character = session.get(Character, character_id)
        if not character:
            _fail_job(job_id, project_id, f"Character not found: {character_id}")
            return {"status": "failed", "error": f"Character not found: {character_id}"}

        # 检查是否有锚定图
        if not character.anchor_image_path and not character.anchor_image_url:
            _fail_job(job_id, project_id, "Please set an anchor image first before generating variants.")
            return {"status": "failed", "error": "No anchor image set"}

        # 提取需要的数据
        base_prompt = character.appearance_prompt or character.prompt_base or character.name
        anchor_image = character.anchor_image_path or character.anchor_image_url

    # 构建变体 prompt - 让表情/姿态/角度更突出
    # 表情放在最前面，权重最高
    variant_parts = []

    # 表情描述 - 使用更强烈的描述词
    expression_emphasis = {
        "neutral": "calm neutral expression, relaxed face",
        "smiling": "bright smile, happy smiling face, cheerful expression",
        "laughing": "laughing out loud, wide open mouth laughing, very happy joyful expression",
        "serious": "serious stern expression, focused determined face",
        "surprised": "shocked surprised expression, wide eyes open mouth, astonished face",
        "thinking": "thoughtful thinking expression, contemplative face, pondering",
        "sad": "sad melancholy expression, sorrowful face, downcast eyes",
        "angry": "angry furious expression, frowning face, intense glare",
        "shy": "shy bashful expression, blushing face, looking away embarrassed",
        "happy": "happy joyful expression, bright cheerful face",
    }

    # 角度描述 - 使用更明确的摄影术语
    angle_emphasis = {
        "front view": "front facing view, looking straight at camera, frontal portrait",
        "side view": "side profile view, 90 degree side angle, profile portrait",
        "three-quarter view": "three quarter view, 45 degree angle, dynamic angle portrait",
        "low angle": "low angle shot, looking up at subject, worm's eye view",
        "high angle": "high angle shot, looking down at subject, bird's eye view",
        "back view": "back view, from behind, rear view",
    }

    # 姿态描述
    pose_emphasis = {
        "standing": "standing upright, full body standing pose",
        "sitting": "sitting down, seated pose",
        "walking": "walking, mid-stride walking pose",
        "running": "running, dynamic running pose",
        "arms crossed": "arms crossed over chest, confident pose",
        "hands on hips": "hands on hips, assertive pose",
        "waving": "waving hand, friendly greeting pose",
        "fighting stance": "fighting stance, combat ready pose",
    }

    if expression:
        expr_desc = expression_emphasis.get(expression, f"{expression} expression, {expression} face")
        variant_parts.append(expr_desc)

    if angle:
        angle_desc = angle_emphasis.get(angle, angle)
        variant_parts.append(angle_desc)

    if pose:
        pose_desc = pose_emphasis.get(pose, f"{pose} pose")
        variant_parts.append(pose_desc)

    if custom_prompt:
        variant_parts.append(custom_prompt)

    variant_desc = ", ".join(variant_parts) if variant_parts else "portrait"
    full_prompt = f"{base_prompt}, {variant_desc}"

    # 导入必要的模块
    from integrations.provider_factory import ProviderFactory
    from integrations.oss_service import is_oss_configured, OSSService

    use_oss = is_oss_configured()
    image_client = ProviderFactory.get_image_client(image_provider)

    generated_images = []
    failed_count = 0

    for i in range(num_images):
        # 检查任务是否被取消
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job and job.status == JobStatus.REVOKED:
                logger.info(f"Job {job_id} was cancelled, stopping generation")
                publish_job_update_sync(job_id, project_id, {
                    "status": JobStatus.REVOKED.value,
                    "progress": i / num_images,
                    "message": "生成任务已取消",
                    "generated_count": len(generated_images),
                })
                return {"status": "cancelled", "generated": len(generated_images)}

        current_seed = (seed + i) if seed is not None else int(datetime.now().timestamp() * 1000) + i
        progress = i / num_images

        # 推送进度更新
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.STARTED.value,
            "progress": progress,
            "message": f"正在生成第 {i + 1}/{num_images} 张变体图...",
            "current_image": i + 1,
            "total_images": num_images,
        })

        try:
            # 生成图片
            generation_prompt = f"{full_prompt}, {style_preset}, best quality"
            image_bytes = image_client.generate_image(
                generation_prompt,
                reference_image_path=anchor_image if not anchor_image.startswith('http') else None,
                style_preset=style_preset,
                negative_prompt=negative_prompt,
                seed=current_seed,
            )

            if not image_bytes:
                logger.warning(f"Failed to generate variant image {i + 1}")
                failed_count += 1
                continue

            # 保存图片
            image_path = None
            image_url = None

            if use_oss:
                oss = OSSService.get_instance()
                filename = f"char_{character_id}_variant_{i+1}_seed{current_seed}"
                image_url = oss.upload_image_bytes(image_bytes, filename=filename)
                logger.info(f"Variant image {i + 1} uploaded to OSS: {image_url}")
            else:
                from pathlib import Path
                from config import settings

                assets_dir = Path(settings.ASSETS_DIR)
                character_dir = assets_dir / "projects" / project_id / "characters" / character_id
                character_dir.mkdir(parents=True, exist_ok=True)

                image_path = str(character_dir / f"variant_{i+1}_seed{current_seed}.png")
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Variant image {i + 1} saved to: {image_path}")

            # 存入数据库
            with Session(engine) as session:
                image = CharacterImage(
                    character_id=character_id,
                    image_type=CharacterImageType.VARIANT,
                    image_path=image_path,
                    image_url=image_url,
                    prompt=generation_prompt,
                    pose=pose,
                    expression=expression,
                    angle=angle,
                    style_preset=style_preset,
                    generation_metadata={
                        "custom_prompt": custom_prompt,
                        "anchor_image": anchor_image,
                        "negative_prompt": negative_prompt,
                        "seed": current_seed,
                        "job_id": job_id,
                    }
                )
                session.add(image)
                session.commit()
                session.refresh(image)

                image_data = {
                    "id": image.id,
                    "character_id": image.character_id,
                    "image_type": image.image_type.value,
                    "image_path": image.image_path,
                    "image_url": image.image_url,
                    "prompt": image.prompt,
                    "pose": image.pose,
                    "expression": image.expression,
                    "angle": image.angle,
                    "style_preset": image.style_preset,
                    "is_selected_for_training": image.is_selected_for_training,
                    "is_anchor": image.is_anchor,
                    "created_at": image.created_at.isoformat(),
                }
                generated_images.append(image_data)

            # 推送单张图片完成的更新
            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": (i + 1) / num_images,
                "message": f"第 {i + 1}/{num_images} 张变体图生成完成",
                "current_image": i + 1,
                "total_images": num_images,
                "image_generated": image_data,
            })

        except Exception as e:
            logger.error(f"Error generating variant image {i + 1}: {e}")
            failed_count += 1
            continue

    # 完成任务
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            if len(generated_images) > 0:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.result = {
                    "generated_count": len(generated_images),
                    "failed_count": failed_count,
                    "images": generated_images,
                }
            else:
                job.status = JobStatus.FAILURE
                job.error_message = "All variant image generations failed"
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()

    # 推送最终状态
    if len(generated_images) > 0:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.SUCCESS.value,
            "progress": 1.0,
            "message": f"变体图生成完成，共 {len(generated_images)} 张图片",
            "result": {
                "generated_count": len(generated_images),
                "failed_count": failed_count,
                "images": generated_images,
            },
        })
    else:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.FAILURE.value,
            "error_message": "All variant image generations failed",
        })

    logger.info(f"Character variant generation completed: {len(generated_images)} images, {failed_count} failed")
    return {
        "status": "success" if generated_images else "failed",
        "generated_count": len(generated_images),
        "failed_count": failed_count,
        "images": generated_images,
    }


@celery_app.task(bind=True, name="tasks.assets.batch_generate_character_variants", max_retries=0)
def batch_generate_character_variants_task(
    self,
    job_id: str,
    character_id: str,
    project_id: str,
    variants: list[dict],
    style_preset: str = "anime style",
    negative_prompt: Optional[str] = None,
    image_provider: Optional[str] = None,
):
    """
    异步批量生成角色变体图片（多种姿态/表情/角度组合）。

    Args:
        job_id: Job ID for tracking
        character_id: Character ID to generate images for
        project_id: Project ID
        variants: List of variant configs, each with pose/expression/angle/custom_prompt
        style_preset: Style preset for generation
        negative_prompt: Optional negative prompt
        image_provider: Optional image provider (google, aliyun)
    """
    provider_info = f", provider={image_provider}" if image_provider else ""
    logger.info(f"Starting batch variant generation for {character_id}, job_id={job_id}, {len(variants)} variants{provider_info}")

    # 更新 Job 状态为 STARTED
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": 0.0,
                "message": f"开始批量生成 {len(variants)} 张变体图...{' (使用 ' + image_provider + ')' if image_provider else ''}",
            })

    # 获取角色信息
    with Session(engine) as session:
        character = session.get(Character, character_id)
        if not character:
            _fail_job(job_id, project_id, f"Character not found: {character_id}")
            return {"status": "failed", "error": f"Character not found: {character_id}"}

        if not character.anchor_image_path and not character.anchor_image_url:
            _fail_job(job_id, project_id, "Please set an anchor image first before generating variants.")
            return {"status": "failed", "error": "No anchor image set"}

        base_prompt = character.appearance_prompt or character.prompt_base or character.name
        anchor_image = character.anchor_image_path or character.anchor_image_url

    # 导入必要的模块
    from integrations.provider_factory import ProviderFactory
    from integrations.oss_service import is_oss_configured, OSSService

    use_oss = is_oss_configured()
    image_client = ProviderFactory.get_image_client(image_provider)

    generated_images = []
    failed_count = 0
    total_variants = len(variants)

    for i, variant in enumerate(variants):
        # 检查任务是否被取消
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job and job.status == JobStatus.REVOKED:
                logger.info(f"Job {job_id} was cancelled, stopping generation")
                publish_job_update_sync(job_id, project_id, {
                    "status": JobStatus.REVOKED.value,
                    "progress": i / total_variants,
                    "message": "生成任务已取消",
                    "generated_count": len(generated_images),
                })
                return {"status": "cancelled", "generated": len(generated_images)}

        pose = variant.get("pose", "")
        expression = variant.get("expression", "")
        angle = variant.get("angle", "")
        custom = variant.get("custom_prompt", "")

        # 表情描述 - 使用更强烈的描述词
        expression_emphasis = {
            "neutral": "calm neutral expression, relaxed face",
            "smiling": "bright smile, happy smiling face, cheerful expression",
            "laughing": "laughing out loud, wide open mouth laughing, very happy joyful expression",
            "serious": "serious stern expression, focused determined face",
            "surprised": "shocked surprised expression, wide eyes open mouth, astonished face",
            "thinking": "thoughtful thinking expression, contemplative face, pondering",
            "sad": "sad melancholy expression, sorrowful face, downcast eyes",
            "angry": "angry furious expression, frowning face, intense glare",
            "shy": "shy bashful expression, blushing face, looking away embarrassed",
            "happy": "happy joyful expression, bright cheerful face",
        }

        # 角度描述 - 使用更明确的摄影术语
        angle_emphasis = {
            "front view": "front facing view, looking straight at camera, frontal portrait",
            "side view": "side profile view, 90 degree side angle, profile portrait",
            "three-quarter view": "three quarter view, 45 degree angle, dynamic angle portrait",
            "low angle": "low angle shot, looking up at subject, worm's eye view",
            "high angle": "high angle shot, looking down at subject, bird's eye view",
            "back view": "back view, from behind, rear view",
        }

        # 姿态描述
        pose_emphasis = {
            "standing": "standing upright, full body standing pose",
            "sitting": "sitting down, seated pose",
            "walking": "walking, mid-stride walking pose",
            "running": "running, dynamic running pose",
            "arms crossed": "arms crossed over chest, confident pose",
            "hands on hips": "hands on hips, assertive pose",
            "waving": "waving hand, friendly greeting pose",
            "fighting stance": "fighting stance, combat ready pose",
        }

        # 构建 prompt - 表情放最前面权重最高
        variant_parts = []
        if expression:
            expr_desc = expression_emphasis.get(expression, f"{expression} expression, {expression} face")
            variant_parts.append(expr_desc)
        if angle:
            angle_desc = angle_emphasis.get(angle, angle)
            variant_parts.append(angle_desc)
        if pose:
            pose_desc = pose_emphasis.get(pose, f"{pose} pose")
            variant_parts.append(pose_desc)
        if custom:
            variant_parts.append(custom)

        variant_desc = ", ".join(variant_parts) if variant_parts else "portrait"
        full_prompt = f"{base_prompt}, {variant_desc}"

        current_seed = int(datetime.now().timestamp() * 1000) + i
        progress = i / total_variants

        # 推送进度更新
        variant_label = f"{pose or ''} {expression or ''} {angle or ''}".strip() or f"变体 {i+1}"
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.STARTED.value,
            "progress": progress,
            "message": f"正在生成第 {i + 1}/{total_variants} 张: {variant_label}",
            "current_image": i + 1,
            "total_images": total_variants,
        })

        try:
            generation_prompt = f"{full_prompt}, {style_preset}, best quality"
            image_bytes = image_client.generate_image(
                generation_prompt,
                reference_image_path=anchor_image if not anchor_image.startswith('http') else None,
                style_preset=style_preset,
                negative_prompt=negative_prompt,
                seed=current_seed,
            )

            if not image_bytes:
                logger.warning(f"Failed to generate batch variant image {i + 1}")
                failed_count += 1
                continue

            # 保存图片
            image_path = None
            image_url = None

            if use_oss:
                oss = OSSService.get_instance()
                filename = f"char_{character_id}_batch_{i+1}_seed{current_seed}"
                image_url = oss.upload_image_bytes(image_bytes, filename=filename)
                logger.info(f"Batch variant {i + 1} uploaded to OSS: {image_url}")
            else:
                from pathlib import Path
                from config import settings

                assets_dir = Path(settings.ASSETS_DIR)
                character_dir = assets_dir / "projects" / project_id / "characters" / character_id
                character_dir.mkdir(parents=True, exist_ok=True)

                image_path = str(character_dir / f"batch_{i+1}_seed{current_seed}.png")
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Batch variant {i + 1} saved to: {image_path}")

            # 存入数据库
            with Session(engine) as session:
                image = CharacterImage(
                    character_id=character_id,
                    image_type=CharacterImageType.VARIANT,
                    image_path=image_path,
                    image_url=image_url,
                    prompt=generation_prompt,
                    pose=pose or None,
                    expression=expression or None,
                    angle=angle or None,
                    style_preset=style_preset,
                    generation_metadata={
                        "batch_index": i,
                        "variant_config": variant,
                        "anchor_image": anchor_image,
                        "negative_prompt": negative_prompt,
                        "seed": current_seed,
                        "job_id": job_id,
                    }
                )
                session.add(image)
                session.commit()
                session.refresh(image)

                image_data = {
                    "id": image.id,
                    "character_id": image.character_id,
                    "image_type": image.image_type.value,
                    "image_path": image.image_path,
                    "image_url": image.image_url,
                    "prompt": image.prompt,
                    "pose": image.pose,
                    "expression": image.expression,
                    "angle": image.angle,
                    "style_preset": image.style_preset,
                    "is_selected_for_training": image.is_selected_for_training,
                    "is_anchor": image.is_anchor,
                    "created_at": image.created_at.isoformat(),
                }
                generated_images.append(image_data)

            # 推送单张图片完成的更新
            publish_job_update_sync(job_id, project_id, {
                "status": JobStatus.STARTED.value,
                "progress": (i + 1) / total_variants,
                "message": f"第 {i + 1}/{total_variants} 张生成完成: {variant_label}",
                "current_image": i + 1,
                "total_images": total_variants,
                "image_generated": image_data,
            })

        except Exception as e:
            logger.error(f"Error generating batch variant {i + 1}: {e}")
            failed_count += 1
            continue

    # 完成任务
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            if len(generated_images) > 0:
                job.status = JobStatus.SUCCESS
                job.progress = 1.0
                job.result = {
                    "generated_count": len(generated_images),
                    "failed_count": failed_count,
                    "images": generated_images,
                }
            else:
                job.status = JobStatus.FAILURE
                job.error_message = "All batch variant generations failed"
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()

    # 推送最终状态
    if len(generated_images) > 0:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.SUCCESS.value,
            "progress": 1.0,
            "message": f"批量生成完成，共 {len(generated_images)} 张图片",
            "result": {
                "generated_count": len(generated_images),
                "failed_count": failed_count,
                "images": generated_images,
            },
        })
    else:
        publish_job_update_sync(job_id, project_id, {
            "status": JobStatus.FAILURE.value,
            "error_message": "All batch variant generations failed",
        })

    logger.info(f"Batch variant generation completed: {len(generated_images)} images, {failed_count} failed")
    return {
        "status": "success" if generated_images else "failed",
        "generated_count": len(generated_images),
        "failed_count": failed_count,
        "images": generated_images,
    }


@celery_app.task(bind=True, name="tasks.assets.start_lora_training", max_retries=0)
def start_lora_training_task(
    self,
    job_id: str,
    lora_id: str,
    character_id: str,
    project_id: str,
    ancestor_image_path: Optional[str] = None,
    image_ids: Optional[List[str]] = None,
    use_selected_images: bool = True,
    num_dataset_images: int = 20,
    training_steps: int = 1000,
    provider: str = "fal",
):
    """
    异步启动 LoRA 训练流水线。

    流程：
    1. 收集训练图片
    2. 生成数据集（如果图片不足）
    3. 打包上传到 OSS
    4. 调用云端 API 启动训练
    5. 返回训练任务 ID，后续通过轮询获取进度

    Args:
        job_id: Job ID for tracking
        lora_id: LoRA record ID
        character_id: Character ID
        project_id: Project ID
        ancestor_image_path: 始祖图路径（可选）
        image_ids: 指定用于训练的图片 ID 列表
        use_selected_images: 是否使用标记为训练的图片
        num_dataset_images: 数据集图片数量
        training_steps: 训练步数
        provider: 训练提供商 (fal/replicate)
    """
    logger.info(f"Starting LoRA training task for character {character_id}, lora_id={lora_id}, job_id={job_id}")

    # 更新 Job 状态为 STARTED
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.STARTED
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

    def update_progress(progress: float, message: str, status: JobStatus = JobStatus.STARTED):
        """更新进度"""
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.progress = progress
                job.status = status
                session.add(job)
                session.commit()

            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.progress = progress
                session.add(lora)
                session.commit()

        publish_job_update_sync(job_id, project_id, {
            "status": status.value,
            "progress": progress,
            "message": message,
            "lora_id": lora_id,
        })

    try:
        # 阶段 1: 获取角色信息 (5%)
        update_progress(0.05, "正在获取角色信息...")

        with Session(engine) as session:
            character = session.get(Character, character_id)
            if not character:
                raise ValueError(f"Character not found: {character_id}")

            # 提取需要的数据
            character_name = character.name
            appearance_prompt = character.appearance_prompt or character.prompt_base or character.name
            anchor_image = character.anchor_image_url or character.anchor_image_path
            reference_image = character.reference_image_url or character.reference_image_path

        # 阶段 2: 收集训练图片 (10%)
        update_progress(0.10, "正在收集训练图片...")

        training_images = []
        with Session(engine) as session:
            # 如果指定了 image_ids
            if image_ids:
                for img_id in image_ids:
                    img = session.get(CharacterImage, img_id)
                    if img and img.character_id == character_id:
                        training_images.append({
                            "id": img.id,
                            "path": img.image_url or img.image_path,
                            "pose": img.pose,
                            "expression": img.expression,
                            "angle": img.angle,
                        })

            # 如果使用标记的训练图片
            if use_selected_images and not training_images:
                statement = (
                    select(CharacterImage)
                    .where(CharacterImage.character_id == character_id)
                    .where(CharacterImage.is_selected_for_training == True)
                )
                for img in session.exec(statement).all():
                    training_images.append({
                        "id": img.id,
                        "path": img.image_url or img.image_path,
                        "pose": img.pose,
                        "expression": img.expression,
                        "angle": img.angle,
                    })

        logger.info(f"Found {len(training_images)} training images from gallery")
        update_progress(0.15, f"找到 {len(training_images)} 张训练图片")

        # 确定始祖图
        base_image_path = ancestor_image_path or anchor_image or reference_image
        if not base_image_path and not training_images:
            raise ValueError(f"No reference image or training images for character: {character_id}")

        # 生成触发词
        clean_name = character_name.lower().replace(" ", "_")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
        trigger_word = f"ohwx_{clean_name}"

        # 更新 LoRA 记录
        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.trigger_word = trigger_word
                lora.status = LoRATrainingStatus.GENERATING_DATASET
                session.add(lora)
                session.commit()

        # 阶段 3: 准备数据集 (15% - 50%)
        update_progress(0.20, "正在准备数据集...")

        from integrations.lora_trainer import DatasetImage, dataset_generator
        import requests

        dataset: List[DatasetImage] = []

        # 从图片库中的图片创建 DatasetImage
        for i, img_info in enumerate(training_images):
            img_path = img_info["path"]
            if not img_path:
                continue

            try:
                # 读取图片数据
                if img_path.startswith(("http://", "https://")):
                    response = requests.get(img_path, timeout=30)
                    response.raise_for_status()
                    image_data = response.content
                else:
                    import os
                    if os.path.exists(img_path):
                        with open(img_path, "rb") as f:
                            image_data = f.read()
                    else:
                        continue

                # 生成 caption
                caption = f"a photo of {trigger_word}"
                if img_info.get("pose"):
                    caption += f", {img_info['pose']}"
                if img_info.get("expression"):
                    caption += f", {img_info['expression']}"
                if img_info.get("angle"):
                    caption += f", {img_info['angle']}"

                dataset.append(DatasetImage(
                    image_data=image_data,
                    caption=caption,
                    filename=f"{img_info['id']}.png"
                ))

                progress = 0.20 + (0.15 * (i + 1) / max(len(training_images), 1))
                update_progress(progress, f"已处理 {i + 1}/{len(training_images)} 张图片")

            except Exception as e:
                logger.warning(f"Failed to read image {img_path}: {e}")
                continue

        logger.info(f"Prepared {len(dataset)} images from gallery")

        # 如果图片不足，生成补充图片
        if len(dataset) < num_dataset_images and base_image_path:
            num_to_generate = num_dataset_images - len(dataset)
            update_progress(0.35, f"图片不足，正在生成 {num_to_generate} 张补充图片...")

            try:
                additional_dataset = dataset_generator.generate_dataset(
                    ancestor_image_path=base_image_path,
                    character_name=trigger_word,
                    character_prompt=appearance_prompt,
                    num_images=num_to_generate,
                )
                if additional_dataset:
                    dataset.extend(additional_dataset)
                    logger.info(f"Generated {len(additional_dataset)} additional images")
            except Exception as e:
                logger.warning(f"Failed to generate additional images: {e}")

        if not dataset:
            raise RuntimeError("Failed to prepare dataset - no images available")

        # 更新 LoRA 状态
        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.status = LoRATrainingStatus.DATASET_READY
                lora.dataset_size = len(dataset)
                session.add(lora)
                session.commit()

        update_progress(0.50, f"数据集准备完成，共 {len(dataset)} 张图片")

        # 阶段 4: 打包上传数据集 (50% - 60%)
        update_progress(0.55, "正在打包数据集...")

        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.status = LoRATrainingStatus.UPLOADING
                session.add(lora)
                session.commit()

        zip_data = dataset_generator.package_dataset(dataset)
        update_progress(0.58, "正在上传数据集到 OSS...")

        from integrations.oss_service import is_oss_configured, require_oss

        if not is_oss_configured():
            raise RuntimeError("OSS is not configured. LoRA training requires OSS to upload dataset.")

        oss = require_oss()
        dataset_filename = f"lora_dataset_{lora_id}"
        dataset_url = oss.upload_bytes(zip_data, filename=dataset_filename, folder="lora_datasets", ext=".zip")
        logger.info(f"Dataset uploaded to OSS: {dataset_url}")

        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.dataset_url = dataset_url
                session.add(lora)
                session.commit()

        update_progress(0.60, "数据集上传完成")

        # 阶段 5: 启动云端训练 (60% - 65%)
        update_progress(0.62, f"正在启动 {provider} 训练...")

        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.status = LoRATrainingStatus.TRAINING
                session.add(lora)
                session.commit()

        from integrations.lora_trainer import LoRATrainerFactory, TrainingConfig, TrainingProvider

        trainer = LoRATrainerFactory.get_trainer(TrainingProvider(provider))
        config = TrainingConfig(
            trigger_word=trigger_word,
            base_model="flux",
            steps=training_steps,
        )

        training_job = trainer.start_training(dataset_url, config)

        # 更新 LoRA 记录
        with Session(engine) as session:
            lora = session.get(CharacterLoRA, lora_id)
            if lora:
                lora.training_job_id = training_job.job_id
                lora.training_metadata = {
                    "job": training_job.metadata,
                    "gallery_images": len(training_images),
                    "generated_images": len(dataset) - len(training_images),
                    "total_steps": training_steps,
                }
                session.add(lora)
                session.commit()

        update_progress(0.65, f"训练任务已提交: {training_job.job_id}")

        # 阶段 6: 轮询训练进度 (65% - 100%)
        # 训练进度从 65% 到 100%，映射训练步数
        import time
        max_poll_time = 3600 * 2  # 最多轮询 2 小时
        poll_interval = 30  # 每 30 秒轮询一次
        start_time = time.time()

        while time.time() - start_time < max_poll_time:
            # 检查任务是否被取消
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if job and job.status == JobStatus.REVOKED:
                    logger.info(f"Job {job_id} was cancelled")
                    trainer.cancel_training(training_job.job_id)
                    with Session(engine) as session:
                        lora = session.get(CharacterLoRA, lora_id)
                        if lora:
                            lora.status = LoRATrainingStatus.FAILED
                            lora.error_message = "Training cancelled by user"
                            session.add(lora)
                            session.commit()
                    return {"status": "cancelled", "lora_id": lora_id}

            # 查询训练状态
            status_job = trainer.get_training_status(training_job.job_id)

            # 计算总进度：65% + 训练进度 * 35%
            training_progress = status_job.progress
            total_progress = 0.65 + (training_progress * 0.35)

            current_step = int(training_progress * training_steps)
            update_progress(
                total_progress,
                f"训练中... {current_step}/{training_steps} 步 ({int(training_progress * 100)}%)"
            )

            with Session(engine) as session:
                lora = session.get(CharacterLoRA, lora_id)
                if lora:
                    lora.progress = training_progress
                    session.add(lora)
                    session.commit()

            if status_job.status == "completed":
                # 训练完成
                with Session(engine) as session:
                    lora = session.get(CharacterLoRA, lora_id)
                    if lora:
                        lora.status = LoRATrainingStatus.READY
                        lora.lora_url = status_job.lora_url
                        lora.progress = 1.0
                        session.add(lora)
                        session.commit()

                    job = session.get(Job, job_id)
                    if job:
                        job.status = JobStatus.SUCCESS
                        job.progress = 1.0
                        job.completed_at = datetime.utcnow()
                        job.result = {
                            "lora_id": lora_id,
                            "lora_url": status_job.lora_url,
                            "trigger_word": trigger_word,
                            "dataset_size": len(dataset),
                            "training_steps": training_steps,
                        }
                        session.add(job)
                        session.commit()

                publish_job_update_sync(job_id, project_id, {
                    "status": JobStatus.SUCCESS.value,
                    "progress": 1.0,
                    "message": f"LoRA 训练完成！",
                    "lora_id": lora_id,
                    "lora_url": status_job.lora_url,
                })

                logger.info(f"LoRA training completed: {status_job.lora_url}")
                return {
                    "status": "success",
                    "lora_id": lora_id,
                    "lora_url": status_job.lora_url,
                }

            elif status_job.status == "failed":
                # 训练失败
                error_msg = status_job.error_message or "Training failed"
                with Session(engine) as session:
                    lora = session.get(CharacterLoRA, lora_id)
                    if lora:
                        lora.status = LoRATrainingStatus.FAILED
                        lora.error_message = error_msg
                        session.add(lora)
                        session.commit()

                    job = session.get(Job, job_id)
                    if job:
                        job.status = JobStatus.FAILURE
                        job.error_message = error_msg
                        job.completed_at = datetime.utcnow()
                        session.add(job)
                        session.commit()

                publish_job_update_sync(job_id, project_id, {
                    "status": JobStatus.FAILURE.value,
                    "error_message": error_msg,
                    "lora_id": lora_id,
                })

                logger.error(f"LoRA training failed: {error_msg}")
                return {"status": "failed", "error": error_msg, "lora_id": lora_id}

            time.sleep(poll_interval)

        # 超时
        error_msg = "Training timeout after 2 hours"
        _fail_lora_job(job_id, lora_id, project_id, error_msg)
        return {"status": "failed", "error": error_msg, "lora_id": lora_id}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"LoRA training task failed: {error_msg}")
        _fail_lora_job(job_id, lora_id, project_id, error_msg)
        return {"status": "failed", "error": error_msg, "lora_id": lora_id}


def _fail_lora_job(job_id: str, lora_id: str, project_id: str, error_message: str):
    """Helper to mark LoRA job as failed."""
    with Session(engine) as session:
        lora = session.get(CharacterLoRA, lora_id)
        if lora:
            lora.status = LoRATrainingStatus.FAILED
            lora.error_message = error_message
            session.add(lora)
            session.commit()

        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILURE
            job.error_message = error_message
            job.completed_at = datetime.utcnow()
            session.add(job)
            session.commit()

    publish_job_update_sync(job_id, project_id, {
        "status": JobStatus.FAILURE.value,
        "error_message": error_message,
        "lora_id": lora_id,
    })
