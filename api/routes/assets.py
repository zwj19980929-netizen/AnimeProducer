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
    VoiceConfig,
    VoicePreviewRequest,
    VoicePreviewResponse,
    AvailableVoicesResponse,
)
from core.models import Character, Project

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
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def generate_character_reference(
    character_id: str,
    session: DBSession,
    asset_service: AssetDep,
    request: GenerateReferenceRequest = None,
) -> CharacterResponse:
    """Generate reference image for a character using AI.

    This endpoint triggers the asset generation pipeline for the character.
    You can provide a custom prompt to customize the generated image.

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

    # 构建完整的 prompt
    if custom_prompt:
        # 如果有自定义 prompt，追加到 prompt_base 后面
        full_prompt_base = f"{character.prompt_base}, {custom_prompt}"
        # 更新角色的 prompt_base
        character.prompt_base = full_prompt_base
        session.add(character)
        session.commit()
        session.refresh(character)

    try:
        # 生成参考图候选
        candidates = asset_service.manager.generate_reference_images(
            character=character,
            style_spec=style_preset,
            n=num_candidates,
            project_id=character.project_id,
            style_preset=style_preset
        )

        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate reference images",
            )

        # 选择最佳参考图（目前简单选第一个，后续可以加入评分逻辑）
        best_path = asset_service.manager.select_best_reference(
            candidates=candidates,
            character=character,
            session=session
        )

        logger.info(f"Generated reference image for {character_id}: {best_path}")

        # 刷新角色数据
        session.refresh(character)

        return CharacterResponse(
            character_id=character.character_id,
            project_id=character.project_id,
            name=character.name,
            prompt_base=character.prompt_base,
            reference_image_path=character.reference_image_path,
            reference_image_url=character.reference_image_url,
            voice_id=character.voice_id,
            character_metadata=character.character_metadata,
            created_at=character.created_at,
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
