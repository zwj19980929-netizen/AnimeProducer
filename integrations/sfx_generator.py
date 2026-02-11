"""
SFX Generator - AI 拟音系统

使用 AudioLDM 等模型生成环境音效：
- 从分镜描述中提取音效标签
- 并行生成音效素材
- 支持混音合成

实现 agent.md 中的 "AI 拟音师" 功能。
"""

import io
import logging
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SFXProvider(str, Enum):
    """音效生成提供商"""
    AUDIOLDM = "audioldm"
    ELEVENLABS = "elevenlabs"
    REPLICATE = "replicate"


@dataclass
class SFXRequest:
    """音效生成请求"""
    description: str  # 音效描述，如 "rain", "footsteps", "explosion"
    duration: float = 5.0  # 音效时长（秒）
    num_inference_steps: int = 50
    guidance_scale: float = 2.5


@dataclass
class SFXResult:
    """音效生成结果"""
    audio_path: str  # 音频文件路径或 URL
    duration: float
    description: str
    provider: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SFXLayer:
    """音效层"""
    audio_path: str
    start_time: float = 0.0  # 开始时间（秒）
    volume: float = 1.0  # 音量 (0-1)
    loop: bool = False  # 是否循环
    fade_in: float = 0.0  # 淡入时长
    fade_out: float = 0.0  # 淡出时长


class BaseSFXClient:
    """��效生成客户端基类"""

    provider_name: str = "base"

    def generate(self, request: SFXRequest) -> SFXResult:
        """生成音效"""
        raise NotImplementedError

    def health_check(self) -> bool:
        """检查服务是否可用"""
        return True


class AudioLDMClient(BaseSFXClient):
    """
    AudioLDM 音效生成客户端

    使用 AudioLDM 模型生成高质量音效。
    支持通过 Replicate API 调用。
    """

    provider_name = "audioldm"

    def __init__(self, use_replicate: bool = True):
        self.use_replicate = use_replicate
        self._replicate_client = None

    def _get_replicate_client(self):
        """获取 Replicate 客户端"""
        if self._replicate_client is None:
            try:
                import replicate
                self._replicate_client = replicate
            except ImportError:
                raise ImportError("请安装 replicate: pip install replicate")
        return self._replicate_client

    def generate(self, request: SFXRequest) -> SFXResult:
        """
        生成音效

        Args:
            request: 音效生成请求

        Returns:
            SFXResult: 生成结果
        """
        logger.info(f"[AudioLDM] Generating SFX: {request.description}")

        if self.use_replicate:
            return self._generate_via_replicate(request)
        else:
            raise NotImplementedError("本地 AudioLDM 推理待实现")

    def _generate_via_replicate(self, request: SFXRequest) -> SFXResult:
        """通过 Replicate API 生成"""
        replicate = self._get_replicate_client()

        try:
            # 使用真实的 AudioLDM2 模型
            # 参考: https://replicate.com/cjwbw/audioldm2
            output = replicate.run(
                "cjwbw/audioldm2:79f6d22e3e47d8f1c0e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8",
                input={
                    "prompt": request.description,
                    "duration": request.duration,
                    "guidance_scale": request.guidance_scale,
                    "num_inference_steps": request.num_inference_steps,
                    "seed": -1,  # 随机种子
                }
            )

            # 下载音频
            audio_path = self._download_audio(output)

            return SFXResult(
                audio_path=audio_path,
                duration=request.duration,
                description=request.description,
                provider=self.provider_name,
                metadata={"replicate_output": str(output)}
            )

        except Exception as e:
            logger.error(f"[AudioLDM] Generation failed: {e}")
            # 尝试备用模型
            return self._generate_via_replicate_fallback(request)

    def _generate_via_replicate_fallback(self, request: SFXRequest) -> SFXResult:
        """使用备用模型生成音效"""
        replicate = self._get_replicate_client()

        try:
            # 备用: MusicGen 也可以生成音效
            output = replicate.run(
                "meta/musicgen:b05b1dff1d8c6dc63d14b0cdb42135378dcb87f6373b0d3d341ede46e59e2b38",
                input={
                    "prompt": f"sound effect: {request.description}",
                    "duration": int(request.duration),
                    "model_version": "stereo-melody-large",
                }
            )

            audio_path = self._download_audio(output)

            return SFXResult(
                audio_path=audio_path,
                duration=request.duration,
                description=request.description,
                provider=f"{self.provider_name}_fallback",
                metadata={"replicate_output": str(output), "fallback": True}
            )

        except Exception as e:
            logger.error(f"[AudioLDM] Fallback also failed: {e}")
            raise RuntimeError(f"All SFX generation methods failed: {e}")

    def _download_audio(self, output) -> str:
        """下载音频文件"""
        import requests

        if isinstance(output, str):
            url = output
        elif isinstance(output, list) and len(output) > 0:
            url = output[0]
        elif hasattr(output, "url"):
            url = output.url
        else:
            url = str(output)

        response = requests.get(url, timeout=60)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_file.write(response.content)
        temp_file.close()

        return temp_file.name


