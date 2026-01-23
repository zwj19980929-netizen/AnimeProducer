"""
Pipeline - 视觉流水线组件

职责：
- KeyframeGenerator: 关键帧生成（注入 reference image）
- VLMScorer: VLM 评分（可选）
- VideoGenerator: 图生视频
- AudioGenerator: TTS 生成
- ShotAligner: 音视频对齐

每个组件都是可独立测试的类
"""
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TypeVar

from config import settings
from core.editor import AlignmentStrategy, ShotArtifact

logger = logging.getLogger(__name__)


# ============================================================================
# 数据类型定义
# ============================================================================


@dataclass
class KeyframeRequest:
    """关键帧生成请求"""
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
    """关键帧生成结果"""
    shot_id: int
    image_path: str
    image_data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VLMScoreRequest:
    """VLM 评分请求"""
    image_path: str
    prompt: str
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
    image_path: str
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
        duration: float = 4.0
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
    
    使用图像生成模型创建关键帧，支持注入参考图像以保持角色一致性
    """
    
    def __init__(
        self, 
        image_generator: Optional[ImageGeneratorProtocol] = None,
        output_dir: Optional[str] = None
    ):
        super().__init__("KeyframeGenerator")
        self._image_generator = image_generator
        self._output_dir = output_dir or settings.OUTPUT_DIR
        
        if self._image_generator is None:
            from integrations.gen_client import gen_client
            self._image_generator = gen_client
    
    def process(self, request: KeyframeRequest) -> KeyframeResult:
        """
        生成关键帧
        
        Args:
            request: 关键帧生成请求
            
        Returns:
            关键帧生成结果
            
        Raises:
            RuntimeError: 图像生成失败
        """
        self.logger.info(f"Generating keyframe for shot {request.shot_id}")
        self.logger.debug(f"Prompt: {request.prompt[:100]}...")
        
        if request.reference_image_path:
            self.logger.debug(f"Using reference image: {request.reference_image_path}")
        
        full_prompt = self._build_prompt(request)
        
        image_data = self._image_generator.generate_image(
            prompt=full_prompt,
            reference_image_path=request.reference_image_path
        )
        
        if not image_data:
            raise RuntimeError(f"Failed to generate keyframe for shot {request.shot_id}")
        
        os.makedirs(self._output_dir, exist_ok=True)
        image_path = os.path.join(
            self._output_dir, 
            f"keyframe_shot_{request.shot_id}.png"
        )
        
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        self.logger.info(f"Saved keyframe: {image_path}")
        
        return KeyframeResult(
            shot_id=request.shot_id,
            image_path=image_path,
            image_data=image_data,
            metadata={
                "prompt": full_prompt,
                "reference_image": request.reference_image_path,
                "style_preset": request.style_preset
            }
        )
    
    def _build_prompt(self, request: KeyframeRequest) -> str:
        """构建完整的提示词"""
        parts = [request.prompt]
        
        if request.style_preset:
            parts.append(request.style_preset)
        
        parts.append("high quality, detailed")
        
        return ", ".join(parts)
    
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
    
    使用视觉语言模型对生成的图像进行质量评分
    """
    
    def __init__(self, vlm_client: Optional[VLMProtocol] = None):
        super().__init__("VLMScorer")
        self._vlm_client = vlm_client
        
        if self._vlm_client is None:
            self._vlm_client = self._create_default_vlm()
    
    def _create_default_vlm(self) -> VLMProtocol:
        """创建默认 VLM 客户端（mock 实现）"""
        class MockVLM:
            def score_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
                return {
                    "overall_score": 0.85,
                    "composition": 0.8,
                    "style_consistency": 0.9,
                    "prompt_adherence": 0.85,
                    "quality": 0.85,
                    "feedback": "Good overall quality"
                }
        return MockVLM()
    
    def process(self, request: VLMScoreRequest) -> VLMScoreResult:
        """
        对图像进行评分
        
        Args:
            request: VLM 评分请求
            
        Returns:
            VLM 评分结果
        """
        self.logger.info(f"Scoring image: {request.image_path}")
        
        if not os.path.exists(request.image_path):
            raise FileNotFoundError(f"Image not found: {request.image_path}")
        
        result = self._vlm_client.score_image(request.image_path, request.prompt)
        
        criteria_scores = {
            criterion: result.get(criterion, 0.0)
            for criterion in request.criteria
            if criterion in result
        }
        
        score_result = VLMScoreResult(
            image_path=request.image_path,
            overall_score=result.get("overall_score", 0.0),
            criteria_scores=criteria_scores,
            feedback=result.get("feedback")
        )
        
        self.logger.info(
            f"Image score: {score_result.overall_score:.2f} "
            f"(criteria: {criteria_scores})"
        )
        
        return score_result
    
    def validate(self, request: VLMScoreRequest) -> bool:
        """验证请求"""
        if not request.image_path:
            self.logger.error("Image path is required")
            return False
        return True


