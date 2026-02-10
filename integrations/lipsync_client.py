"""
Lip-Sync Client - 音频驱动人像动画模块

支持多种 Lip-Sync 技术：
- SadTalker: 基于 3DMM 的音频驱动人脸动画
- MuseTalk: 实时音频驱动口型同步
- LivePortrait: 高质量人像动画驱动

根据 TTS 音频重绘视频中人物的嘴部动作，实现口型同步。
"""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class LipSyncProvider(str, Enum):
    """Lip-Sync 提供商"""
    SADTALKER = "sadtalker"
    MUSETALK = "musetalk"
    LIVEPORTRAIT = "liveportrait"
    WAV2LIP = "wav2lip"


@dataclass
class LipSyncRequest:
    """Lip-Sync 请求"""
    video_path: str  # 输入视频路径或 URL
    audio_path: str  # 音频路径或 URL
    face_enhance: bool = True  # 是否增强面部质量
    face_region: Optional[Dict[str, int]] = None  # 面部区域 {x, y, w, h}
    expression_scale: float = 1.0  # 表情幅度缩放


@dataclass
class LipSyncResult:
    """Lip-Sync 结果"""
    video_path: str  # 输出视频路径或 URL
    duration: float
    provider: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseLipSyncClient(ABC):
    """Lip-Sync 客户端基类"""

    provider_name: str = "base"

    @abstractmethod
    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """处理 Lip-Sync 请求"""
        pass

    def health_check(self) -> bool:
        """检查服务是否可用"""
        return True