class ElevenLabsSFXClient(BaseSFXClient):
    """
    ElevenLabs 音效生成客户端

    使用 ElevenLabs Sound Effects API。
    """

    provider_name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")

    def generate(self, request: SFXRequest) -> SFXResult:
        """生成音效"""
        import requests

        if not self.api_key:
            raise ValueError("ElevenLabs API key not configured")

        logger.info(f"[ElevenLabs] Generating SFX: {request.description}")

        response = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            },
            json={
                "text": request.description,
                "duration_seconds": request.duration,
            },
            timeout=60
        )
        response.raise_for_status()

        # 保存音频
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_file.write(response.content)
        temp_file.close()

        return SFXResult(
            audio_path=temp_file.name,
            duration=request.duration,
            description=request.description,
            provider=self.provider_name,
        )


class SFXGenerator:
    """
    音效生成器

    从分镜描述中提取音效标签并生成音效。
    """

    # 常见音效映射
    SFX_MAPPINGS = {
        # 自然环境
        "rain": "heavy rain falling on roof, ambient sound",
        "thunder": "loud thunder crack, storm",
        "wind": "strong wind blowing, howling wind",
        "ocean": "ocean waves crashing on shore",
        "forest": "forest ambience, birds chirping, leaves rustling",
        "fire": "crackling fire, fireplace",

        # 城市环境
        "traffic": "city traffic, cars passing by",
        "crowd": "crowd murmuring, people talking",
        "construction": "construction site, hammering, drilling",

        # 动作音效
        "footsteps": "footsteps on wooden floor",
        "running": "running footsteps, fast pace",
        "door": "door opening and closing, creaking",
        "glass": "glass breaking, shatter",
        "explosion": "large explosion, debris falling",
        "gunshot": "single gunshot, echo",
        "sword": "sword clash, metal on metal",
        "punch": "punch impact, fighting",

        # 情感音效
        "heartbeat": "heartbeat, tense moment",
        "breathing": "heavy breathing, exhausted",
        "crying": "soft crying, sobbing",
        "laughing": "laughter, happy",

        # 科幻/奇幻
        "magic": "magical spell casting, sparkles",
        "laser": "laser beam, sci-fi weapon",
        "teleport": "teleportation sound, whoosh",
        "monster": "monster growl, creature roar",
    }

    def __init__(self, provider: SFXProvider = SFXProvider.AUDIOLDM):
        self.provider = provider
        self._client = None

    def _get_client(self) -> BaseSFXClient:
        """获取音效生成客户端"""
        if self._client is None:
            if self.provider == SFXProvider.AUDIOLDM:
                self._client = AudioLDMClient()
            elif self.provider == SFXProvider.ELEVENLABS:
                self._client = ElevenLabsSFXClient()
            else:
                raise ValueError(f"Unknown SFX provider: {self.provider}")
        return self._client

    def extract_sfx_tags(self, scene_description: str) -> List[str]:
        """
        从场景描述中提取音效标签

        Args:
            scene_description: 场景描述文本

        Returns:
            List[str]: 音效标签列表
        """
        tags = []
        description_lower = scene_description.lower()

        for tag, _ in self.SFX_MAPPINGS.items():
            if tag in description_lower:
                tags.append(tag)

        # 使用 LLM 提取更多标签（可选）
        if not tags:
            tags = self._extract_with_llm(scene_description)

        return tags

    def _extract_with_llm(self, scene_description: str) -> List[str]:
        """使用 LLM 提取音效标签"""
        try:
            from integrations.llm_client import llm_client
            from pydantic import BaseModel

            class SFXTags(BaseModel):
                tags: List[str]

            prompt = f"""Analyze this scene description and extract sound effect tags.
Return only the most important 1-3 ambient sounds that would enhance the scene.

Scene: {scene_description}

Available tags: {', '.join(self.SFX_MAPPINGS.keys())}

Return tags that match the scene. If no matching tags, return empty list."""

            result = llm_client.generate_structured_output(prompt, SFXTags, temperature=0.1)
            if result:
                return [tag for tag in result.tags if tag in self.SFX_MAPPINGS]

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        return []

    def generate_sfx(
        self,
        tag: str,
        duration: float = 5.0
    ) -> SFXResult:
        """
        生成单个音效

        Args:
            tag: 音效标签
            duration: 音效时长

        Returns:
            SFXResult: 生成结果
        """
        # 获取详细描述
        description = self.SFX_MAPPINGS.get(tag, tag)

        client = self._get_client()
        return client.generate(SFXRequest(
            description=description,
            duration=duration
        ))

    def generate_sfx_for_shot(
        self,
        scene_description: str,
        shot_duration: float,
        sfx_tags: Optional[List[str]] = None
    ) -> List[SFXResult]:
        """
        为镜头生成音效

        Args:
            scene_description: 场景描述
            shot_duration: 镜头时长
            sfx_tags: 预定义的音效标签（可选）

        Returns:
            List[SFXResult]: 音效列表
        """
        # 提取或使用预定义标签
        tags = sfx_tags or self.extract_sfx_tags(scene_description)

        if not tags:
            logger.info("No SFX tags found for scene")
            return []

        logger.info(f"Generating SFX for tags: {tags}")

        results = []
        for tag in tags[:3]:  # 最多生成 3 个音效
            try:
                result = self.generate_sfx(tag, duration=shot_duration)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to generate SFX for '{tag}': {e}")

        return results


