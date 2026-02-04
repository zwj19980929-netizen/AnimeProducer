"""
TTS Client for voice synthesis using OpenAI.
Strict mode: No mocks.
"""
import io
import logging
import os
from pathlib import Path
from typing import Optional, Literal

from config import settings

logger = logging.getLogger(__name__)

class TTSClient:
    """Text-to-Speech client strictly using OpenAI."""

    def __init__(self):
        # 强制使用 OpenAI，忽略配置文件的 backend 设置如果它不是 openai
        self.backend = "openai"
        self.api_key = settings.OPENAI_API_KEY
        self._client = None

        if not self.api_key:
            # 尝试从环境变量获取
            self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.error("OPENAI_API_KEY is not set. TTS will fail.")
        else:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI Client: {e}")

    def generate_speech(
        self,
        text: str,
        voice_id: str = "nova",
    ) -> bytes:
        """
        Generate real speech using OpenAI TTS.
        """
        if not self._client:
            raise RuntimeError("OpenAI Client not initialized (Missing API Key).")

        if not text or not text.strip():
            logger.warning("Empty text provided for TTS.")
            return b""

        logger.info(f"Generating speech with OpenAI (Voice: {voice_id})...")

        try:
            # 确保使用有效的 OpenAI Voice ID
            valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
            voice = voice_id if voice_id in valid_voices else "alloy"

            response = self._client.audio.speech.create(
                model="tts-1", # 或 tts-1-hd
                voice=voice,
                input=text,
                response_format="mp3",
            )

            # response.content 包含二进制音频数据
            return response.content

        except Exception as e:
            logger.error(f"OpenAI TTS Generation Failed: {e}")
            raise e

    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize speech (alias for generate_speech to match TTSProtocol).
        """
        return self.generate_speech(text, voice_id or "nova")

    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration using moviepy (since we have it installed)."""
        try:
            from moviepy import AudioFileClip
            if not os.path.exists(audio_path):
                return 0.0
            with AudioFileClip(audio_path) as clip:
                return clip.duration
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 3.0 # Default fallback duration just to avoid crash in calculation

    def save_audio(self, audio_data: bytes, output_path: str) -> bool:
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(audio_data)
            logger.info(f"Saved audio to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise e

tts_client = TTSClient()