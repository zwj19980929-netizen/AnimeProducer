"""Pipeline - 视觉流水线组件"""

import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TypeVar

from config import settings
from core.editor import AlignmentStrategy, ShotArtifact
from core.duration_planner import DurationPlanner, DurationPlan, get_audio_duration
from core.prompt_translator import PromptTranslator, StructuredPrompt, prompt_translator
from core.character_registry import CharacterRegistry, CharacterAsset, character_registry


def sanitize_filename(name: Any) -> str:
    """清理文件名中的非法字符。"""
    return re.sub(r'[^\w\-_.]', '_', str(name))


logger = logging.getLogger(__name__)


# ============================================================================
# 数据类型定义
# ============================================================================


@dataclass
class KeyframeRequest:
    """关键帧生成请求。"""
    shot_id: int
    prompt: str
    reference_image_path: Optional[str] = None
    style_preset: Optional[str] = None
    width: int = 1024
    height: int = 1024
    num_inference_steps: int = 30
    guidance_scale: float = 7.5
    negative_prompt: str = "low quality, bad anatomy, blurry"


@dataclass
class KeyframeResult:
    """关键帧生成结果。"""
    shot_id: int
    image_path: str  # 本地路径（如果保存到本地）或空字符串
    image_data: Optional[bytes] = None
    image_url: Optional[str] = None  # OSS URL（如果上传到云端）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VLMScoreRequest:
    """VLM 评分请求"""
    image_path: str  # 本地路径（可为空）
    prompt: str
    image_url: Optional[str] = None  # OSS URL
    image_data: Optional[bytes] = None  # 图片二进制数据
    criteria: List[str] = field(default_factory=lambda: [
        "composition",
        "style_consistency",
        "prompt_adherence",
        "quality"
    ])


@dataclass
class VLMScoreResult:
    """VLM 评分结果"""
    image_path: str
    overall_score: float
    criteria_scores: Dict[str, float] = field(default_factory=dict)
    feedback: Optional[str] = None


@dataclass
class VideoGenRequest:
    """图生视频请求"""
    shot_id: int
    image_path: str  # 本地路径（可为空）
    image_url: Optional[str] = None  # OSS URL（优先使用）
    motion_prompt: Optional[str] = None
    camera_movement: Optional[str] = None
    duration: float = 4.0
    fps: int = 24


@dataclass
class VideoGenResult:
    """图生视频结果"""
    shot_id: int
    video_path: str
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AudioGenRequest:
    """TTS 音频生成请求"""
    shot_id: int
    text: str
    voice_id: Optional[str] = None
    language: str = "zh-CN"
    speed: float = 1.0
    # 情感参数
    emotion: Optional[str] = None  # happy, sad, angry, fearful, surprised, excited, tense, neutral
    emotion_intensity: float = 0.5  # 0-1


@dataclass
class AudioGenResult:
    """TTS 音频生成结果"""
    shot_id: int
    audio_path: str
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlignmentRequest:
    """音视频对齐请求"""
    shot_id: int
    video_path: str
    audio_path: str
    strategy: AlignmentStrategy = AlignmentStrategy.LOOP


@dataclass
class AlignmentResult:
    """音视频对齐结果"""
    shot_id: int
    output_path: str
    final_duration: float
    strategy_used: AlignmentStrategy


@dataclass
class LipSyncRequest:
    """Lip-Sync 请求"""
    shot_id: int
    video_path: str  # 输入视频路径或 URL
    audio_path: str  # 音频路径或 URL
    face_enhance: bool = True
    expression_scale: float = 1.0


@dataclass
class LipSyncResult:
    """Lip-Sync 结果"""
    shot_id: int
    video_path: str  # 输出视频路径或 URL
    duration: float
    provider: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 抽象接口定义
# ============================================================================


class ImageGeneratorProtocol(Protocol):
    """图像生成器协议"""
    def generate_image(
        self, 
        prompt: str, 
        reference_image_path: Optional[str] = None
    ) -> Optional[bytes]:
        ...


class VLMProtocol(Protocol):
    """VLM 协议"""
    def score_image(
        self, 
        image_path: str, 
        prompt: str
    ) -> Dict[str, Any]:
        ...


class VideoGeneratorProtocol(Protocol):
    """视频生成器协议"""
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        image_url: Optional[str] = None
    ) -> Optional[bytes]:
        ...


class TTSProtocol(Protocol):
    """TTS 协议"""
    def synthesize(
        self, 
        text: str, 
        voice_id: Optional[str] = None
    ) -> Optional[bytes]:
        ...


# ============================================================================
# 流水线组件
# ============================================================================


