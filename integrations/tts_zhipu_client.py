"""
智谱 TTS 语音合成客户端
使用 GLM-4-Voice 模型进行语音合成
"""
import base64
import logging
from typing import Optional

from config import settings
from integrations.base_client import QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class ZhipuTTSClient:
    """智谱 TTS 语音合成客户端 (使用 GLM-4-Voice)"""

    provider_name: str = "zhipu_tts"

    def __init__(self):
        self.api_key = settings.ZHIPU_API_KEY
        self._client = None

        if not self.api_key:
            logger.warning("ZHIPU_API_KEY 未配置")

    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            from zhipuai import ZhipuAI
            self._client = ZhipuAI(api_key=self.api_key)
        return self._client

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> bytes:
        """
        使用智谱 GLM-4-Voice 合成语音

        Args:
            text: 要合成的文本
            voice_id: 音色ID (暂不支持，GLM-4-Voice 使用默认音色)
            speed: 语速 (暂不支持)

        Returns:
            音频数据 (WAV 格式)
        """
        if not self.api_key:
            raise AuthenticationError("ZHIPU_API_KEY 未配置")

        try:
            client = self._get_client()

            # 使用 GLM-4-Voice 模型，它会返回语音
            response = client.chat.completions.create(
                model='glm-4-voice',
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': text}
                        ]
                    }
                ]
            )

            # 从响应中提取音频数据
            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                if hasattr(message, 'audio') and message.audio:
                    audio_data = message.audio.get('data')
                    if audio_data:
                        # 音频数据是 base64 编码的 WAV
                        return base64.b64decode(audio_data)

            raise RuntimeError("智谱 GLM-4-Voice 未返回音频数据")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"智谱 TTS API 请求失败: {error_msg}")

            if "429" in error_msg or "rate" in error_msg.lower():
                raise QuotaExceededError("智谱 TTS API 限流")
            if "401" in error_msg or "403" in error_msg or "auth" in error_msg.lower():
                raise AuthenticationError("智谱 TTS 认证失败")

            raise RuntimeError(f"智谱 TTS 合成失败: {error_msg}")

    def health_check(self) -> bool:
        return bool(self.api_key)


zhipu_tts_client = ZhipuTTSClient()