class VideoGenerator(PipelineComponent):
    """
    图生视频生成器
    
    将静态关键帧转换为动态视频片段
    """
    
    def __init__(
        self, 
        video_generator: Optional[VideoGeneratorProtocol] = None,
        output_dir: Optional[str] = None
    ):
        super().__init__("VideoGenerator")
        self._video_generator = video_generator
        self._output_dir = output_dir or settings.OUTPUT_DIR
        
        if self._video_generator is None:
            self._video_generator = self._create_default_generator()
    
    def _create_default_generator(self) -> VideoGeneratorProtocol:
        """创建默认视频生成器（mock 实现）"""
        class MockVideoGenerator:
            def generate_video(
                self, 
                image_path: str, 
                motion_prompt: Optional[str] = None,
                duration: float = 4.0
            ) -> Optional[bytes]:
                logger.debug(f"[MOCK] Generating video from {image_path}")
                return b"mock_video_data"
        return MockVideoGenerator()
    
    def process(self, request: VideoGenRequest) -> VideoGenResult:
        """
        生成视频
        
        Args:
            request: 图生视频请求
            
        Returns:
            图生视频结果
            
        Raises:
            FileNotFoundError: 输入图像不存在
            RuntimeError: 视频生成失败
        """
        self.logger.info(f"Generating video for shot {request.shot_id}")
        
        if not os.path.exists(request.image_path):
            raise FileNotFoundError(f"Image not found: {request.image_path}")
        
        motion_prompt = request.motion_prompt
        if request.camera_movement:
            motion_prompt = f"{motion_prompt or ''}, {request.camera_movement}".strip(", ")
        
        video_data = self._video_generator.generate_video(
            image_path=request.image_path,
            motion_prompt=motion_prompt,
            duration=request.duration
        )
        
        if not video_data:
            raise RuntimeError(f"Failed to generate video for shot {request.shot_id}")
        
        os.makedirs(self._output_dir, exist_ok=True)
        video_path = os.path.join(
            self._output_dir, 
            f"video_shot_{request.shot_id}.mp4"
        )
        
        with open(video_path, "wb") as f:
            f.write(video_data)
        
        self.logger.info(f"Saved video: {video_path}")
        
        return VideoGenResult(
            shot_id=request.shot_id,
            video_path=video_path,
            duration=request.duration,
            metadata={
                "source_image": request.image_path,
                "motion_prompt": motion_prompt,
                "camera_movement": request.camera_movement
            }
        )
    
    def validate(self, request: VideoGenRequest) -> bool:
        """验证请求"""
        if not request.image_path:
            self.logger.error("Image path is required")
            return False
        if request.duration <= 0:
            self.logger.error("Duration must be positive")
            return False
        return True


