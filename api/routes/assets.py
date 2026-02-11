"""Character assets API routes."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import func, select

from api.deps import AssetDep, DBSession
from api.schemas import (
    CharacterCreate,
    CharacterListResponse,
    CharacterResponse,
    CharacterUpdate,
    ErrorResponse,
    GenerateReferenceRequest,
    GenerateVariantRequest,
    BatchGenerateVariantRequest,
    CharacterImageResponse,
    CharacterImageListResponse,
    SetAnchorImageRequest,
    MarkTrainingImagesRequest,
    VoiceConfig,
    VoicePreviewRequest,
    VoicePreviewResponse,
    AvailableVoicesResponse,
)
from core.models import Character, CharacterImage, CharacterImageType, Project

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/characters",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_character(
    character_in: CharacterCreate,
    session: DBSession,
    project_id: str | None = Query(default=None),
) -> Character:
    """Create a new character."""
    logger.info(f"Creating character: {character_in.name}")
    
    if project_id:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}",
            )
    
    existing = session.get(Character, character_in.character_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Character already exists: {character_in.character_id}",
        )
    
    character = Character(
        character_id=character_in.character_id,
        project_id=project_id,
        name=character_in.name,
        appearance_prompt=character_in.appearance_prompt,
        bio=character_in.bio,
        prompt_base=character_in.prompt_base,
        reference_image_path=character_in.reference_image_path,
        voice_id=character_in.voice_id,
        character_metadata=character_in.character_metadata,
    )
    
    session.add(character)
    session.commit()
    session.refresh(character)
    
    logger.info(f"Created character: {character.character_id}")
    return character


@router.get(
    "/characters",
    response_model=CharacterListResponse,
)
def list_characters(
    session: DBSession,
    project_id: str | None = Query(default=None),
) -> CharacterListResponse:
    """List all characters, optionally filtered by project."""
    logger.debug(f"Listing characters: project_id={project_id}")
    
    query = select(Character)
    count_query = select(func.count()).select_from(Character)
    
    if project_id:
        query = query.where(Character.project_id == project_id)
        count_query = count_query.where(Character.project_id == project_id)
    
    query = query.order_by(Character.created_at.desc())
    
    characters = session.exec(query).all()
    total = session.exec(count_query).one()
    
    return CharacterListResponse(
        items=[CharacterResponse.model_validate(c) for c in characters],
        total=total,
    )


@router.get(
    "/characters/{character_id}",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_character(
    character_id: str,
    session: DBSession,
) -> Character:
    """Get a character by ID."""
    logger.debug(f"Getting character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    return character


@router.patch(
    "/characters/{character_id}",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_character(
    character_id: str,
    character_in: CharacterUpdate,
    session: DBSession,
) -> Character:
    """Update a character."""
    logger.info(f"Updating character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    update_data = character_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    session.add(character)
    session.commit()
    session.refresh(character)
    
    logger.info(f"Updated character: {character_id}")
    return character


@router.delete(
    "/characters/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_character(
    character_id: str,
    session: DBSession,
) -> None:
    """Delete a character."""
    logger.info(f"Deleting character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    session.delete(character)
    session.commit()
    
    logger.info(f"Deleted character: {character_id}")


@router.post(
    "/characters/{character_id}/generate-reference",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def generate_character_reference(
    character_id: str,
    session: DBSession,
    asset_service: AssetDep,
    request: GenerateReferenceRequest = None,
) -> CharacterImageListResponse:
    """Generate reference images for a character using AI.

    使用角色的 appearance_prompt 生成候选参考图，存入图片库。
    用户可以从中选择一张作为锚定图。

    Args:
        character_id: The character ID
        request: Optional request body with custom_prompt, style_preset, num_candidates
    """
    logger.info(f"Generating reference for character: {character_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    # 解析请求参数
    if request is None:
        request = GenerateReferenceRequest()

    custom_prompt = request.custom_prompt
    style_preset = request.style_preset or "anime style"
    num_candidates = request.num_candidates
    negative_prompt = request.negative_prompt
    seed = request.seed

    # 构建完整的 prompt（使用 appearance_prompt）
    base_prompt = character.appearance_prompt or character.prompt_base or character.name
    if custom_prompt:
        full_prompt = f"{base_prompt}, {custom_prompt}"
    else:
        full_prompt = base_prompt

    try:
        # 生成参考图候选
        candidates = asset_service.manager.generate_reference_images(
            character=character,
            style_spec=style_preset,
            n=num_candidates,
            project_id=character.project_id,
            style_preset=style_preset,
            negative_prompt=negative_prompt,
            seed=seed,
            prompt_override=full_prompt  # 使用完整 prompt
        )

        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate reference images",
            )

        # 将候选图存入图片库
        created_images = []
        for candidate in candidates:
            image = CharacterImage(
                character_id=character_id,
                image_type=CharacterImageType.CANDIDATE,
                image_path=candidate.local_path,
                image_url=candidate.oss_url,
                prompt=full_prompt,
                style_preset=style_preset,
                generation_metadata={
                    "style_spec": style_preset,
                    "custom_prompt": custom_prompt,
                    "negative_prompt": negative_prompt,
                    "seed": candidate.seed,
                }
            )
            session.add(image)
            created_images.append(image)

        session.commit()

        # 刷新获取 ID
        for img in created_images:
            session.refresh(img)

        logger.info(f"Generated {len(created_images)} reference images for {character_id}")

        return CharacterImageListResponse(
            items=[CharacterImageResponse.model_validate(img) for img in created_images],
            total=len(created_images),
        )

    except Exception as e:
        logger.error(f"Failed to generate reference for {character_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reference image: {str(e)}",
        )


@router.post(
    "/characters/{character_id}/upload-to-oss",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def upload_character_image_to_oss(
    character_id: str,
    session: DBSession,
) -> CharacterResponse:
    """Upload existing local reference image to OSS.

    If the character already has a local reference image, this will upload it to OSS
    and update the reference_image_url field.
    """
    import os
    from integrations.oss_service import is_oss_configured, upload_file_to_oss

    logger.info(f"Uploading reference image to OSS for character: {character_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    # 检查是否已经有 OSS URL
    if character.reference_image_url:
        logger.info(f"Character {character_id} already has OSS URL")
        return CharacterResponse.model_validate(character)

    # 检查本地文件是否存在
    local_path = character.reference_image_path
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Local reference image not found: {local_path}",
        )

    # 检查 OSS 是否配置
    if not is_oss_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OSS is not configured",
        )

    try:
        # 上传到 OSS
        oss_url = upload_file_to_oss(local_path, cleanup=False)
        logger.info(f"Uploaded to OSS: {oss_url}")

        # 更新数据库
        character.reference_image_url = oss_url
        session.add(character)
        session.commit()
        session.refresh(character)

        return CharacterResponse.model_validate(character)

    except Exception as e:
        logger.error(f"Failed to upload to OSS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload to OSS: {str(e)}",
        )


@router.post(
    "/characters/batch-upload-to-oss",
    response_model=CharacterListResponse,
)
def batch_upload_characters_to_oss(
    session: DBSession,
    project_id: str | None = Query(default=None),
) -> CharacterListResponse:
    """Batch upload all local reference images to OSS.

    This will upload all characters that have local reference images but no OSS URL.
    """
    import os
    from integrations.oss_service import is_oss_configured, upload_file_to_oss

    logger.info(f"Batch uploading reference images to OSS, project_id={project_id}")

    if not is_oss_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OSS is not configured",
        )

    # 查询需要上传的角色
    query = select(Character).where(Character.reference_image_url.is_(None))
    if project_id:
        query = query.where(Character.project_id == project_id)

    characters = session.exec(query).all()
    logger.info(f"Found {len(characters)} characters to upload")

    uploaded = []
    for character in characters:
        local_path = character.reference_image_path
        if not local_path or not os.path.exists(local_path):
            logger.warning(f"Skipping {character.character_id}: local file not found")
            continue

        try:
            oss_url = upload_file_to_oss(local_path, cleanup=False)
            character.reference_image_url = oss_url
            session.add(character)
            uploaded.append(character)
            logger.info(f"Uploaded {character.name}: {oss_url}")
        except Exception as e:
            logger.error(f"Failed to upload {character.character_id}: {e}")

    session.commit()

    # 刷新所有上传的角色
    for character in uploaded:
        session.refresh(character)

    return CharacterListResponse(
        items=[CharacterResponse.model_validate(c) for c in uploaded],
        total=len(uploaded),
    )


# ============================================================================
# 语音相关 API
# ============================================================================

@router.get(
    "/voices",
    response_model=AvailableVoicesResponse,
)
def list_available_voices() -> AvailableVoicesResponse:
    """获取当前 TTS 提供商支持的语音列表"""
    from config import settings

    provider = settings.TTS_PROVIDER

    # 定义各提供商的可用语音
    voices_by_provider = {
        "openai": [
            {"id": "alloy", "name": "Alloy", "gender": "neutral", "description": "中性、平衡的声音"},
            {"id": "echo", "name": "Echo", "gender": "male", "description": "男性、深沉的声音"},
            {"id": "fable", "name": "Fable", "gender": "neutral", "description": "叙事风格的声音"},
            {"id": "onyx", "name": "Onyx", "gender": "male", "description": "男性、低沉有力的声音"},
            {"id": "nova", "name": "Nova", "gender": "female", "description": "女性、温暖的声音"},
            {"id": "shimmer", "name": "Shimmer", "gender": "female", "description": "女性、清亮的声音"},
        ],
        "aliyun": [
            {"id": "longxiaochun", "name": "龙小淳", "gender": "female", "description": "女性、甜美的声音"},
            {"id": "longyuan", "name": "龙媛", "gender": "female", "description": "女性、知性的声音"},
            {"id": "longxiaoxia", "name": "龙小夏", "gender": "female", "description": "女性、活泼的声音"},
            {"id": "longlaotie", "name": "龙老铁", "gender": "male", "description": "男性、东北口音"},
            {"id": "longshu", "name": "龙叔", "gender": "male", "description": "男性、成熟稳重"},
        ],
        "doubao": [
            {"id": "zh_female_cancan", "name": "灿灿", "gender": "female", "description": "女性、甜美的声音"},
            {"id": "zh_male_chunhou", "name": "淳厚", "gender": "male", "description": "男性、浑厚的声音"},
            {"id": "zh_female_shuangkuai", "name": "爽快", "gender": "female", "description": "女性、爽朗的声音"},
        ],
        "minimax": [
            {"id": "male_narrator", "name": "男性旁白", "gender": "male", "description": "适合旁白解说"},
            {"id": "female_narrator", "name": "女性旁白", "gender": "female", "description": "适合旁白解说"},
            {"id": "male_anime", "name": "男性动漫", "gender": "male", "description": "适合动漫角色"},
            {"id": "female_anime", "name": "女性动漫", "gender": "female", "description": "适合动漫角色"},
            {"id": "child", "name": "儿童", "gender": "neutral", "description": "适合儿童角色"},
            {"id": "elder_male", "name": "老年男性", "gender": "male", "description": "适合老年男性角色"},
            {"id": "elder_female", "name": "老年女性", "gender": "female", "description": "适合老年女性角色"},
        ],
        "zhipu": [
            {"id": "default", "name": "默认", "gender": "neutral", "description": "智谱默认语音"},
        ],
    }

    voices = voices_by_provider.get(provider, [])

    return AvailableVoicesResponse(
        provider=provider,
        voices=voices,
    )


@router.post(
    "/voices/preview",
    response_model=VoicePreviewResponse,
)
def preview_voice(
    request: VoicePreviewRequest,
) -> VoicePreviewResponse:
    """预览语音效果，生成一段测试音频"""
    from integrations.provider_factory import ProviderFactory
    from integrations.oss_service import is_oss_configured, OSSService
    from core.duration_planner import get_audio_duration
    import tempfile
    import os

    logger.info(f"Previewing voice: {request.voice_id}")

    try:
        # 获取 TTS 客户端
        tts_client = ProviderFactory.get_tts_client()

        # 生成音频
        audio_data = tts_client.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            speed=request.speed,
        )

        if not audio_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate audio",
            )

        # 上传到 OSS
        if is_oss_configured():
            oss = OSSService.get_instance()
            filename = f"voice_preview_{request.voice_id}"
            audio_url = oss.upload_audio_bytes(audio_data, filename=filename, ext=".mp3")
        else:
            # 保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_file.write(audio_data)
            temp_file.close()
            audio_url = temp_file.name

        # 计算时长
        duration = get_audio_duration(audio_data)

        return VoicePreviewResponse(
            audio_url=audio_url,
            duration=duration,
            voice_id=request.voice_id,
            text=request.text,
        )

    except Exception as e:
        logger.error(f"Failed to preview voice: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview voice: {str(e)}",
        )


@router.post(
    "/characters/{character_id}/voice",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def set_character_voice(
    character_id: str,
    voice_config: VoiceConfig,
    session: DBSession,
) -> CharacterResponse:
    """设置角色的语音配置

    设置后，该角色的所有对白都会使用这个语音。
    """
    logger.info(f"Setting voice for character {character_id}: {voice_config.voice_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    # 更新语音配置
    character.voice_id = voice_config.voice_id

    # 将其他语音参数存储在 metadata 中
    if character.character_metadata is None:
        character.character_metadata = {}

    character.character_metadata["voice_config"] = {
        "voice_id": voice_config.voice_id,
        "speed": voice_config.speed,
        "pitch": voice_config.pitch,
        "emotion": voice_config.emotion,
    }

    session.add(character)
    session.commit()
    session.refresh(character)

    logger.info(f"Voice set for character {character_id}")
    return CharacterResponse.model_validate(character)


# ============================================================================
# 角色图片库 API
# ============================================================================

@router.get(
    "/characters/{character_id}/images",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_character_images(
    character_id: str,
    session: DBSession,
    image_type: CharacterImageType | None = Query(default=None, description="按类型筛选"),
    training_only: bool = Query(default=False, description="只显示标记为训练的图片"),
) -> CharacterImageListResponse:
    """获取角色的图片库列表"""
    logger.debug(f"Listing images for character: {character_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    query = select(CharacterImage).where(CharacterImage.character_id == character_id)

    if image_type:
        query = query.where(CharacterImage.image_type == image_type)

    if training_only:
        query = query.where(CharacterImage.is_selected_for_training == True)

    query = query.order_by(CharacterImage.created_at.desc())
    images = session.exec(query).all()

    return CharacterImageListResponse(
        items=[CharacterImageResponse.model_validate(img) for img in images],
        total=len(images),
    )


@router.get(
    "/characters/{character_id}/images/{image_id}",
    response_model=CharacterImageResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_character_image(
    character_id: str,
    image_id: str,
    session: DBSession,
) -> CharacterImageResponse:
    """获取单张角色图片详情"""
    image = session.get(CharacterImage, image_id)
    if not image or image.character_id != character_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {image_id}",
        )

    return CharacterImageResponse.model_validate(image)


@router.delete(
    "/characters/{character_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_character_image(
    character_id: str,
    image_id: str,
    session: DBSession,
) -> None:
    """删除角色图片"""
    import os

    image = session.get(CharacterImage, image_id)
    if not image or image.character_id != character_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {image_id}",
        )

    # 检查是否为锚定图
    character = session.get(Character, character_id)
    if character and character.anchor_image_id == image_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete anchor image. Please set another image as anchor first.",
        )

    # 删除本地文件
    if image.image_path and os.path.exists(image.image_path):
        try:
            os.remove(image.image_path)
        except Exception as e:
            logger.warning(f"Failed to delete local file: {e}")

    session.delete(image)
    session.commit()

    logger.info(f"Deleted image {image_id} for character {character_id}")


@router.post(
    "/characters/{character_id}/images/set-anchor",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def set_anchor_image(
    character_id: str,
    request: SetAnchorImageRequest,
    session: DBSession,
) -> CharacterResponse:
    """设置锚定图（确定角色形象）

    设置后，所有后续生成的图片都会基于这张锚定图。
    """
    logger.info(f"Setting anchor image for character {character_id}: {request.image_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    image = session.get(CharacterImage, request.image_id)
    if not image or image.character_id != character_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {request.image_id}",
        )

    # 取消之前的锚定图标记
    if character.anchor_image_id:
        old_anchor = session.get(CharacterImage, character.anchor_image_id)
        if old_anchor:
            old_anchor.is_anchor = False
            old_anchor.image_type = CharacterImageType.CANDIDATE
            session.add(old_anchor)

    # 设置新的锚定图
    image.is_anchor = True
    image.image_type = CharacterImageType.ANCHOR
    session.add(image)

    # 更新角色
    character.anchor_image_id = image.id
    character.anchor_image_path = image.image_path
    character.anchor_image_url = image.image_url
    # 同时更新参考图（兼容旧逻辑）
    character.reference_image_path = image.image_path
    character.reference_image_url = image.image_url
    character.updated_at = datetime.utcnow()
    session.add(character)

    session.commit()
    session.refresh(character)

    logger.info(f"Anchor image set for character {character_id}")
    return CharacterResponse.model_validate(character)


@router.post(
    "/characters/{character_id}/images/mark-training",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def mark_training_images(
    character_id: str,
    request: MarkTrainingImagesRequest,
    session: DBSession,
) -> CharacterImageListResponse:
    """标记/取消标记图片用于 LoRA 训练"""
    logger.info(f"Marking training images for character {character_id}: {request.image_ids}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    updated_images = []
    for image_id in request.image_ids:
        image = session.get(CharacterImage, image_id)
        if image and image.character_id == character_id:
            image.is_selected_for_training = request.selected
            if request.selected:
                image.image_type = CharacterImageType.TRAINING
            elif image.image_type == CharacterImageType.TRAINING:
                # 取消训练标记时，恢复为变体图或候选图
                image.image_type = CharacterImageType.VARIANT if image.pose or image.expression else CharacterImageType.CANDIDATE
            session.add(image)
            updated_images.append(image)

    session.commit()

    for img in updated_images:
        session.refresh(img)

    return CharacterImageListResponse(
        items=[CharacterImageResponse.model_validate(img) for img in updated_images],
        total=len(updated_images),
    )


@router.post(
    "/characters/{character_id}/images/generate-variants",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def generate_character_variants(
    character_id: str,
    request: GenerateVariantRequest,
    session: DBSession,
    asset_service: AssetDep,
) -> CharacterImageListResponse:
    """基于锚定图生成变体图片（不同姿态/表情/角度）

    必须先设置锚定图才能生成变体。
    """
    logger.info(f"Generating variants for character {character_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    # 检查是否有锚定图
    if not character.anchor_image_path and not character.anchor_image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set an anchor image first before generating variants.",
        )

    # 构建变体 prompt
    base_prompt = character.appearance_prompt or character.prompt_base or character.name
    variant_parts = []

    if request.pose:
        variant_parts.append(request.pose)
    if request.expression:
        variant_parts.append(request.expression)
    if request.angle:
        variant_parts.append(request.angle)
    if request.custom_prompt:
        variant_parts.append(request.custom_prompt)

    variant_desc = ", ".join(variant_parts) if variant_parts else "portrait"
    full_prompt = f"{base_prompt}, {variant_desc}"

    style_preset = request.style_preset or "anime style"
    negative_prompt = request.negative_prompt
    seed = request.seed

    try:
        # 使用锚定图作为参考进行 I2I 生成
        candidates = asset_service.manager.generate_reference_images(
            character=character,
            style_spec=style_preset,
            n=request.num_images,
            project_id=character.project_id,
            style_preset=style_preset,
            negative_prompt=negative_prompt,
            seed=seed,
            prompt_override=full_prompt,
            reference_image=character.anchor_image_path or character.anchor_image_url,
        )

        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate variant images",
            )

        # 存入图片库
        created_images = []
        for candidate in candidates:
            image = CharacterImage(
                character_id=character_id,
                image_type=CharacterImageType.VARIANT,
                image_path=candidate.local_path,
                image_url=candidate.oss_url,
                prompt=full_prompt,
                pose=request.pose,
                expression=request.expression,
                angle=request.angle,
                style_preset=style_preset,
                generation_metadata={
                    "custom_prompt": request.custom_prompt,
                    "anchor_image": character.anchor_image_path,
                    "negative_prompt": negative_prompt,
                    "seed": candidate.seed,
                }
            )
            session.add(image)
            created_images.append(image)

        session.commit()

        for img in created_images:
            session.refresh(img)

        logger.info(f"Generated {len(created_images)} variant images for {character_id}")

        return CharacterImageListResponse(
            items=[CharacterImageResponse.model_validate(img) for img in created_images],
            total=len(created_images),
        )

    except Exception as e:
        logger.error(f"Failed to generate variants for {character_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate variant images: {str(e)}",
        )


@router.post(
    "/characters/{character_id}/images/batch-generate-variants",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def batch_generate_character_variants(
    character_id: str,
    request: BatchGenerateVariantRequest,
    session: DBSession,
    asset_service: AssetDep,
) -> CharacterImageListResponse:
    """批量生成多种变体图片

    一次性生成多种姿态/表情/角度的组合。
    """
    logger.info(f"Batch generating variants for character {character_id}")

    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    if not character.anchor_image_path and not character.anchor_image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set an anchor image first before generating variants.",
        )

    # 如果没有指定变体，使用默认的姿态/表情组合
    variants = request.variants
    if not variants:
        variants = [
            {"pose": "standing", "expression": "neutral", "angle": "front view"},
            {"pose": "standing", "expression": "smiling", "angle": "three-quarter view"},
            {"pose": "sitting", "expression": "serious", "angle": "side view"},
            {"pose": "walking", "expression": "happy", "angle": "front view"},
        ]

    base_prompt = character.appearance_prompt or character.prompt_base or character.name
    style_preset = request.style_preset or "anime style"
    negative_prompt = request.negative_prompt

    all_created_images = []

    for variant in variants:
        pose = variant.get("pose", "")
        expression = variant.get("expression", "")
        angle = variant.get("angle", "")
        custom = variant.get("custom_prompt", "")

        variant_parts = [p for p in [pose, expression, angle, custom] if p]
        variant_desc = ", ".join(variant_parts) if variant_parts else "portrait"
        full_prompt = f"{base_prompt}, {variant_desc}"

        try:
            candidates = asset_service.manager.generate_reference_images(
                character=character,
                style_spec=style_preset,
                n=1,
                project_id=character.project_id,
                style_preset=style_preset,
                negative_prompt=negative_prompt,
                prompt_override=full_prompt,
                reference_image=character.anchor_image_path or character.anchor_image_url,
            )

            if candidates:
                for candidate in candidates:
                    metadata = dict(variant)
                    metadata["negative_prompt"] = negative_prompt
                    metadata["seed"] = candidate.seed
                    image = CharacterImage(
                        character_id=character_id,
                        image_type=CharacterImageType.VARIANT,
                        image_path=candidate.local_path,
                        image_url=candidate.oss_url,
                        prompt=full_prompt,
                        pose=pose or None,
                        expression=expression or None,
                        angle=angle or None,
                        style_preset=style_preset,
                        generation_metadata=metadata,
                    )
                    session.add(image)
                    all_created_images.append(image)

        except Exception as e:
            logger.warning(f"Failed to generate variant {variant}: {e}")
            continue

    session.commit()

    for img in all_created_images:
        session.refresh(img)

    logger.info(f"Batch generated {len(all_created_images)} variant images for {character_id}")

    return CharacterImageListResponse(
        items=[CharacterImageResponse.model_validate(img) for img in all_created_images],
        total=len(all_created_images),
    )


@router.get(
    "/characters/{character_id}/training-images",
    response_model=CharacterImageListResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_training_images(
    character_id: str,
    session: DBSession,
) -> CharacterImageListResponse:
    """获取标记为训练的图片列表（用于 LoRA 训练）"""
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )

    query = (
        select(CharacterImage)
        .where(CharacterImage.character_id == character_id)
        .where(CharacterImage.is_selected_for_training == True)
        .order_by(CharacterImage.created_at)
    )
    images = session.exec(query).all()

    return CharacterImageListResponse(
        items=[CharacterImageResponse.model_validate(img) for img in images],
        total=len(images),
    )
