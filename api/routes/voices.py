"""
Voice Profile API - 角色音色档案管理接口

提供音色样本的上传、生成和管理功能，用于 Seedance 2.0 音色一致性。
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from config import settings
from core.voice_profile import VoiceProfileManager, VoiceProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voices", tags=["voices"])


class VoiceProfileResponse(BaseModel):
    """音色档案响应"""
    character_id: str
    character_name: str
    sample_audio_path: Optional[str] = None
    tts_voice_id: Optional[str] = None
    tts_provider: Optional[str] = None
    language: str = "zh"
    has_sample: bool = False


class CreateVoiceProfileRequest(BaseModel):
    """创建音色档案请求（TTS 生成）"""
    character_id: str
    character_name: str
    tts_voice_id: str
    tts_provider: str = "aliyun"
    language: str = "zh"
    sample_text: Optional[str] = None


class VoiceProfileListResponse(BaseModel):
    """音色档案列表响应"""
    profiles: list[VoiceProfileResponse]
    total: int


def _profile_to_response(profile: VoiceProfile) -> VoiceProfileResponse:
    """转换 VoiceProfile 为响应模型"""
    return VoiceProfileResponse(
        character_id=profile.character_id,
        character_name=profile.character_name,
        sample_audio_path=profile.sample_audio_path,
        tts_voice_id=profile.tts_voice_id,
        tts_provider=profile.tts_provider,
        language=profile.language,
        has_sample=profile.has_sample()
    )


@router.get("", response_model=VoiceProfileListResponse)
async def list_voice_profiles(project_id: Optional[str] = None):
    """
    列出所有音色档案

    Args:
        project_id: 项目 ID（可选，用于项目级别的音色管理）
    """
    manager = VoiceProfileManager(project_id)
    manager.load_all_profiles()

    profiles = manager.list_profiles()
    return VoiceProfileListResponse(
        profiles=[_profile_to_response(p) for p in profiles],
        total=len(profiles)
    )


@router.get("/{character_id}", response_model=VoiceProfileResponse)
async def get_voice_profile(character_id: str, project_id: Optional[str] = None):
    """
    获取指定角色的音色档案

    Args:
        character_id: 角色 ID
        project_id: 项目 ID（可选）
    """
    manager = VoiceProfileManager(project_id)
    profile = manager.load_profile(character_id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Voice profile not found: {character_id}")

    return _profile_to_response(profile)


@router.post("/create-with-tts", response_model=VoiceProfileResponse)
async def create_voice_profile_with_tts(request: CreateVoiceProfileRequest, project_id: Optional[str] = None):
    """
    使用 TTS 创建音色档案

    通过指定的 TTS 提供商和音色 ID 生成音色样本。

    Args:
        request: 创建请求
        project_id: 项目 ID（可选）
    """
    manager = VoiceProfileManager(project_id)

    try:
        profile = manager.create_profile_with_tts(
            character_id=request.character_id,
            character_name=request.character_name,
            tts_voice_id=request.tts_voice_id,
            tts_provider=request.tts_provider,
            language=request.language,
            sample_text=request.sample_text
        )
        return _profile_to_response(profile)
    except Exception as e:
        logger.error(f"Failed to create voice profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-sample", response_model=VoiceProfileResponse)
async def upload_voice_sample(
    character_id: str = Form(...),
    character_name: str = Form(...),
    language: str = Form("zh"),
    project_id: Optional[str] = Form(None),
    audio_file: UploadFile = File(...)
):
    """
    上传音色样本创建档案

    上传 3-5 秒的音频样本作为角色音色参考。

    Args:
        character_id: 角色 ID
        character_name: 角色名称
        language: 语言
        project_id: 项目 ID（可选）
        audio_file: 音频文件（支持 mp3, wav, m4a）
    """
    # 验证文件类型
    allowed_types = ["audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"]
    if audio_file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {audio_file.content_type}"
        )

    manager = VoiceProfileManager(project_id)

    try:
        audio_data = await audio_file.read()
        profile = manager.create_profile_with_sample(
            character_id=character_id,
            character_name=character_name,
            audio_sample=audio_data,
            language=language
        )
        return _profile_to_response(profile)
    except Exception as e:
        logger.error(f"Failed to upload voice sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{character_id}")
async def delete_voice_profile(character_id: str, project_id: Optional[str] = None):
    """
    删除音色档案

    Args:
        character_id: 角色 ID
        project_id: 项目 ID（可选）
    """
    import os

    manager = VoiceProfileManager(project_id)
    profile = manager.load_profile(character_id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Voice profile not found: {character_id}")

    # 删除音频文件
    if profile.sample_audio_path and os.path.exists(profile.sample_audio_path):
        os.remove(profile.sample_audio_path)

    # 删除配置文件
    config_path = manager._voices_dir / f"{character_id}.json"
    if config_path.exists():
        config_path.unlink()

    return {"status": "deleted", "character_id": character_id}


@router.get("/tts-voices/{provider}")
async def list_tts_voices(provider: str):
    """
    列出指定 TTS 提供商的可用音色

    Args:
        provider: TTS 提供商 (aliyun, doubao, minimax, zhipu, openai)
    """
    # 预定义的音色列表
    voices = {
        "aliyun": [
            {"id": "longxiaochun", "name": "龙小淳", "gender": "female", "style": "温柔"},
            {"id": "longyuan", "name": "龙媛", "gender": "female", "style": "甜美"},
            {"id": "longxiaoxia", "name": "龙小夏", "gender": "female", "style": "活泼"},
            {"id": "longjielidou", "name": "龙杰力豆", "gender": "male", "style": "阳光"},
            {"id": "longshu", "name": "龙叔", "gender": "male", "style": "成熟"},
            {"id": "longxiaobai", "name": "龙小白", "gender": "male", "style": "少年"},
        ],
        "doubao": [
            {"id": "zh_female_shuangkuaisisi_moon_bigtts", "name": "爽快思思", "gender": "female"},
            {"id": "zh_male_wennuanahu_moon_bigtts", "name": "温暖阿虎", "gender": "male"},
            {"id": "zh_female_tianmeixiaoyuan_moon_bigtts", "name": "甜美小源", "gender": "female"},
        ],
        "openai": [
            {"id": "alloy", "name": "Alloy", "gender": "neutral"},
            {"id": "echo", "name": "Echo", "gender": "male"},
            {"id": "fable", "name": "Fable", "gender": "neutral"},
            {"id": "onyx", "name": "Onyx", "gender": "male"},
            {"id": "nova", "name": "Nova", "gender": "female"},
            {"id": "shimmer", "name": "Shimmer", "gender": "female"},
        ],
        "minimax": [
            {"id": "male-qn-qingse", "name": "青涩青年", "gender": "male"},
            {"id": "female-shaonv", "name": "少女", "gender": "female"},
            {"id": "male-qn-jingying", "name": "精英青年", "gender": "male"},
        ],
        "zhipu": [
            {"id": "alloy", "name": "默认音色", "gender": "neutral"},
        ]
    }

    if provider not in voices:
        raise HTTPException(status_code=400, detail=f"Unknown TTS provider: {provider}")

    return {"provider": provider, "voices": voices[provider]}