class AudioGenerator(PipelineComponent):
    """
    TTS 音频生成器
    
    将文本对白转换为语音音频
    """
    
    def __init__(
        self, 
        tts_client: Optional[TTSProtocol] = None,
        output_dir: Optional[str] = None
    ):
        super().__init__("AudioGenerator")
        self._tts_client = tts_client
        self._output_dir = output_dir or settings.OUTPUT_DIR
        
        if self._tts_client is None:
            self._tts_client = self._create_default_tts()
    
    def _create_default_tts(self) -> TTSProtocol:
        """创建默认 TTS 客户端（mock 实现）"""
        class MockTTS:
            def synthesize(
                self, 
                text: str, 
                voice_id: Optional[str] = None
            ) -> Optional[bytes]:
                logger.debug(f"[MOCK] Synthesizing: {text[:50]}...")
                return b"mock_audio_data"
        return MockTTS()
    
    def process(self, request: AudioGenRequest) -> AudioGenResult:
        """
        生成音频
        
        Args:
            request: TTS 音频生成请求
            
        Returns:
            TTS 音频生成结果
            
        Raises:
            RuntimeError: 音频生成失败
        """
        self.logger.info(f"Generating audio for shot {request.shot_id}")
        self.logger.debug(f"Text: {request.text[:100]}...")
        
        audio_data = self._tts_client.synthesize(
            text=request.text,
            voice_id=request.voice_id
        )
        
        if not audio_data:
            raise RuntimeError(f"Failed to generate audio for shot {request.shot_id}")
        
        os.makedirs(self._output_dir, exist_ok=True)
        audio_path = os.path.join(
            self._output_dir, 
            f"audio_shot_{request.shot_id}.mp3"
        )
        
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        
        estimated_duration = len(request.text) * 0.1 / request.speed
        
        self.logger.info(f"Saved audio: {audio_path}")
        
        return AudioGenResult(
            shot_id=request.shot_id,
            audio_path=audio_path,
            duration=estimated_duration,
            metadata={
                "text": request.text,
                "voice_id": request.voice_id,
                "language": request.language,
                "speed": request.speed
            }
        )
    
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
    
    将视频和音频对齐到相同时长
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        super().__init__("ShotAligner")
        self._output_dir = output_dir or settings.OUTPUT_DIR
    
    def process(self, request: AlignmentRequest) -> AlignmentResult:
        """
        对齐音视频
        
        Args:
            request: 音视频对齐请求
            
        Returns:
            音视频对齐结果
            
        Raises:
            FileNotFoundError: 输入文件不存在
        """
        from moviepy import VideoFileClip, AudioFileClip
        from moviepy.video.fx import Loop
        
        self.logger.info(f"Aligning shot {request.shot_id}")
        
        if not os.path.exists(request.video_path):
            raise FileNotFoundError(f"Video not found: {request.video_path}")
        if not os.path.exists(request.audio_path):
            raise FileNotFoundError(f"Audio not found: {request.audio_path}")
        
        video = VideoFileClip(request.video_path)
        audio = AudioFileClip(request.audio_path)
        
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
        
        os.makedirs(self._output_dir, exist_ok=True)
        output_path = os.path.join(
            self._output_dir, 
            f"aligned_shot_{request.shot_id}.mp4"
        )
        
        video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264",
            audio_codec="aac",
            logger=None
        )
        
        video.close()
        audio.close()
        
        self.logger.info(f"Aligned shot saved: {output_path} ({final_duration:.2f}s)")
        
        return AlignmentResult(
            shot_id=request.shot_id,
            output_path=output_path,
            final_duration=final_duration,
            strategy_used=request.strategy
        )
    
    def validate(self, request: AlignmentRequest) -> bool:
        """验证请求"""
        if not request.video_path or not request.audio_path:
            self.logger.error("Both video and audio paths are required")
            return False
        return True


# ============================================================================
# 流水线编排器
# ============================================================================


