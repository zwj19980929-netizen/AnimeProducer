"""
Voice Profile - 角色音色档案管理

管理角色的音色样本，支持：
- TTS 生成音色样本
- 手动上传音色样本
- 音色样本的存储和检索
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class VoiceProfile:
    """角色音色档案"""
    character_id: str                    # 角色 ID
    character_name: str                  # 角色名称
    sample_audio_path: Optional[str] = None  # 音色样本路径（3-5秒）
    tts_voice_id: Optional[str] = None   # 备用 TTS 音色 ID
    tts_provider: Optional[str] = None   # TTS 提供商
    language: str = "zh"                 # 语言
    gender: Optional[str] = None         # 性别 (male/female)
    age_group: Optional[str] = None      # 年龄段 (child/young/adult/elder)
    tone: Optional[str] = None           # 音调特征 (warm/cold/energetic/calm)
    sample_text: Optional[str] = None    # 生成样本时使用的文本
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_sample(self) -> bool:
        """是否有音色样本"""
        return self.sample_audio_path is not None and os.path.exists(self.sample_audio_path)

    def get_sample_bytes(self) -> Optional[bytes]:
        """获取音色样本的字节数据"""
        if not self.has_sample():
            return None
        with open(self.sample_audio_path, "rb") as f:
            return f.read()


class VoiceProfileManager:
    """
    音色档案管理器

    负责：
    - 创建和管理角色音色档案
    - 使用 TTS 生成音色样本
    - 存储和检索音色样本
    """

    # 默认样本文本（用于生成音色样本）
    DEFAULT_SAMPLE_TEXTS = {
        "zh": "你好，很高兴认识你。今天的天气真不错，我们一起出去走走吧。",
        "en": "Hello, nice to meet you. The weather is lovely today, shall we go for a walk?",
        "ja": "こんにちは、はじめまして。今日はいい天気ですね、一緒に散歩しましょうか。",
    }

    def __init__(self, project_id: Optional[str] = None):
        self._profiles: Dict[str, VoiceProfile] = {}
        self._project_id = project_id

        if project_id:
            self._voices_dir = settings.get_project_dir(project_id) / "voices"
        else:
            self._voices_dir = settings.ASSETS_DIR / "voices"

        self._voices_dir.mkdir(parents=True, exist_ok=True)

    def register(self, profile: VoiceProfile) -> None:
        """注册音色档案"""
        self._profiles[profile.character_id] = profile
        logger.info(f"注册音色档案: {profile.character_name} (id={profile.character_id})")

    def get(self, character_id: str) -> Optional[VoiceProfile]:
        """获取音色档案"""
        return self._profiles.get(character_id)

    def get_by_name(self, name: str) -> Optional[VoiceProfile]:
        """根据名称获取音色档案"""
        name_lower = name.lower()
        for profile in self._profiles.values():
            if profile.character_name.lower() == name_lower:
                return profile
        return None

    def list_profiles(self) -> List[VoiceProfile]:
        """列出所有音色档案"""
        return list(self._profiles.values())

    def create_profile_with_tts(
        self,
        character_id: str,
        character_name: str,
        tts_voice_id: str,
        tts_provider: str = "aliyun",
        language: str = "zh",
        sample_text: Optional[str] = None,
        **kwargs
    ) -> VoiceProfile:
        """
        使用 TTS 创建音色档案并生成样本

        Args:
            character_id: 角色 ID
            character_name: 角色名称
            tts_voice_id: TTS 音色 ID
            tts_provider: TTS 提供商
            language: 语言
            sample_text: 样本文本（可选）
        """
        from integrations.provider_factory import ProviderFactory

        # 获取 TTS 客户端
        tts_client = ProviderFactory.get_tts_client(tts_provider)

        # 使用默认样本文本
        text = sample_text or self.DEFAULT_SAMPLE_TEXTS.get(language, self.DEFAULT_SAMPLE_TEXTS["zh"])

        # 生成音频样本
        logger.info(f"使用 {tts_provider} TTS 生成音色样本: voice_id={tts_voice_id}")
        audio_data = tts_client.synthesize(text=text, voice_id=tts_voice_id)

        # 保存样本
        sample_path = self._voices_dir / f"{character_id}_sample.mp3"
        with open(sample_path, "wb") as f:
            f.write(audio_data)

        logger.info(f"音色样本已保存: {sample_path}")

        # 创建档案
        profile = VoiceProfile(
            character_id=character_id,
            character_name=character_name,
            sample_audio_path=str(sample_path),
            tts_voice_id=tts_voice_id,
            tts_provider=tts_provider,
            language=language,
            sample_text=text,
            **kwargs
        )

        self.register(profile)
        self.save_profile(character_id)

        return profile

    def create_profile_with_sample(
        self,
        character_id: str,
        character_name: str,
        audio_sample: bytes,
        language: str = "zh",
        **kwargs
    ) -> VoiceProfile:
        """
        使用上传的音频样本创建音色档案

        Args:
            character_id: 角色 ID
            character_name: 角色名称
            audio_sample: 音频样本数据
            language: 语言
        """
        # 保存样本
        sample_path = self._voices_dir / f"{character_id}_sample.mp3"
        with open(sample_path, "wb") as f:
            f.write(audio_sample)

        logger.info(f"上传的音色样本已保存: {sample_path}")

        # 创建档案
        profile = VoiceProfile(
            character_id=character_id,
            character_name=character_name,
            sample_audio_path=str(sample_path),
            language=language,
            **kwargs
        )

        self.register(profile)
        self.save_profile(character_id)

        return profile

    def generate_sample_with_clone(
        self,
        character_id: str,
        reference_audio: bytes,
        sample_text: Optional[str] = None,
        language: str = "zh"
    ) -> Optional[str]:
        """
        使用语音克隆生成标准化的音色样本

        Args:
            character_id: 角色 ID
            reference_audio: 参考音频
            sample_text: 样本文本
            language: 语言

        Returns:
            生成的样本路径
        """
        from integrations.tts_aliyun_client import aliyun_tts_client

        text = sample_text or self.DEFAULT_SAMPLE_TEXTS.get(language, self.DEFAULT_SAMPLE_TEXTS["zh"])

        try:
            # 使用 CosyVoice 克隆
            audio_data = aliyun_tts_client.clone_voice(
                audio_sample=reference_audio,
                text=text
            )

            # 保存
            sample_path = self._voices_dir / f"{character_id}_sample.mp3"
            with open(sample_path, "wb") as f:
                f.write(audio_data)

            logger.info(f"克隆音色样本已保存: {sample_path}")
            return str(sample_path)

        except Exception as e:
            logger.error(f"音色克隆失败: {e}")
            return None

    def save_profile(self, character_id: str) -> bool:
        """保存音色档案到文件"""
        profile = self.get(character_id)
        if not profile:
            return False

        config_path = self._voices_dir / f"{character_id}.json"
        config_data = asdict(profile)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        return True

    def load_profile(self, character_id: str) -> Optional[VoiceProfile]:
        """从文件加载音色档案"""
        config_path = self._voices_dir / f"{character_id}.json"
        if not config_path.exists():
            return None

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        profile = VoiceProfile(**config_data)
        self.register(profile)
        return profile

    def load_all_profiles(self) -> int:
        """加载目录下所有音色档案"""
        count = 0
        for json_file in self._voices_dir.glob("*.json"):
            character_id = json_file.stem
            if self.load_profile(character_id):
                count += 1
        logger.info(f"加载了 {count} 个音色档案")
        return count

    def ensure_voice_sample(
        self,
        character_id: str,
        character_name: str,
        tts_voice_id: Optional[str] = None,
        tts_provider: str = "aliyun",
        language: str = "zh"
    ) -> VoiceProfile:
        """
        确保角色有音色样本（没有则创建）

        Args:
            character_id: 角色 ID
            character_name: 角色名称
            tts_voice_id: TTS 音色 ID（可选）
            tts_provider: TTS 提供商
            language: 语言

        Returns:
            VoiceProfile
        """
        # 先尝试加载已有的
        profile = self.get(character_id) or self.load_profile(character_id)

        if profile and profile.has_sample():
            return profile

        # 需要创建新的
        if tts_voice_id:
            return self.create_profile_with_tts(
                character_id=character_id,
                character_name=character_name,
                tts_voice_id=tts_voice_id,
                tts_provider=tts_provider,
                language=language
            )
        else:
            # 没有指定音色，创建空档案
            profile = VoiceProfile(
                character_id=character_id,
                character_name=character_name,
                language=language
            )
            self.register(profile)
            return profile


# 全局实例
voice_profile_manager = VoiceProfileManager()
