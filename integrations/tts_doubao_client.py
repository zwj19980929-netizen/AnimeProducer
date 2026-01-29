"""
豆包 Seed-TTS 语音合成客户端
通过火山引擎接入
"""
import base64
import json
import logging
from typing import Optional

import requests

from config import settings
from integrations.base_client import QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class DoubaoTTSClient:
    """豆包 Seed-TTS 语音合成客户端"""
    
    provider_name: str = "doubao_tts"
    
    def __init__(self):
        self.api_key = settings.DOUBAO_TTS_API_KEY
        self.endpoint = settings.DOUBAO_TTS_ENDPOINT
        self.app_id = settings.DOUBAO_TTS_APP_ID
        
        if not self.api_key:
            logger.warning("DOUBAO_TTS_API_KEY 未配置")
    
    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        使用豆包 Seed-TTS 合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 音色ID
            speed: 语速 (0.5-2.0)
            emotion: 情感标签 (happy, sad, angry 等)
        
        Returns:
            音频数据 (bytes)
        """
        if not self.api_key:
            raise AuthenticationError("DOUBAO_TTS_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "app": {
                "appid": self.app_id,
                "cluster": "volcano_tts"
            },
            "user": {
                "uid": "anime_producer"
            },
            "audio": {
                "voice_type": voice_id or "zh_female_cancan",
                "encoding": "mp3",
                "speed_ratio": speed
            },
            "request": {
                "text": text,
                "operation": "query"
            }
        }
        
        if emotion:
            payload["audio"]["emotion"] = emotion
        
        try:
            response = requests.post(
                f"{self.endpoint}/api/v1/tts",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("豆包 TTS API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("豆包 TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 3000:
                raise RuntimeError(f"豆包 TTS 错误: {result.get('message')}")
            
            audio_b64 = result.get("data")
            if audio_b64:
                return base64.b64decode(audio_b64)
            
            raise RuntimeError("豆包 TTS 未返回音频数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"豆包 TTS API 请求失败: {e}")
            raise
    
    def clone_voice(
        self,
        audio_sample: bytes,
        text: str,
        **kwargs
    ) -> bytes:
        """
        使用音色克隆功能
        
        Args:
            audio_sample: 参考音频样本 (几秒即可)
            text: 要合成的文本
        """
        if not self.api_key:
            raise AuthenticationError("DOUBAO_TTS_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        audio_b64 = base64.b64encode(audio_sample).decode("utf-8")
        
        payload = {
            "app": {
                "appid": self.app_id,
                "cluster": "volcano_tts"
            },
            "audio": {
                "encoding": "mp3"
            },
            "request": {
                "text": text,
                "reference_audio": audio_b64,
                "operation": "clone"
            }
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/api/v1/tts/clone",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("豆包 TTS 克隆 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("豆包 TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            audio_data = result.get("data")
            if audio_data:
                return base64.b64decode(audio_data)
            
            raise RuntimeError("豆包音色克隆未返回数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"豆包音色克隆失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.api_key and self.app_id)


doubao_tts_client = DoubaoTTSClient()