class ShotPipeline:
    """
    镜头处理流水线
    
    编排关键帧生成、评分、视频生成、音频生成和对齐的完整流程
    """
    
    def __init__(
        self,
        keyframe_generator: Optional[KeyframeGenerator] = None,
        vlm_scorer: Optional[VLMScorer] = None,
        video_generator: Optional[VideoGenerator] = None,
        audio_generator: Optional[AudioGenerator] = None,
        shot_aligner: Optional[ShotAligner] = None,
        enable_vlm_scoring: bool = False,
        min_vlm_score: float = 0.7,
        max_keyframe_retries: int = 3
    ):
        self.keyframe_generator = keyframe_generator or KeyframeGenerator()
        self.vlm_scorer = vlm_scorer or VLMScorer()
        self.video_generator = video_generator or VideoGenerator()
        self.audio_generator = audio_generator or AudioGenerator()
        self.shot_aligner = shot_aligner or ShotAligner()
        
        self.enable_vlm_scoring = enable_vlm_scoring
        self.min_vlm_score = min_vlm_score
        self.max_keyframe_retries = max_keyframe_retries
        
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
        alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP
    ) -> ShotArtifact:
        """
        处理单个镜头的完整流水线
        
        Args:
            shot_id: 镜头 ID
            visual_prompt: 视觉提示词
            dialogue: 对白文本（可选）
            reference_image_path: 参考图像路径（可选）
            camera_movement: 相机运动（可选）
            voice_id: 语音 ID（可选）
            target_duration: 目标时长
            alignment_strategy: 对齐策略
            
        Returns:
            镜头产出物
        """
        self.logger.info(f"Processing shot {shot_id}")
        
        keyframe_result = self._generate_keyframe_with_retry(
            shot_id=shot_id,
            prompt=visual_prompt,
            reference_image_path=reference_image_path
        )
        
        video_result = self.video_generator.process(VideoGenRequest(
            shot_id=shot_id,
            image_path=keyframe_result.image_path,
            motion_prompt=visual_prompt,
            camera_movement=camera_movement,
            duration=target_duration
        ))
        
        audio_path: Optional[str] = None
        audio_duration: float = 0.0
        
        if dialogue:
            audio_result = self.audio_generator.process(AudioGenRequest(
                shot_id=shot_id,
                text=dialogue,
                voice_id=voice_id
            ))
            audio_path = audio_result.audio_path
            audio_duration = audio_result.duration
            
            alignment_result = self.shot_aligner.process(AlignmentRequest(
                shot_id=shot_id,
                video_path=video_result.video_path,
                audio_path=audio_path,
                strategy=alignment_strategy
            ))
            final_video_path = alignment_result.output_path
            final_duration = alignment_result.final_duration
        else:
            final_video_path = video_result.video_path
            final_duration = video_result.duration
        
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
    
    def _generate_keyframe_with_retry(
        self,
        shot_id: int,
        prompt: str,
        reference_image_path: Optional[str] = None
    ) -> KeyframeResult:
        """生成关键帧，支持 VLM 评分重试"""
        for attempt in range(self.max_keyframe_retries):
            keyframe_result = self.keyframe_generator.process(KeyframeRequest(
                shot_id=shot_id,
                prompt=prompt,
                reference_image_path=reference_image_path
            ))
            
            if not self.enable_vlm_scoring:
                return keyframe_result
            
            score_result = self.vlm_scorer.process(VLMScoreRequest(
                image_path=keyframe_result.image_path,
                prompt=prompt
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
        alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP
    ) -> List[ShotArtifact]:
        """
        批量处理镜头
        
        Args:
            shots: 镜头配置列表
            alignment_strategy: 对齐策略
            
        Returns:
            镜头产出物列表
        """
        artifacts: List[ShotArtifact] = []
        
        for shot_config in shots:
            artifact = self.process_shot(
                shot_id=shot_config["shot_id"],
                visual_prompt=shot_config["visual_prompt"],
                dialogue=shot_config.get("dialogue"),
                reference_image_path=shot_config.get("reference_image_path"),
                camera_movement=shot_config.get("camera_movement"),
                voice_id=shot_config.get("voice_id"),
                target_duration=shot_config.get("duration", 4.0),
                alignment_strategy=alignment_strategy
            )
            artifacts.append(artifact)
        
        return artifacts
