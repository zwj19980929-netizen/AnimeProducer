"""
TTS (Text-to-Speech) Client for voice synthesis.
Supports multiple TTS backends with configurable voice settings.
"""
import io
import logging
import os
import struct
import wave
from pathlib import Path
from typing import Optional, Literal

from config import settings

logger = logging.getLogger(__name__)

TTSBackend = Literal["openai", "google", "edge", "mock"]


class TTSClient:
    """Text-to-Speech client supporting multiple backends."""

    SAMPLE_RATE = 24000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit audio

    def __init__(
        self,
        backend: Optional[TTSBackend] = None,
        mock_mode: Optional[bool] = None,
    ):
        """
        Initialize TTS client.
        """
        self.backend = backend or settings.TTS_BACKEND
        self._mock_mode = mock_mode
        self._client = None

        if not self._is_mock_mode():
            self._init_client()

    def _is_mock_mode(self) -> bool:
        if self._mock_mode is not None:
            return self._mock_mode

        if self.backend == "mock":
            return True

        if self.backend == "openai":
            return not os.getenv("OPENAI_API_KEY")

        if self.backend == "google":
            return not settings.GOOGLE_API_KEY

        return False

    def _init_client(self) -> None:
        try:
            if self.backend == "openai":
                from openai import OpenAI
                self._client = OpenAI()
            elif self.backend == "google":
                logger.info("Google TTS client initialized (placeholder)")
            elif self.backend == "edge":
                logger.info("Edge TTS client initialized (uses edge-tts package)")
        except Exception as e:
            logger.warning(f"Failed to initialize TTS client: {e}. Falling back to mock mode.")
            self._mock_mode = True

    def _generate_mock_audio(self, text: str, duration: Optional[float] = None) -> bytes:
        """Generate mock WAV audio data for testing."""
        if duration is None:
            words = len(text.split())
            duration = max(1.0, words * 0.3)

        num_samples = int(self.SAMPLE_RATE * duration)
        samples = [0] * num_samples

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(struct.pack(f"<{num_samples}h", *samples))

        return buffer.getvalue()

    def _generate_openai(self, text: str, voice_id: str) -> bytes:
        """Generate speech using OpenAI TTS."""
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        voice = voice_id if voice_id in valid_voices else settings.TTS_DEFAULT_VOICE

        # 使用配置文件中的 TTS_MODEL
        response = self._client.audio.speech.create(
            model=settings.TTS_MODEL,
            voice=voice,
            input=text,
            response_format="wav",
        )

        return response.content

    # ... 其余方法保持不变 ...

    async def _generate_edge(self, text: str, voice_id: str) -> bytes:
        """Generate speech using Edge TTS (Microsoft)."""
        try:
            import edge_tts
        except ImportError:
            logger.error("edge-tts package not installed. Run: pip install edge-tts")
            return self._generate_mock_audio(text)

        voice = voice_id or "zh-CN-XiaoxiaoNeural"

        communicate = edge_tts.Communicate(text, voice)
        buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])

        return buffer.getvalue()

    def generate_speech(
        self,
        text: str,
        voice_id: str = "nova",
    ) -> bytes:
        """
        Generate speech audio from text.
        """
        if not text or not text.strip():
            logger.warning("Empty text provided, returning silence")
            return self.generate_silence(0.5)

        try:
            if self._is_mock_mode():
                logger.info(f"[MOCK] Generating speech for: {text[:50]}...")
                return self._generate_mock_audio(text)

            logger.info(f"Generating speech with {self.backend}: {text[:50]}...")

            if self.backend == "openai":
                return self._generate_openai(text, voice_id)

            elif self.backend == "edge":
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                return asyncio.run(self._generate_edge(text, voice_id))

            else:
                logger.warning(f"Backend {self.backend} not fully implemented, using mock")
                return self._generate_mock_audio(text)

        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return self._generate_mock_audio(text)

    def get_audio_duration(self, audio_path: str) -> float:
        """
        Get duration of an audio file in seconds.
        """
        path = Path(audio_path)
        if not path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return 0.0

        try:
            suffix = path.suffix.lower()

            if suffix == ".wav":
                with wave.open(str(path), "rb") as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    return frames / float(rate)

            elif suffix == ".mp3":
                try:
                    from mutagen.mp3 import MP3
                    audio = MP3(str(path))
                    return audio.info.length
                except ImportError:
                    logger.warning("mutagen not installed, falling back to moviepy")

            try:
                from moviepy import AudioFileClip
                with AudioFileClip(str(path)) as clip:
                    return clip.duration
            except Exception as e:
                logger.error(f"Failed to get duration with moviepy: {e}")
                return 0.0

        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            return 0.0

    def generate_silence(self, duration: float) -> bytes:
        """
        Generate silent audio of specified duration.
        """
        if duration <= 0:
            duration = 0.1

        num_samples = int(self.SAMPLE_RATE * duration)
        samples = [0] * num_samples

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(struct.pack(f"<{num_samples}h", *samples))

        logger.debug(f"Generated {duration:.2f}s of silence")
        return buffer.getvalue()

    def save_audio(self, audio_data: bytes, output_path: str) -> bool:
        """
        Save audio data to file.
        """
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "wb") as f:
                f.write(audio_data)

            logger.info(f"Saved audio to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            return False


tts_client = TTSClient()