class SadTalkerClient(BaseLipSyncClient):
    """
    SadTalker Lip-Sync 客户端

    SadTalker 是一个基于 3DMM 的音频驱动人脸动画系统。
    支持通过 Replicate API 或本地部署调用。
    """

    provider_name = "sadtalker"

    def __init__(
        self,
        api_url: Optional[str] = None,
        use_replicate: bool = True
    ):
        self.api_url = api_url
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

    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """
        使用 SadTalker 处理 Lip-Sync

        Args:
            request: Lip-Sync 请求

        Returns:
            LipSyncResult: 处理结果
        """
        logger.info(f"[SadTalker] Processing lip-sync for video: {request.video_path}")

        if self.use_replicate:
            return self._process_via_replicate(request)
        else:
            return self._process_via_api(request)

    def _process_via_replicate(self, request: LipSyncRequest) -> LipSyncResult:
        """通过 Replicate API 处理"""
        replicate = self._get_replicate_client()

        # 准备输入
        # SadTalker 需要源图像和驱动音频
        # 我们从视频中提取第一帧作为源图像
        source_image = self._extract_first_frame(request.video_path)

        try:
            output = replicate.run(
                "cjwbw/sadtalker:3aa3dac9353cc4d6bd62a8f95957bd844003b401ca4e4a9b33baa574c549d376",
                input={
                    "source_image": open(source_image, "rb"),
                    "driven_audio": self._resolve_audio(request.audio_path),
                    "enhancer": "gfpgan" if request.face_enhance else None,
                    "preprocess": "crop",
                    "expression_scale": request.expression_scale,
                }
            )

            # 下载输出视频
            output_path = self._download_output(output)

            return LipSyncResult(
                video_path=output_path,
                duration=self._get_video_duration(output_path),
                provider=self.provider_name,
                metadata={
                    "source_image": source_image,
                    "face_enhance": request.face_enhance,
                }
            )
        finally:
            # 清理临时文件
            if os.path.exists(source_image):
                try:
                    os.unlink(source_image)
                except Exception:
                    pass

    def _process_via_api(self, request: LipSyncRequest) -> LipSyncResult:
        """通过自定义 API 处理"""
        import requests

        if not self.api_url:
            raise ValueError("API URL not configured for SadTalker")

        # 准备请求数据
        files = {
            "video": open(self._resolve_path(request.video_path), "rb"),
            "audio": open(self._resolve_path(request.audio_path), "rb"),
        }
        data = {
            "face_enhance": request.face_enhance,
            "expression_scale": request.expression_scale,
        }

        response = requests.post(
            f"{self.api_url}/process",
            files=files,
            data=data,
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        return LipSyncResult(
            video_path=result["video_url"],
            duration=result.get("duration", 0),
            provider=self.provider_name,
        )

    def _extract_first_frame(self, video_path: str) -> str:
        """从视频中提取第一帧"""
        from moviepy import VideoFileClip

        local_path = self._resolve_path(video_path)
        temp_image = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_image.close()

        clip = VideoFileClip(local_path)
        try:
            clip.save_frame(temp_image.name, t=0)
        finally:
            clip.close()

        return temp_image.name

    def _resolve_path(self, path: str) -> str:
        """解析路径，如果是 URL 则下载"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=60)
            response.raise_for_status()

            suffix = ".mp4" if "video" in response.headers.get("content-type", "") else ".mp3"
            temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        return path

    def _resolve_audio(self, audio_path: str):
        """解析音频路径"""
        if audio_path.startswith("http://") or audio_path.startswith("https://"):
            return audio_path
        return open(audio_path, "rb")

    def _download_output(self, output) -> str:
        """下载输出视频"""
        import requests

        if isinstance(output, str):
            url = output
        elif hasattr(output, "url"):
            url = output.url
        else:
            url = str(output)

        response = requests.get(url, timeout=120)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_file.write(response.content)
        temp_file.close()

        return temp_file.name

    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        from moviepy import VideoFileClip
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        return duration


class MuseTalkClient(BaseLipSyncClient):
    """
    MuseTalk Lip-Sync 客户端

    MuseTalk 是一个实时音频驱动口型同步系统。
    支持通过 API 调用。
    """

    provider_name = "musetalk"

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("MUSETALK_API_URL")

    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """处理 Lip-Sync 请求"""
        logger.info(f"[MuseTalk] Processing lip-sync for video: {request.video_path}")

        if not self.api_url:
            raise ValueError("MuseTalk API URL not configured")

        import requests

        files = {
            "video": self._open_file(request.video_path),
            "audio": self._open_file(request.audio_path),
        }
        data = {
            "face_enhance": request.face_enhance,
        }

        response = requests.post(
            f"{self.api_url}/lipsync",
            files=files,
            data=data,
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        return LipSyncResult(
            video_path=result["video_url"],
            duration=result.get("duration", 0),
            provider=self.provider_name,
        )

    def _open_file(self, path: str):
        """打开文件或从 URL 下载"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=60)
            response.raise_for_status()
            return response.content
        return open(path, "rb")


class LivePortraitClient(BaseLipSyncClient):
    """
    LivePortrait Lip-Sync 客户端

    LivePortrait 是一个高质量人像动画驱动系统。
    可以直接驱动静态图的五官表情，比 I2V 生成更可控。
    """

    provider_name = "liveportrait"

    def __init__(
        self,
        api_url: Optional[str] = None,
        use_replicate: bool = True
    ):
        self.api_url = api_url or os.getenv("LIVEPORTRAIT_API_URL")
        self.use_replicate = use_replicate

    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """处理 Lip-Sync 请求"""
        logger.info(f"[LivePortrait] Processing lip-sync for video: {request.video_path}")

        if self.use_replicate:
            return self._process_via_replicate(request)
        else:
            return self._process_via_api(request)

    def _process_via_replicate(self, request: LipSyncRequest) -> LipSyncResult:
        """通过 Replicate API 处理"""
        try:
            import replicate
        except ImportError:
            raise ImportError("请安装 replicate: pip install replicate")

        # 从视频提取第一帧作为源图像
        source_image = self._extract_first_frame(request.video_path)

        try:
            output = replicate.run(
                "fofr/live-portrait:067dd98cc3e5cb396c4a9efb4bba3eec6c4a9d271211325c477518fc6485e146",
                input={
                    "face_image": open(source_image, "rb"),
                    "driving_video": self._resolve_file(request.audio_path),
                    "live_portrait_dsize": 512,
                    "live_portrait_scale": request.expression_scale,
                    "video_select_every_n_frames": 1,
                    "live_portrait_lip_zero": True,
                    "live_portrait_relative": True,
                    "live_portrait_vx_ratio": 0,
                    "live_portrait_vy_ratio": -0.12,
                    "live_portrait_stitching": True,
                }
            )

            # 下载输出
            output_path = self._download_output(output)

            return LipSyncResult(
                video_path=output_path,
                duration=self._get_video_duration(output_path),
                provider=self.provider_name,
                metadata={
                    "source_image": source_image,
                }
            )
        finally:
            if os.path.exists(source_image):
                try:
                    os.unlink(source_image)
                except Exception:
                    pass

    def _process_via_api(self, request: LipSyncRequest) -> LipSyncResult:
        """通过自定义 API 处理"""
        import requests

        if not self.api_url:
            raise ValueError("LivePortrait API URL not configured")

        files = {
            "video": self._open_file(request.video_path),
            "audio": self._open_file(request.audio_path),
        }
        data = {
            "expression_scale": request.expression_scale,
        }

        response = requests.post(
            f"{self.api_url}/animate",
            files=files,
            data=data,
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        return LipSyncResult(
            video_path=result["video_url"],
            duration=result.get("duration", 0),
            provider=self.provider_name,
        )

    def _extract_first_frame(self, video_path: str) -> str:
        """从视频中提取第一帧"""
        from moviepy import VideoFileClip

        local_path = self._resolve_path(video_path)
        temp_image = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_image.close()

        clip = VideoFileClip(local_path)
        try:
            clip.save_frame(temp_image.name, t=0)
        finally:
            clip.close()

        return temp_image.name

    def _resolve_path(self, path: str) -> str:
        """解析路径"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=60)
            response.raise_for_status()

            suffix = ".mp4"
            temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        return path

    def _resolve_file(self, path: str):
        """解析文件"""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return open(path, "rb")

    def _open_file(self, path: str):
        """打开文件"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=60)
            response.raise_for_status()
            return response.content
        return open(path, "rb")

    def _download_output(self, output) -> str:
        """下载输出"""
        import requests

        if isinstance(output, str):
            url = output
        elif hasattr(output, "url"):
            url = output.url
        else:
            url = str(output)

        response = requests.get(url, timeout=120)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_file.write(response.content)
        temp_file.close()

        return temp_file.name

    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        from moviepy import VideoFileClip
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        return duration


class Wav2LipClient(BaseLipSyncClient):
    """
    Wav2Lip Lip-Sync 客户端

    Wav2Lip 是经典的音频驱动口型同步模型。
    """

    provider_name = "wav2lip"

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("WAV2LIP_API_URL")

    def process(self, request: LipSyncRequest) -> LipSyncResult:
        """处理 Lip-Sync 请求"""
        logger.info(f"[Wav2Lip] Processing lip-sync for video: {request.video_path}")

        if not self.api_url:
            # 尝试使用 Replicate
            return self._process_via_replicate(request)

        import requests

        files = {
            "video": self._open_file(request.video_path),
            "audio": self._open_file(request.audio_path),
        }

        response = requests.post(
            f"{self.api_url}/lipsync",
            files=files,
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        return LipSyncResult(
            video_path=result["video_url"],
            duration=result.get("duration", 0),
            provider=self.provider_name,
        )

    def _process_via_replicate(self, request: LipSyncRequest) -> LipSyncResult:
        """通过 Replicate 处理"""
        try:
            import replicate
        except ImportError:
            raise ImportError("请安装 replicate: pip install replicate")

        output = replicate.run(
            "devxpy/wav2lip:8d65e3f4f4298520e079198b493c25adfc43c058ffec924f2aefc8010ed25eef",
            input={
                "face": self._resolve_file(request.video_path),
                "audio": self._resolve_file(request.audio_path),
            }
        )

        output_path = self._download_output(output)

        return LipSyncResult(
            video_path=output_path,
            duration=self._get_video_duration(output_path),
            provider=self.provider_name,
        )

    def _resolve_file(self, path: str):
        """解析文件"""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return open(path, "rb")

    def _open_file(self, path: str):
        """打开文件"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=60)
            response.raise_for_status()
            return response.content
        return open(path, "rb")

    def _download_output(self, output) -> str:
        """下载输出"""
        import requests

        if isinstance(output, str):
            url = output
        elif hasattr(output, "url"):
            url = output.url
        else:
            url = str(output)

        response = requests.get(url, timeout=120)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_file.write(response.content)
        temp_file.close()

        return temp_file.name

    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        from moviepy import VideoFileClip
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        return duration


class LipSyncClientFactory:
    """Lip-Sync 客户端工厂"""

    _clients: Dict[LipSyncProvider, BaseLipSyncClient] = {}

    @classmethod
    def get_client(
        cls,
        provider: LipSyncProvider = LipSyncProvider.SADTALKER,
        **kwargs
    ) -> BaseLipSyncClient:
        """
        获取 Lip-Sync 客户端

        Args:
            provider: 提供商类型
            **kwargs: 客户端配置参数

        Returns:
            BaseLipSyncClient: Lip-Sync 客户端实例
        """
        if provider not in cls._clients:
            if provider == LipSyncProvider.SADTALKER:
                cls._clients[provider] = SadTalkerClient(**kwargs)
            elif provider == LipSyncProvider.MUSETALK:
                cls._clients[provider] = MuseTalkClient(**kwargs)
            elif provider == LipSyncProvider.LIVEPORTRAIT:
                cls._clients[provider] = LivePortraitClient(**kwargs)
            elif provider == LipSyncProvider.WAV2LIP:
                cls._clients[provider] = Wav2LipClient(**kwargs)
            else:
                raise ValueError(f"Unknown lip-sync provider: {provider}")

        return cls._clients[provider]

    @classmethod
    def get_default_client(cls) -> BaseLipSyncClient:
        """获取默认的 Lip-Sync 客户端"""
        from config import settings

        provider_name = getattr(settings, "LIPSYNC_PROVIDER", "sadtalker")
        try:
            provider = LipSyncProvider(provider_name.lower())
        except ValueError:
            logger.warning(f"Unknown lip-sync provider: {provider_name}, using sadtalker")
            provider = LipSyncProvider.SADTALKER

        return cls.get_client(provider)