class PipelineComponent(ABC):
    """流水线组件基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    def process(self, request: Any) -> Any:
        """处理请求"""
        pass
    
    def validate(self, request: Any) -> bool:
        """验证请求"""
        return True


class KeyframeGenerator(PipelineComponent):
    """
    关键帧生成器

    使用图像生成模型创建关键帧，支持：
    - 注入参考图像以保持角色一致性
    - 自动将自然语言提示词转换为 Danbooru 风格标签
    - 所有生成的图片强制上传到 OSS
    """

    def __init__(
        self,
        image_generator: Optional[ImageGeneratorProtocol] = None,
        prompt_translator: Optional[PromptTranslator] = None,
        enable_prompt_translation: bool = True
    ):
        super().__init__("KeyframeGenerator")
        self._image_generator = image_generator
        self._prompt_translator = prompt_translator
        self._enable_prompt_translation = enable_prompt_translation

        if self._image_generator is None:
            from integrations.provider_factory import ProviderFactory
            self._image_generator = ProviderFactory.get_image_client()

        if self._prompt_translator is None:
            from core.prompt_translator import prompt_translator as default_translator
            self._prompt_translator = default_translator

    def process(self, request: KeyframeRequest) -> KeyframeResult:
        """
        生成关键帧

        Args:
            request: 关键帧生成请求

        Returns:
            关键帧生成结果

        Raises:
            RuntimeError: 图像生成失败或 OSS 上传失败
        """
        self.logger.info(f"Generating keyframe for shot {request.shot_id}")
        self.logger.debug(f"Original prompt: {request.prompt[:100]}...")

        if request.reference_image_path:
            self.logger.debug(f"Using reference image: {request.reference_image_path}")

        # 构建提示词（可选择是否翻译为 Danbooru 风格）
        full_prompt, negative_prompt = self._build_prompt(request)
        self.logger.debug(f"Final prompt: {full_prompt[:200]}...")

        image_data = self._image_generator.generate_image(
            prompt=full_prompt,
            reference_image_path=request.reference_image_path
        )

        if not image_data:
            raise RuntimeError(f"Failed to generate keyframe for shot {request.shot_id}")

        # 强制上传到 OSS
        from integrations.oss_service import require_oss
        oss = require_oss()

        filename = f"keyframe_shot_{sanitize_filename(request.shot_id)}"
        image_url = oss.upload_image_bytes(image_data, filename=filename)
        self.logger.info(f"Keyframe uploaded to OSS: {image_url}")

        return KeyframeResult(
            shot_id=request.shot_id,
            image_path="",  # 不保存本地
            image_data=image_data,
            image_url=image_url,
            metadata={
                "prompt": full_prompt,
                "negative_prompt": negative_prompt,
                "original_prompt": request.prompt,
                "reference_image": request.reference_image_path,
                "style_preset": request.style_preset,
                "prompt_translated": self._enable_prompt_translation
            }
        )

    def _build_prompt(self, request: KeyframeRequest) -> tuple:
        """
        构建完整的提示词

        Args:
            request: 关键帧请求

        Returns:
            (positive_prompt, negative_prompt) 元组
        """
        if self._enable_prompt_translation:
            # 使用提示词翻译器转换为 Danbooru 风格
            structured = self._prompt_translator.translate(
                natural_prompt=request.prompt,
                style_preset=request.style_preset,
            )
            return structured.positive, structured.negative
        else:
            # 使用原始提示词（简单拼接）
            parts = [request.prompt]
            if request.style_preset:
                parts.append(request.style_preset)
            parts.append("high quality, detailed")
            return ", ".join(parts), request.negative_prompt

    def validate(self, request: KeyframeRequest) -> bool:
        """验证请求"""
        if not request.prompt:
            self.logger.error("Prompt is required")
            return False

        if request.reference_image_path and not os.path.exists(request.reference_image_path):
            self.logger.warning(f"Reference image not found: {request.reference_image_path}")

        return True


class VLMScorer(PipelineComponent):
    """
    VLM 评分器

    使用视觉语言模型对生成的图像进行质量评分。
    支持 Gemini Vision 和 OpenAI GPT-4o 作为后端。
    不使用 Mock，必须配置真实的 VLM API。
    """

    def __init__(self, vlm_client: Optional[VLMProtocol] = None):
        super().__init__("VLMScorer")
        self._vlm_client = vlm_client

        if self._vlm_client is None:
            self._vlm_client = self._create_vlm_client()

    def _create_vlm_client(self) -> VLMProtocol:
        """创建真实的 VLM 客户端"""
        from integrations.vlm_client import VLMClient
        real_client = VLMClient()

        # 包装 VLMClient 以符合 VLMProtocol 接口
        class VLMClientWrapper:
            def __init__(self, client: VLMClient):
                self._client = client

            def score_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
                """评分单张图片"""
                # 使用 VLMClient 的 score_keyframes 方法
                candidates = [{"id": "single", "image_path": image_path}]
                results = self._client.score_keyframes(
                    candidates=candidates,
                    scene_description=prompt,
                    characters=[]
                )

                if results and len(results) > 0:
                    scored = results[0]
                    # 转换为统一的评分格式 (0-1 范围)
                    return {
                        "overall_score": scored.weighted_total / 100.0,
                        "composition": scored.scores.composition_score / 100.0,
                        "style_consistency": scored.scores.character_consistency_score / 100.0,
                        "prompt_adherence": scored.scores.prompt_match_score / 100.0,
                        "quality": scored.weighted_total / 100.0,
                        "feedback": scored.scores.reasoning
                    }
                else:
                    raise RuntimeError("VLM scoring failed: no results returned")

        self.logger.info("Using real VLM client for scoring")
        return VLMClientWrapper(real_client)

    def process(self, request: VLMScoreRequest) -> VLMScoreResult:
        """
        对图像进行评分

        Args:
            request: VLM 评分请求

        Returns:
            VLM 评分结果
        """
        self.logger.info(f"Scoring image: {request.image_path or request.image_url or 'from bytes'}")

        # 确定图片来源
        image_path = request.image_path
        temp_file = None

        # 如果没有本地文件，尝试从 URL 下载或使用 image_data
        if not image_path or not os.path.exists(image_path):
            if request.image_data:
                # 使用传入的图片数据创建临时文件
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                temp_file.write(request.image_data)
                temp_file.close()
                image_path = temp_file.name
            elif request.image_url:
                # 从 URL 下载图片
                import tempfile
                import requests
                self.logger.info(f"Downloading image from URL for scoring...")
                response = requests.get(request.image_url, timeout=30)
                response.raise_for_status()
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                temp_file.write(response.content)
                temp_file.close()
                image_path = temp_file.name
            else:
                raise FileNotFoundError(f"Image not found: {request.image_path}")

        try:
            result = self._vlm_client.score_image(image_path, request.prompt)

            criteria_scores = {
                criterion: result.get(criterion, 0.0)
                for criterion in request.criteria
                if criterion in result
            }

            score_result = VLMScoreResult(
                image_path=request.image_path or request.image_url or "",
                overall_score=result.get("overall_score", 0.0),
                criteria_scores=criteria_scores,
                feedback=result.get("feedback")
            )

            self.logger.info(
                f"Image score: {score_result.overall_score:.2f} "
                f"(criteria: {criteria_scores})"
            )

            return score_result
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
    
    def validate(self, request: VLMScoreRequest) -> bool:
        """验证请求"""
        if not request.image_path:
            self.logger.error("Image path is required")
            return False
        return True


class VideoGenerator(PipelineComponent):
    """
    图生视频生成器

    将静态关键帧转换为动态视频片段。
    所有生成的视频强制上传到 OSS。
    """

    def __init__(
        self,
        video_generator: Optional[VideoGeneratorProtocol] = None
    ):
        super().__init__("VideoGenerator")
        self._video_generator = video_generator

        if self._video_generator is None:
            from integrations.provider_factory import ProviderFactory
            self._video_generator = ProviderFactory.get_video_client()

    def process(self, request: VideoGenRequest) -> VideoGenResult:
        """
        生成视频

        Args:
            request: 图生视频请求

        Returns:
            图生视频结果

        Raises:
            FileNotFoundError: 输入图像不存在
            RuntimeError: 视频生成失败或 OSS 上传失败
        """
        self.logger.info(f"Generating video for shot {request.shot_id}")
        self.logger.info(f"  image_path: {request.image_path}")
        self.logger.info(f"  image_url: {request.image_url}")

        # 确定图片来源：优先使用 URL，否则使用本地路径
        image_source = request.image_url or request.image_path

        if not image_source:
            raise ValueError(f"No image source provided for shot {request.shot_id}")

        # 如果是本地路径，检查文件是否存在
        if not request.image_url and request.image_path:
            if not os.path.exists(request.image_path):
                raise FileNotFoundError(f"Image not found: {request.image_path}")

        motion_prompt = request.motion_prompt
        if request.camera_movement:
            motion_prompt = f"{motion_prompt or ''}, {request.camera_movement}".strip(", ")

        # 调用视频生成器
        video_data = self._video_generator.generate_video(
            image_path=request.image_path if not request.image_url else request.image_path,
            image_url=request.image_url,
            motion_prompt=motion_prompt,
            duration=request.duration
        )

        if not video_data:
            raise RuntimeError(f"Failed to generate video for shot {request.shot_id}")

        # 强制上传到 OSS
        from integrations.oss_service import require_oss
        oss = require_oss()

        filename = f"video_shot_{sanitize_filename(request.shot_id)}"
        video_url = oss.upload_video_bytes(video_data, filename=filename)
        self.logger.info(f"Video uploaded to OSS: {video_url}")

        return VideoGenResult(
            shot_id=request.shot_id,
            video_path=video_url,  # 现在存储的是 OSS URL
            duration=request.duration,
            metadata={
                "source_image": request.image_url or request.image_path,
                "motion_prompt": motion_prompt,
                "camera_movement": request.camera_movement,
                "oss_url": video_url
            }
        )

    def validate(self, request: VideoGenRequest) -> bool:
        """验证请求"""
        if not request.image_path and not request.image_url:
            self.logger.error("Image path or URL is required")
            return False
        if request.duration <= 0:
            self.logger.error("Duration must be positive")
            return False
        return True


class AudioGenerator(PipelineComponent):
    """
    TTS 音频生成器

    将文本对白转换为语音音频。
    所有生成的音频强制上传到 OSS。
    """

    def __init__(
        self,
        tts_client: Optional[TTSProtocol] = None
    ):
        super().__init__("AudioGenerator")
        self._tts_client = tts_client

        if self._tts_client is None:
            from integrations.provider_factory import ProviderFactory
            self._tts_client = ProviderFactory.get_tts_client()

    def process(self, request: AudioGenRequest) -> AudioGenResult:
        """
        生成音频

        Args:
            request: TTS 音频生成请求

        Returns:
            TTS 音频生成结果

        Raises:
            RuntimeError: 音频生成失败或 OSS 上传失败
            ValueError: 无效的 speed 参数
        """
        # 验证 speed 参数，防止除零错误
        if request.speed <= 0:
            raise ValueError(f"Speed must be positive, got {request.speed}")

        self.logger.info(f"Generating audio for shot {request.shot_id}")
        self.logger.debug(f"Text: {request.text[:100]}...")

        # 根据情感计算 TTS 参数
        tts_speed = request.speed
        tts_emotion = None
        tts_pitch = 0

        if request.emotion:
            from core.emotion_analyzer import emotion_analyzer
            tts_params = emotion_analyzer.get_tts_params(
                emotion=request.emotion,
                intensity=request.emotion_intensity,
                base_speed=request.speed,
            )
            tts_speed = tts_params["speed"]
            tts_emotion = tts_params["emotion"]
            tts_pitch = tts_params["pitch"]
            self.logger.info(
                f"Emotion-aware TTS: emotion={request.emotion}, "
                f"intensity={request.emotion_intensity:.2f}, "
                f"speed={tts_speed:.2f}, pitch={tts_pitch}, tts_emotion={tts_emotion}"
            )

        # 调用 TTS 客户端，传递情感参数
        try:
            audio_data = self._tts_client.synthesize(
                text=request.text,
                voice_id=request.voice_id,
                speed=tts_speed,
                emotion=tts_emotion,
            )
        except TypeError:
            # 某些 TTS 客户端可能不支持 emotion 参数
            self.logger.warning("TTS client does not support emotion parameter, falling back")
            audio_data = self._tts_client.synthesize(
                text=request.text,
                voice_id=request.voice_id,
            )

        if not audio_data:
            raise RuntimeError(f"Failed to generate audio for shot {request.shot_id}")

        # 检测音频格式
        ext = ".mp3"
        if len(audio_data) >= 4:
            if audio_data[:4] == b'RIFF':
                ext = ".wav"
            elif audio_data[:4] == b'fLaC':
                ext = ".flac"
            elif audio_data[:3] == b'OGG':
                ext = ".ogg"

        # 强制上传到 OSS
        from integrations.oss_service import require_oss
        oss = require_oss()

        filename = f"audio_shot_{sanitize_filename(request.shot_id)}"
        audio_url = oss.upload_audio_bytes(audio_data, filename=filename, ext=ext)
        self.logger.info(f"Audio uploaded to OSS: {audio_url}")

        # 获取精确的音频时长
        # 需要先下载到临时文件来获取时长
        actual_duration = self._get_audio_duration_from_bytes(audio_data, ext)
        self.logger.info(f"Audio duration: {actual_duration:.2f}s")

        return AudioGenResult(
            shot_id=request.shot_id,
            audio_path=audio_url,  # 现在存储的是 OSS URL
            duration=actual_duration,
            metadata={
                "text": request.text,
                "voice_id": request.voice_id,
                "language": request.language,
                "speed": tts_speed,
                "emotion": request.emotion,
                "emotion_intensity": request.emotion_intensity,
                "oss_url": audio_url
            }
        )

    def _get_audio_duration_from_bytes(self, audio_data: bytes, ext: str) -> float:
        """从音频字节数据获取时长"""
        import tempfile
        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            temp_file.write(audio_data)
            temp_file.close()
            return get_audio_duration(temp_file.name)
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass

    def validate(self, request: AudioGenRequest) -> bool:
        """验证请求"""
        if not request.text:
            self.logger.error("Text is required")
            return False
        if request.speed <= 0:
            self.logger.error("Speed must be positive")
            return False
        return True


class ShotAligner(PipelineComponent):
    """
    音视频对齐器

    将视频和音频对齐到相同时长。
    支持从 OSS URL 下载文件，处理后上传结果到 OSS。
    """

    def __init__(self):
        super().__init__("ShotAligner")

    def process(self, request: AlignmentRequest) -> AlignmentResult:
        """
        对齐音视频

        Args:
            request: 音视频对齐请求

        Returns:
            音视频对齐结果

        Raises:
            FileNotFoundError: 输入文件不存在
            RuntimeError: OSS 上传失败
        """
        from moviepy import VideoFileClip, AudioFileClip
        from moviepy.video.fx import Loop
        import tempfile

        self.logger.info(f"Aligning shot {request.shot_id}")

        # 处理视频路径（可能是 OSS URL）
        video_path = self._resolve_path(request.video_path, "video")
        audio_path = self._resolve_path(request.audio_path, "audio")

        video = None
        audio = None
        temp_output = None
        temp_files = []

        try:
            video = VideoFileClip(video_path)
            audio = AudioFileClip(audio_path)

            video_duration = video.duration
            audio_duration = audio.duration

            self.logger.debug(
                f"Video: {video_duration:.2f}s, Audio: {audio_duration:.2f}s, "
                f"Strategy: {request.strategy.value}"
            )

            if video_duration < audio_duration:
                if request.strategy == AlignmentStrategy.SLOW_MOTION:
                    speed_factor = video_duration / audio_duration
                    video = video.with_speed_scaled(speed_factor)
                    self.logger.debug(f"Applied slow-motion: {speed_factor:.2f}x")
                else:
                    video = video.with_effects([Loop(duration=audio_duration)])
                    self.logger.debug(f"Applied loop to {audio_duration:.2f}s")
            elif video_duration > audio_duration:
                video = video.subclipped(0, audio_duration)
                self.logger.debug(f"Trimmed video to {audio_duration:.2f}s")

            video = video.with_audio(audio)
            final_duration = video.duration

            # 写入临时文件
            temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_output.close()
            temp_files.append(temp_output.name)

            video.write_videofile(
                temp_output.name,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )

            # 上传到 OSS
            from integrations.oss_service import require_oss
            oss = require_oss()

            filename = f"aligned_shot_{sanitize_filename(request.shot_id)}"
            output_url = oss.upload_file(temp_output.name, folder="videos")
            self.logger.info(f"Aligned shot uploaded to OSS: {output_url}")

            return AlignmentResult(
                shot_id=request.shot_id,
                output_path=output_url,  # 现在存储的是 OSS URL
                final_duration=final_duration,
                strategy_used=request.strategy
            )
        finally:
            if video:
                try:
                    video.close()
                except Exception:
                    pass
            if audio:
                try:
                    audio.close()
                except Exception:
                    pass
            # 清理临时文件
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception:
                        pass
            # 如果下载了临时文件，也要清理
            if video_path != request.video_path and os.path.exists(video_path):
                try:
                    os.unlink(video_path)
                except Exception:
                    pass
            if audio_path != request.audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass

    def _resolve_path(self, path: str, file_type: str) -> str:
        """
        解析路径，如果是 OSS URL 则下载到临时文件

        Args:
            path: 文件路径或 OSS URL
            file_type: 文件类型（用于日志）

        Returns:
            本地文件路径
        """
        if path.startswith("http://") or path.startswith("https://"):
            self.logger.info(f"Downloading {file_type} from OSS: {path}")
            from integrations.oss_service import OSSService
            return OSSService.get_instance().download_to_temp(path)
        else:
            if not os.path.exists(path):
                raise FileNotFoundError(f"{file_type.capitalize()} not found: {path}")
            return path

    def validate(self, request: AlignmentRequest) -> bool:
        """验证请求"""
        if not request.video_path or not request.audio_path:
            self.logger.error("Both video and audio paths are required")
            return False
        return True


class LipSyncProcessor(PipelineComponent):
    """
    Lip-Sync 处理器

    使用音频驱动人像动画技术，根据 TTS 音频重绘视频中人物的嘴部动作。
    支持 SadTalker, MuseTalk, LivePortrait, Wav2Lip 等技术。
    """

    def __init__(
        self,
        provider: str = "sadtalker",
        enabled: bool = True
    ):
        super().__init__("LipSyncProcessor")
        self.provider = provider
        self.enabled = enabled
        self._client = None

    def _get_client(self):
        """获取 Lip-Sync 客户端"""
        if self._client is None:
            from integrations.lipsync_client import LipSyncClientFactory, LipSyncProvider
            try:
                provider_enum = LipSyncProvider(self.provider.lower())
            except ValueError:
                self.logger.warning(f"Unknown provider: {self.provider}, using sadtalker")
                provider_enum = LipSyncProvider.SADTALKER
            self._client = LipSyncClientFactory.get_client(provider_enum)
        return self._client

    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """
        处理 Lip-Sync 请求

        Args:
            request: Lip-Sync 请求

        Returns:
            LipSyncResult: 处理结果
        """
        if not self.enabled:
            self.logger.info("Lip-Sync is disabled, returning original video")
            return LipSyncResult(
                shot_id=request.shot_id,
                video_path=request.video_path,
                duration=0,
                provider="none",
                metadata={"skipped": True}
            )

        self.logger.info(f"Processing lip-sync for shot {request.shot_id}")
        self.logger.info(f"  Provider: {self.provider}")
        self.logger.info(f"  Video: {request.video_path}")
        self.logger.info(f"  Audio: {request.audio_path}")

        try:
            from integrations.lipsync_client import LipSyncRequest as ClientRequest

            client = self._get_client()
            client_request = ClientRequest(
                video_path=request.video_path,
                audio_path=request.audio_path,
                face_enhance=request.face_enhance,
                expression_scale=request.expression_scale,
            )

            result = client.process(client_request)

            # 上传到 OSS
            from integrations.oss_service import is_oss_configured, require_oss

            if is_oss_configured() and not result.video_path.startswith("http"):
                oss = require_oss()
                video_url = oss.upload_file(result.video_path, folder="videos")
                self.logger.info(f"Lip-synced video uploaded to OSS: {video_url}")
                output_path = video_url
            else:
                output_path = result.video_path

            return LipSyncResult(
                shot_id=request.shot_id,
                video_path=output_path,
                duration=result.duration,
                provider=result.provider,
                metadata=result.metadata or {}
            )

        except Exception as e:
            self.logger.error(f"Lip-sync processing failed: {e}")
            self.logger.warning("Returning original video without lip-sync")
            return LipSyncResult(
                shot_id=request.shot_id,
                video_path=request.video_path,
                duration=0,
                provider="none",
                metadata={"error": str(e)}
            )

    def validate(self, request: LipSyncRequest) -> bool:
        """验证请求"""
        if not request.video_path:
            self.logger.error("Video path is required")
            return False
        if not request.audio_path:
            self.logger.error("Audio path is required")
            return False
        return True


# ============================================================================
# 流水线编排器
# ============================================================================


class ShotPipeline:
    """
    镜头处理流水线 (Audio-First Pipeline)

    采用"音频优先"策略：
    1. 先生成 TTS 音频，获取精确时长
    2. 根据音频时长规划视频生成策略
    3. ��成关键帧和视频
    4. 应用 Lip-Sync 口型同步
    5. 对齐音视频

    支持角色一致性：通过 CharacterRegistry 管理角色参考图和标签。
    支持镜头连续性：通过 Scene Context 保持镜头间的空间连续性。
    """

    def __init__(
        self,
        keyframe_generator: Optional[KeyframeGenerator] = None,
        vlm_scorer: Optional[VLMScorer] = None,
        video_generator: Optional[VideoGenerator] = None,
        audio_generator: Optional[AudioGenerator] = None,
        shot_aligner: Optional[ShotAligner] = None,
        lipsync_processor: Optional[LipSyncProcessor] = None,
        duration_planner: Optional[DurationPlanner] = None,
        character_registry: Optional[CharacterRegistry] = None,
        enable_vlm_scoring: bool = False,
        enable_lipsync: bool = True,
        lipsync_provider: str = "sadtalker",
        min_vlm_score: float = 0.7,
        max_keyframe_retries: int = 3
    ):
        self.keyframe_generator = keyframe_generator or KeyframeGenerator()
        self.vlm_scorer = vlm_scorer or VLMScorer()
        self.video_generator = video_generator or VideoGenerator()
        self.audio_generator = audio_generator or AudioGenerator()
        self.shot_aligner = shot_aligner or ShotAligner()
        self.lipsync_processor = lipsync_processor or LipSyncProcessor(
            provider=lipsync_provider,
            enabled=enable_lipsync
        )
        self.duration_planner = duration_planner or DurationPlanner()
        self.character_registry = character_registry  # 可选，不自动创建

        self.enable_vlm_scoring = enable_vlm_scoring
        self.enable_lipsync = enable_lipsync
        self.min_vlm_score = min_vlm_score
        self.max_keyframe_retries = max_keyframe_retries

        # 镜头连续性：存储上一个镜头的最后一帧
        self._last_frame_cache: Dict[str, str] = {}  # scene_id -> last_frame_path

        self.logger = logging.getLogger(f"{__name__}.ShotPipeline")

    def process_shot(
        self,
        shot_id: int,
        visual_prompt: str,
        dialogue: Optional[str] = None,
        reference_image_path: Optional[str] = None,
        camera_movement: Optional[str] = None,
        voice_id: Optional[str] = None,
        target_duration: float = 4.0,
        alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP,
        character_ids: Optional[List[str]] = None,
        # 情感参数
        emotion: Optional[str] = None,
        emotion_intensity: float = 0.5,
        # 镜头连续性参数
        scene_id: Optional[str] = None,
        previous_frame_path: Optional[str] = None,
        # Lip-Sync 参数
        enable_lipsync: Optional[bool] = None,
    ) -> ShotArtifact:
        """
        处理单个镜头的完整流水线 (Audio-First)

        执行顺序：
        1. 如果有对白，先生成音频获取精确时长
        2. 根据音频时长（或 target_duration）规划视频时长
        3. 生成关键帧（支持角色参考图注入和镜头连续性）
        4. 按规划时长生成视频
        5. 应用 Lip-Sync 口型同步（如有对白）
        6. 对齐音视频（如有需要）

        Args:
            shot_id: 镜头 ID
            visual_prompt: 视觉提示词
            dialogue: 对白文本（可选）
            reference_image_path: 参考图像路径（可选，会被角色参考图覆盖）
            camera_movement: 相机运动（可选）
            voice_id: 语音 ID（可选，会被角色语音 ID 覆盖）
            target_duration: 目标时长（无对白时使用）
            alignment_strategy: 对齐策略
            character_ids: 出场角色 ID 列表（可选）
            emotion: 镜头情感（可选，如未提供则从对白分析）
            emotion_intensity: 情感强度 0-1
            scene_id: 场景 ID（用于镜头连续性）
            previous_frame_path: 上一镜头的最后一帧（用于镜头连续性）
            enable_lipsync: 是否启用 Lip-Sync（默认使用全局设置）

        Returns:
            镜头产出物
        """
        self.logger.info(f"Processing shot {shot_id} (Audio-First Pipeline)")

        # 确定是否启用 Lip-Sync
        use_lipsync = enable_lipsync if enable_lipsync is not None else self.enable_lipsync

        # ========== 镜头连续性处理 ==========
        # 如果提供了 scene_id，尝试获取上一镜头的最后一帧
        continuity_reference = previous_frame_path
        if scene_id and not continuity_reference:
            continuity_reference = self._last_frame_cache.get(scene_id)
            if continuity_reference:
                self.logger.info(f"Using scene context from previous shot: {continuity_reference}")

        # ========== 情感分析 ==========
        effective_emotion = emotion
        effective_emotion_intensity = emotion_intensity

        # 如果没有提供情感，从对白分析
        if not effective_emotion and dialogue:
            from core.emotion_analyzer import emotion_analyzer
            self.logger.info("Analyzing dialogue emotion...")
            emotion_result = emotion_analyzer.analyze(
                dialogue=dialogue,
                context=visual_prompt,
            )
            effective_emotion = emotion_result.emotion
            effective_emotion_intensity = emotion_result.intensity
            self.logger.info(
                f"Detected emotion: {effective_emotion} "
                f"(intensity={effective_emotion_intensity:.2f}, "
                f"confidence={emotion_result.confidence:.2f})"
            )

        # ========== 角色一致性处理 ==========
        effective_reference_image = reference_image_path
        effective_voice_id = voice_id
        character_tags: List[str] = []

        if character_ids and self.character_registry:
            self.logger.info(f"Processing with characters: {character_ids}")

            # 获取第一个角色的参考图（如果未指定）
            if not effective_reference_image and character_ids:
                first_char = self.character_registry.get(character_ids[0])
                if first_char:
                    effective_reference_image = self.character_registry.get_reference_for_shot(
                        character_ids[0]
                    )
                    if effective_reference_image:
                        self.logger.info(f"Using character reference: {effective_reference_image}")

                    # 使用角色的语音 ID
                    if not effective_voice_id and first_char.voice_id:
                        effective_voice_id = first_char.voice_id
                        self.logger.info(f"Using character voice: {effective_voice_id}")

            # 获取所有角色的标签
            positive_tags, negative_tags = self.character_registry.get_combined_tags_for_shot(
                character_ids
            )
            character_tags = positive_tags

        # ========== Step 1: 音频生成（如有对白）==========
        audio_path: Optional[str] = None
        audio_duration: float = 0.0
        duration_plan: Optional[DurationPlan] = None

        if dialogue:
            self.logger.info(f"[Step 1/4] Generating audio for dialogue (emotion={effective_emotion})...")
            audio_result = self.audio_generator.process(AudioGenRequest(
                shot_id=shot_id,
                text=dialogue,
                voice_id=effective_voice_id,
                emotion=effective_emotion,
                emotion_intensity=effective_emotion_intensity,
            ))
            audio_path = audio_result.audio_path
            audio_duration = audio_result.duration
            self.logger.info(f"Audio generated: {audio_duration:.2f}s")

            # ========== Step 2: 时长规划 ==========
            self.logger.info(f"[Step 2/4] Planning video duration based on audio...")
            duration_plan = self.duration_planner.plan(audio_duration)
            planned_video_duration = duration_plan.target_video_duration
            self.logger.info(
                f"Duration plan: audio={audio_duration:.2f}s -> "
                f"video={planned_video_duration:.2f}s "
                f"(segments={duration_plan.video_segments})"
            )
        else:
            self.logger.info(f"[Step 1/4] No dialogue, using target_duration={target_duration}s")
            duration_plan = self.duration_planner.plan_for_no_dialogue(target_duration)
            planned_video_duration = duration_plan.target_video_duration

        # ========== Step 3: 关键帧生成 ==========
        self.logger.info(f"[Step 3/6] Generating keyframe...")

        # 构建增强的提示词（包含角色标签和情感标签）
        enhanced_prompt = visual_prompt
        if character_tags:
            enhanced_prompt = f"{', '.join(character_tags)}, {visual_prompt}"

        # 添加情感视觉标签
        if effective_emotion and effective_emotion != "neutral":
            from core.emotion_analyzer import emotion_analyzer
            enhanced_prompt = emotion_analyzer.enhance_visual_prompt(
                visual_prompt=enhanced_prompt,
                emotion=effective_emotion,
                intensity=effective_emotion_intensity,
            )
            self.logger.info(f"Enhanced prompt with emotion tags: {enhanced_prompt[:100]}...")

        # 镜头连续性：优先使用上一镜头的最后一帧作为参考
        keyframe_reference = continuity_reference or effective_reference_image

        keyframe_result = self._generate_keyframe_with_retry(
            shot_id=shot_id,
            prompt=enhanced_prompt,
            reference_image_path=keyframe_reference
        )

        # ========== Step 4: 视频生成 ==========
        self.logger.info(f"[Step 4/6] Generating video (duration={planned_video_duration:.2f}s)...")

        if duration_plan.video_segments == 1:
            # 单段视频
            video_result = self.video_generator.process(VideoGenRequest(
                shot_id=shot_id,
                image_path=keyframe_result.image_path,
                image_url=keyframe_result.image_url,
                motion_prompt=visual_prompt,
                camera_movement=camera_movement,
                duration=planned_video_duration
            ))
            final_video_path = video_result.video_path
        else:
            # 多段视频拼接
            final_video_path = self._generate_multi_segment_video(
                shot_id=shot_id,
                keyframe_result=keyframe_result,
                visual_prompt=visual_prompt,
                camera_movement=camera_movement,
                duration_plan=duration_plan
            )

        # ========== Step 5: Lip-Sync 口型同步（如有对白）==========
        if dialogue and audio_path and use_lipsync:
            self.logger.info(f"[Step 5/6] Applying lip-sync...")
            try:
                lipsync_result = self.lipsync_processor.process(LipSyncRequest(
                    shot_id=shot_id,
                    video_path=final_video_path,
                    audio_path=audio_path,
                    face_enhance=True,
                    expression_scale=1.0 + (effective_emotion_intensity * 0.3),  # 根据情感强度调整表情幅度
                ))
                if lipsync_result.video_path != final_video_path:
                    final_video_path = lipsync_result.video_path
                    self.logger.info(f"Lip-sync applied successfully")
            except Exception as e:
                self.logger.warning(f"Lip-sync failed: {e}, continuing without lip-sync")
        else:
            self.logger.info(f"[Step 5/6] Skipping lip-sync (no dialogue or disabled)")

        # ========== Step 6: 音视频对齐（如有音频）==========
        if audio_path:
            self.logger.info(f"[Step 6/6] Aligning audio and video...")
            alignment_result = self.shot_aligner.process(AlignmentRequest(
                shot_id=shot_id,
                video_path=final_video_path,
                audio_path=audio_path,
                strategy=alignment_strategy
            ))
            final_video_path = alignment_result.output_path
            final_duration = alignment_result.final_duration
        else:
            final_duration = planned_video_duration

        # ========== 镜头连续性：缓存最后一帧 ==========
        if scene_id:
            try:
                last_frame_path = self._extract_last_frame(final_video_path, shot_id)
                if last_frame_path:
                    self._last_frame_cache[scene_id] = last_frame_path
                    self.logger.info(f"Cached last frame for scene {scene_id}: {last_frame_path}")
            except Exception as e:
                self.logger.warning(f"Failed to cache last frame: {e}")

        artifact = ShotArtifact(
            shot_id=shot_id,
            video_path=final_video_path,
            audio_path=audio_path,
            dialogue=dialogue,
            start_time=0.0,
            end_time=final_duration
        )

        self.logger.info(f"Shot {shot_id} processed successfully: {final_duration:.2f}s")

        return artifact

    def _extract_last_frame(self, video_path: str, shot_id: int) -> Optional[str]:
        """
        从视频中提取最后一帧，用于镜头连续性

        Args:
            video_path: 视频路径或 URL
            shot_id: 镜头 ID

        Returns:
            最后一帧的路径（OSS URL 或本地路径）
        """
        from moviepy import VideoFileClip
        import tempfile

        # 解析视频路径
        local_path = video_path
        if video_path.startswith("http://") or video_path.startswith("https://"):
            from integrations.oss_service import OSSService
            local_path = OSSService.get_instance().download_to_temp(video_path)

        clip = VideoFileClip(local_path)
        try:
            # 提取最后一帧
            temp_frame = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp_frame.close()

            # 获取最后一帧（稍微提前一点避免边界问题）
            last_time = max(0, clip.duration - 0.05)
            clip.save_frame(temp_frame.name, t=last_time)

            # 上传到 OSS
            from integrations.oss_service import is_oss_configured, require_oss
            if is_oss_configured():
                oss = require_oss()
                frame_url = oss.upload_file(temp_frame.name, folder="frames")
                # 清理临时文件
                try:
                    os.unlink(temp_frame.name)
                except Exception:
                    pass
                return frame_url
            else:
                return temp_frame.name
        finally:
            clip.close()
            # 清理下载的临时视频文件
            if local_path != video_path and os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                except Exception:
                    pass

    def _generate_multi_segment_video(
        self,
        shot_id: int,
        keyframe_result: KeyframeResult,
        visual_prompt: str,
        camera_movement: Optional[str],
        duration_plan: DurationPlan
    ) -> str:
        """
        生成多段视频并拼接

        当音频时长超过单次视频生成上限时，需要生成多段视频后拼接。

        Args:
            shot_id: 镜头 ID
            keyframe_result: 关键帧结果
            visual_prompt: 视觉提示词
            camera_movement: 相机运动
            duration_plan: 时长规划

        Returns:
            拼接后的视频 URL（OSS）或本地路径
        """
        from moviepy import VideoFileClip, concatenate_videoclips
        import tempfile

        self.logger.info(
            f"Generating {duration_plan.video_segments} video segments "
            f"(each {duration_plan.segment_duration:.2f}s)"
        )

        segment_paths: List[str] = []

        for i in range(duration_plan.video_segments):
            segment_id = f"{shot_id}_seg{i}"
            self.logger.info(f"Generating segment {i + 1}/{duration_plan.video_segments}...")

            video_result = self.video_generator.process(VideoGenRequest(
                shot_id=segment_id,
                image_path=keyframe_result.image_path,
                image_url=keyframe_result.image_url,
                motion_prompt=visual_prompt,
                camera_movement=camera_movement,
                duration=duration_plan.segment_duration
            ))
            segment_paths.append(video_result.video_path)

        # 下载 OSS 视频到临时文件（如果是 URL）
        from integrations.oss_service import is_oss_configured, OSSService
        temp_files = []
        local_segment_paths = []

        for path in segment_paths:
            if path.startswith("http://") or path.startswith("https://"):
                # 从 OSS 下载到临时文件
                oss = OSSService.get_instance()
                temp_path = oss.download_to_temp(path)
                temp_files.append(temp_path)
                local_segment_paths.append(temp_path)
            else:
                local_segment_paths.append(path)

        # 拼接视频
        self.logger.info(f"Concatenating {len(local_segment_paths)} video segments...")
        clips = [VideoFileClip(path) for path in local_segment_paths]

        try:
            final_clip = concatenate_videoclips(clips, method="compose")

            # 使用临时文件保存拼接后的视频
            temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_output.close()

            final_clip.write_videofile(
                temp_output.name,
                fps=24,
                codec="libx264",
                logger=None
            )

            # 上传到 OSS
            if is_oss_configured():
                oss = OSSService.get_instance()
                filename = f"video_shot_{sanitize_filename(shot_id)}_combined"
                video_url = oss.upload_file_and_cleanup(temp_output.name, folder="videos")
                self.logger.info(f"Combined video uploaded to OSS: {video_url}")
                return video_url
            else:
                # 移动到输出目录
                output_path = os.path.join(
                    settings.OUTPUT_DIR,
                    f"video_shot_{sanitize_filename(shot_id)}_combined.mp4"
                )
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.move(temp_output.name, output_path)
                self.logger.info(f"Combined video saved: {output_path}")
                return output_path
        finally:
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass
            # 清理临时文件
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
    
    def _generate_keyframe_with_retry(
        self,
        shot_id: int,
        prompt: str,
        reference_image_path: Optional[str] = None
    ) -> KeyframeResult:
        """生成关键帧，支持 VLM 评分重试"""
        # 确保至少执行一次生成
        max_retries = max(1, self.max_keyframe_retries)
        keyframe_result: Optional[KeyframeResult] = None

        for attempt in range(max_retries):
            keyframe_result = self.keyframe_generator.process(KeyframeRequest(
                shot_id=shot_id,
                prompt=prompt,
                reference_image_path=reference_image_path
            ))
            
            if not self.enable_vlm_scoring:
                return keyframe_result
            
            score_result = self.vlm_scorer.process(VLMScoreRequest(
                image_path=keyframe_result.image_path,
                prompt=prompt,
                image_url=keyframe_result.image_url,
                image_data=keyframe_result.image_data
            ))
            
            if score_result.overall_score >= self.min_vlm_score:
                self.logger.info(
                    f"Keyframe accepted (score: {score_result.overall_score:.2f})"
                )
                return keyframe_result
            
            self.logger.warning(
                f"Keyframe rejected (score: {score_result.overall_score:.2f} < "
                f"{self.min_vlm_score}), attempt {attempt + 1}/{self.max_keyframe_retries}"
            )
        
        self.logger.warning(
            f"Max retries reached for shot {shot_id}, using last keyframe"
        )
        return keyframe_result
    
    def process_shots(
        self,
        shots: List[Dict[str, Any]],
        alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP,
        scene_id: Optional[str] = None,
        enable_continuity: bool = True,
    ) -> List[ShotArtifact]:
        """
        批量处理镜头

        支持镜头连续性：同一场景内的镜头会自动使用上一镜头的最后一帧作为参考。

        Args:
            shots: 镜头配置列表
            alignment_strategy: 对齐策略
            scene_id: 场景 ID（用于镜头连续性）
            enable_continuity: 是否启用镜头连续性

        Returns:
            镜头产出物列表
        """
        artifacts: List[ShotArtifact] = []

        for i, shot_config in enumerate(shots):
            # 确定场景 ID
            shot_scene_id = shot_config.get("scene_id", scene_id)

            # 镜头连续性：获取上一镜头的最后一帧
            previous_frame = None
            if enable_continuity and i > 0 and shot_scene_id:
                previous_frame = self._last_frame_cache.get(shot_scene_id)

            artifact = self.process_shot(
                shot_id=shot_config["shot_id"],
                visual_prompt=shot_config["visual_prompt"],
                dialogue=shot_config.get("dialogue"),
                reference_image_path=shot_config.get("reference_image_path"),
                camera_movement=shot_config.get("camera_movement"),
                voice_id=shot_config.get("voice_id"),
                target_duration=shot_config.get("duration", 4.0),
                alignment_strategy=alignment_strategy,
                character_ids=shot_config.get("character_ids"),
                emotion=shot_config.get("emotion"),
                emotion_intensity=shot_config.get("emotion_intensity", 0.5),
                scene_id=shot_scene_id,
                previous_frame_path=previous_frame,
                enable_lipsync=shot_config.get("enable_lipsync"),
            )
            artifacts.append(artifact)

        return artifacts

    def clear_scene_cache(self, scene_id: Optional[str] = None):
        """
        清除场景缓存

        Args:
            scene_id: 要清除的场景 ID，如果为 None 则清除所有缓存
        """
        if scene_id:
            if scene_id in self._last_frame_cache:
                del self._last_frame_cache[scene_id]
                self.logger.info(f"Cleared scene cache for: {scene_id}")
        else:
            self._last_frame_cache.clear()
            self.logger.info("Cleared all scene caches")
