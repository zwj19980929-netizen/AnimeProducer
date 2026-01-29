"""
阿里云 CosyVoice / Qwen3-TTS 语音合成客户端
通过阿里云百炼接入
"""
import base64
import json
import logging
import time
from typing import Optional

import requests

from config import settings
from integrations.base_client import QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class AliyunTTSClient:
    """阿里云 CosyVoice / Qwen3-TTS 语音合成客户端"""
    
    provider_name: str = "aliyun_tts"
    
    def __init__(self):
        self.api_key = settings.ALIYUN_TTS_API_KEY
        self.endpoint = "https://dashscope.aliyuncs.com/api/v1"
        self.model = settings.ALIYUN_TTS_MODEL  # cosyvoice-v1 或 qwen3-tts
        
        if not self.api_key:
            logger.warning("ALIYUN_TTS_API_KEY 未配置")
    
    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        使用 CosyVoice/Qwen3-TTS 合成语音
        
        Args:
            text: 要合成的文本
            voice_id: 音色ID (如 longxiaochun, longyuan 等)
            speed: 语速
            emotion: 情感 (neutral, happy, sad, angry 等)
        """
        if not self.api_key:
            raise AuthenticationError("ALIYUN_TTS_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }
        
        payload = {
            "model": self.model,
            "input": {
                "text": text
            },
            "parameters": {
                "voice": voice_id or "longxiaochun",
                "format": "mp3",
                "rate": speed
            }
        }
        
        if emotion:
            payload["parameters"]["emotion"] = emotion
        
        try:
            # 提交异步任务
            response = requests.post(
                f"{self.endpoint}/services/aigc/text2audio/text-to-speech",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("阿里云 TTS API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("阿里云 TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"阿里云 TTS 任务创建失败: {result}")
            
            # 轮询任务状态
            for _ in range(30):
                status_response = requests.get(
                    f"{self.endpoint}/tasks/{task_id}",
                    headers=headers,
                    timeout=10
                )
                status_data = status_response.json()
                task_status = status_data.get("output", {}).get("task_status")
                
                if task_status == "SUCCEEDED":
                    audio_url = status_data["output"]["audio_url"]
                    audio_response = requests.get(audio_url, timeout=30)
                    return audio_response.content
                elif task_status == "FAILED":
                    raise RuntimeError(f"阿里云 TTS 生成失败: {status_data}")
                
                time.sleep(1)
            
            raise RuntimeError("阿里云 TTS 任务超时")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"阿里云 TTS API 请求失败: {e}")
            raise
    
    def clone_voice(
        self,
        audio_sample: bytes,
        text: str,
        **kwargs
    ) -> bytes:
        """
        CosyVoice 零样本语音克隆
        
        Args:
            audio_sample: 参考音频样本
            text: 要合成的文本
        """
        if not self.api_key:
            raise AuthenticationError("ALIYUN_TTS_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        audio_b64 = base64.b64encode(audio_sample).decode("utf-8")
        
        payload = {
            "model": "cosyvoice-clone-v1",
            "input": {
                "text": text,
                "reference_audio": f"data:audio/wav;base64,{audio_b64}"
            },
            "parameters": {
                "format": "mp3"
            }
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/services/aigc/text2audio/voice-clone",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("阿里云语音克隆 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("阿里云 TTS 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            audio_url = result.get("output", {}).get("audio_url")
            if audio_url:
                audio_response = requests.get(audio_url, timeout=30)
                return audio_response.content
            
            raise RuntimeError("阿里云语音克隆未返回数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"阿里云语音克隆失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.api_key)


aliyun_tts_client = AliyunTTSClient()
