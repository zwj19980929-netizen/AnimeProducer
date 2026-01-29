"""
智谱 GLM-4-Voice 语音合成客户端
端到端语音模型，支持方言和情感互动
"""
import base64
import json
import logging
from typing import Optional

import requests

from config import settings
from integrations.base_client import QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class ZhipuTTSClient:
    """智谱 GLM-4-Voice 语音合成客户端"""
    
    provider_name: str = "zhipu_tts"
    
    # 支持的方言
    DIALECTS = {
        "mandarin": "zh-CN",
        "cantonese": "zh-HK",
        "sichuan": "zh-SC",
        "shanghai": "zh-SH",
        "chongqing": "zh-CQ"
    }
    
    def __init__(self):
        self.api_key = settings.ZHIPU_API_KEY
        self.endpoint = "https://open.bigmodel.cn/api/paas/v4"
        
        if not self.api_key:
            logger.warning("ZHIPU_API_KEY 未配置")
    
    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        dialect: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        使用 GLM-4-Voice 合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 音色ID
            speed: 语速
            emotion: 情感 (neutral, happy, sad, angry, fear, surprise)
            dialect: 方言 (mandarin, cantonese, sichuan, shanghai, chongqing)
        """
        if not self.api_key:
            raise AuthenticationError("ZHIPU_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建请求
        payload = {
            "model": "glm-4-voice",
            "messages": [
                {
                    "role": "user",
                    "content": text
                }
            ],
            "audio": {
                "voice": voice_id or "alloy",
                "speed": speed,
                "format": "mp3"
            }
        }
        
        if emotion:
            payload["audio"]["emotion"] = emotion
        
        if dialect:
            payload["audio"]["language"] = self.DIALECTS.get(dialect, "zh-CN")
        
        try:
            response = requests.post(
                f"{self.endpoint}/audio/speech",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("智谱 TTS API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("智谱 TTS 认证失败")
            
            response.raise_for_status()
            
            # GLM-4-Voice 直接返回音频流
            content_type = response.headers.get("Content-Type", "")
            if "audio" in content_type or "octet-stream" in content_type:
                return response.content
            
            # 或者返回 JSON 包含 base64
            result = response.json()
            audio_b64 = result.get("data", {}).get("audio")
            if audio_b64:
                return base64.b64decode(audio_b64)
            
            raise RuntimeError("智谱 TTS 未返回音频数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"智谱 TTS API 请求失败: {e}")
            raise
    
    def interactive_speech(
        self,
        text: str,
        context: Optional[str] = None,
        emotion: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        智谱 GLM-4-Voice 情感互动模式
        根据上下文自动调整语气和情感
        
        Args:
            text: 要合成的文本
            context: 对话上下文（帮助模型理解情感）
            emotion: 期望的情感
        """
        if not self.api_key:
            raise AuthenticationError("ZHIPU_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if context:
            messages.append({
                "role": "system",
                "content": f"请根据以下情境理解并合成语音：{context}"
            })
        
        messages.append({
            "role": "user",
            "content": text
        })
        
        payload = {
            "model": "glm-4-voice",
            "messages": messages,
            "audio": {
                "format": "mp3",
                "auto_emotion": True  # 自动情感识别
            }
        }
        
        if emotion:
            payload["audio"]["emotion"] = emotion
        
        try:
            response = requests.post(
                f"{self.endpoint}/audio/speech",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("智谱 TTS API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("智谱 TTS 认证失败")
            
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "")
            if "audio" in content_type or "octet-stream" in content_type:
                return response.content
            
            result = response.json()
            audio_b64 = result.get("data", {}).get("audio")
            if audio_b64:
                return base64.b64decode(audio_b64)
            
            raise RuntimeError("智谱 TTS 未返回音频数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"智谱 TTS 互动模式失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.api_key)


zhipu_tts_client = ZhipuTTSClient()
