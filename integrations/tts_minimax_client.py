"""
MiniMax Speech-02 语音合成客户端
"""
import base64
import json
import logging
from typing import Optional

import requests

from config import settings
from integrations.base_client import QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class MiniMaxTTSClient:
    """MiniMax Speech-02 语音合成客户端"""
    
    provider_name: str = "minimax_tts"
    
    # 精品预设音色
    PRESET_VOICES = {
        "male_narrator": "male_narrator_001",
        "female_narrator": "female_narrator_001",
        "male_anime": "male_anime_001",
        "female_anime": "female_anime_001",
        "child": "child_001",
        "elder_male": "elder_male_001",
        "elder_female": "elder_female_001"
    }
    
    def __init__(self):
        self.api_key = settings.MINIMAX_API_KEY
        self.group_id = settings.MINIMAX_GROUP_ID
        self.endpoint = "https://api.minimax.chat/v1"
        
        if not self.api_key:
            logger.warning("MINIMAX_API_KEY 未配置")
    
    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        pitch: float = 0.0,
        **kwargs
    ) -> bytes:
        """
        使用 MiniMax Speech-02 合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 音色ID (可用预设或自定义)
            speed: 语速 (0.5-2.0)
            emotion: 情感标签
            pitch: 音调调整 (-12 到 12)
        """
        if not self.api_key:
            raise AuthenticationError("MINIMAX_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 使用预设音色或自定义
        actual_voice = self.PRESET_VOICES.get(voice_id, voice_id) or "female_narrator_001"
        
        payload = {
            "model": "speech-02",
            "text": text,
            "voice_setting": {
                "voice_id": actual_voice,
                "speed": speed,
                "pitch": pitch
            },
            "audio_setting": {
                "format": "mp3",
                "sample_rate": 24000
            }
        }
        
        if emotion:
            payload["voice_setting"]["emotion"] = emotion
        
        try:
            response = requests.post(
                f"{self.endpoint}/t2a_v2?GroupId={self.group_id}",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("MiniMax TTS API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("MiniMax TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            if result.get("base_resp", {}).get("status_code") != 0:
                raise RuntimeError(f"MiniMax TTS 错误: {result.get('base_resp', {}).get('status_msg')}")
            
            audio_hex = result.get("audio_file")
            if audio_hex:
                return bytes.fromhex(audio_hex)
            
            audio_b64 = result.get("data", {}).get("audio")
            if audio_b64:
                return base64.b64decode(audio_b64)
            
            raise RuntimeError("MiniMax TTS 未返回音频数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"MiniMax TTS API 请求失败: {e}")
            raise
    
    def clone_voice(
        self,
        audio_sample: bytes,
        text: str,
        voice_name: str = "custom_voice",
        **kwargs
    ) -> bytes:
        """
        MiniMax 声音复刻
        
        Args:
            audio_sample: 参考音频样本
            text: 要合成的文本
            voice_name: 克隆音色名称
        """
        if not self.api_key:
            raise AuthenticationError("MINIMAX_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        audio_b64 = base64.b64encode(audio_sample).decode("utf-8")
        
        payload = {
            "model": "speech-02",
            "text": text,
            "voice_setting": {
                "voice_id": "clone",
                "reference_audio": audio_b64
            },
            "audio_setting": {
                "format": "mp3"
            }
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/t2a_v2?GroupId={self.group_id}",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("MiniMax 声音复刻 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("MiniMax TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            audio_hex = result.get("audio_file")
            if audio_hex:
                return bytes.fromhex(audio_hex)
            
            raise RuntimeError("MiniMax 声音复刻未返回数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"MiniMax 声音复刻失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.api_key and self.group_id)


minimax_tts_client = MiniMaxTTSClient()