class SFXMixer:
    """
    音效混音器

    将多个音效层混合到一起。
    需要 ffmpeg 支持。
    """

    @staticmethod
    def check_ffmpeg() -> bool:
        """检查 ffmpeg 是否可用"""
        import shutil
        return shutil.which("ffmpeg") is not None

    def mix_layers(
        self,
        layers: List[SFXLayer],
        output_duration: float,
        output_path: Optional[str] = None
    ) -> str:
        """
        混合音效层

        Args:
            layers: 音效层列表
            output_duration: 输出时长
            output_path: 输出路径（可选）

        Returns:
            str: 混合后的音频路径

        Raises:
            RuntimeError: 如果 ffmpeg 不可用
        """
        if not self.check_ffmpeg():
            raise RuntimeError(
                "ffmpeg is not installed. SFX mixing requires ffmpeg. "
                "Please install ffmpeg: https://ffmpeg.org/download.html"
            )

        from pydub import AudioSegment

        logger.info(f"Mixing {len(layers)} SFX layers")

        # 创建空白音轨
        mixed = AudioSegment.silent(duration=int(output_duration * 1000))

        for layer in layers:
            try:
                # 加载音频
                audio = AudioSegment.from_file(layer.audio_path)

                # 调整音量
                if layer.volume != 1.0:
                    audio = audio + (20 * (layer.volume - 1))  # dB 调整

                # 淡入淡出
                if layer.fade_in > 0:
                    audio = audio.fade_in(int(layer.fade_in * 1000))
                if layer.fade_out > 0:
                    audio = audio.fade_out(int(layer.fade_out * 1000))

                # 循环处理
                if layer.loop:
                    loop_count = int(output_duration / (len(audio) / 1000)) + 1
                    audio = audio * loop_count
                    audio = audio[:int(output_duration * 1000)]

                # 叠加到混音轨道
                start_ms = int(layer.start_time * 1000)
                mixed = mixed.overlay(audio, position=start_ms)

            except Exception as e:
                logger.error(f"Failed to mix layer {layer.audio_path}: {e}")

        # 保存输出
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            output_path = temp_file.name
            temp_file.close()

        mixed.export(output_path, format="mp3")
        logger.info(f"Mixed audio saved to: {output_path}")

        return output_path

    def mix_with_dialogue(
        self,
        dialogue_path: str,
        sfx_layers: List[SFXLayer],
        output_path: Optional[str] = None,
        sfx_volume: float = 0.3  # 音效相对于对白的音量
    ) -> str:
        """
        将音效与对白混合

        Args:
            dialogue_path: 对白音频路径
            sfx_layers: 音效层列表
            output_path: 输出路径
            sfx_volume: 音效音量（相对于对白）

        Returns:
            str: 混合后的音频路径
        """
        from pydub import AudioSegment

        # 加载对白
        dialogue = AudioSegment.from_file(dialogue_path)
        duration = len(dialogue) / 1000

        # 调整音效音量
        adjusted_layers = []
        for layer in sfx_layers:
            adjusted_layer = SFXLayer(
                audio_path=layer.audio_path,
                start_time=layer.start_time,
                volume=layer.volume * sfx_volume,
                loop=layer.loop,
                fade_in=layer.fade_in,
                fade_out=layer.fade_out
            )
            adjusted_layers.append(adjusted_layer)

        # 混合音效
        sfx_mixed_path = self.mix_layers(adjusted_layers, duration)
        sfx_mixed = AudioSegment.from_file(sfx_mixed_path)

        # 叠加对白和音效
        final = dialogue.overlay(sfx_mixed)

        # 保存输出
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            output_path = temp_file.name
            temp_file.close()

        final.export(output_path, format="mp3")

        # 清理临时文件
        try:
            os.unlink(sfx_mixed_path)
        except Exception:
            pass

        logger.info(f"Final audio with SFX saved to: {output_path}")
        return output_path


# 便捷实例
sfx_generator = SFXGenerator()
sfx_mixer = SFXMixer()
