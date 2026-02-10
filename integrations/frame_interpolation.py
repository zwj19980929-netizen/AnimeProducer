"""
Frame Interpolation - 帧插值模块

使用 RIFE (Real-Time Intermediate Flow Estimation) 等算法进行帧插值，
让慢放视频更流畅，避免"鬼畜"感。

支持的插值算法：
- RIFE: 实时中间流估计，高质量帧插值
- FILM: Frame Interpolation for Large Motion
"""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class InterpolationMethod(str, Enum):
    """插值方法"""
    RIFE = "rife"
    FILM = "film"
    SIMPLE = "simple"  # 简单的帧复制


@dataclass
class InterpolationRequest:
    """帧插值请求"""
    video_path: str  # 输入视频路径或 URL
    target_fps: int = 60  # 目标帧率
    multiplier: int = 2  # 帧率倍数 (2x, 4x, 8x)
    method: InterpolationMethod = InterpolationMethod.RIFE


@dataclass
class InterpolationResult:
    """帧插值结果"""
    video_path: str  # 输出视频路径或 URL
    original_fps: float
    output_fps: float
    duration: float
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseInterpolator(ABC):
    """帧插值器基类"""

    method_name: str = "base"

    @abstractmethod
    def interpolate(self, request: InterpolationRequest) -> InterpolationResult:
        """执行帧插值"""
        pass


class RIFEInterpolator(BaseInterpolator):
    """
    RIFE 帧插值器

    RIFE (Real-Time Intermediate Flow Estimation) 是一个高效的帧插值算法，
    可以在保持高质量的同时实现实时插值。
    """

    method_name = "rife"

    def __init__(
        self,
        api_url: Optional[str] = None,
        use_replicate: bool = True
    ):
        self.api_url = api_url or os.getenv("RIFE_API_URL")
        self.use_replicate = use_replicate

    def interpolate(self, request: InterpolationRequest) -> InterpolationResult:
        """
        使用 RIFE 进行帧插值

        Args:
            request: 插值请求

        Returns:
            InterpolationResult: 插值结果
        """
        logger.info(f"[RIFE] Interpolating video: {request.video_path}")
        logger.info(f"[RIFE] Target: {request.multiplier}x frame rate")

        if self.use_replicate:
            return self._interpolate_via_replicate(request)
        elif self.api_url:
            return self._interpolate_via_api(request)
        else:
            # 使用本地 moviepy 实现简单插值
            return self._interpolate_local(request)

    def _interpolate_via_replicate(self, request: InterpolationRequest) -> InterpolationResult:
        """通过 Replicate API 进行插值"""
        try:
            import replicate
        except ImportError:
            logger.warning("Replicate not installed, falling back to local interpolation")
            return self._interpolate_local(request)

        video_file = self._resolve_file(request.video_path)

        try:
            output = replicate.run(
                "pollinations/rife-video-interpolation:7e0e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e",
                input={
                    "video": video_file,
                    "multiplier": request.multiplier,
                }
            )

            output_path = self._download_output(output)
            original_fps, duration = self._get_video_info(request.video_path)

            return InterpolationResult(
                video_path=output_path,
                original_fps=original_fps,
                output_fps=original_fps * request.multiplier,
                duration=duration,
                metadata={
                    "method": self.method_name,
                    "multiplier": request.multiplier,
                }
            )
        except Exception as e:
            logger.warning(f"Replicate interpolation failed: {e}, falling back to local")
            return self._interpolate_local(request)

    def _interpolate_via_api(self, request: InterpolationRequest) -> InterpolationResult:
        """通过自定义 API 进行插值"""
        import requests

        files = {
            "video": self._open_file(request.video_path),
        }
        data = {
            "multiplier": request.multiplier,
            "target_fps": request.target_fps,
        }

        response = requests.post(
            f"{self.api_url}/interpolate",
            files=files,
            data=data,
            timeout=600
        )
        response.raise_for_status()

        result = response.json()
        return InterpolationResult(
            video_path=result["video_url"],
            original_fps=result.get("original_fps", 24),
            output_fps=result.get("output_fps", 48),
            duration=result.get("duration", 0),
        )

    def _interpolate_local(self, request: InterpolationRequest) -> InterpolationResult:
        """
        本地帧插值实现

        使用 moviepy 进行简单的帧率调整。
        这不是真正的 RIFE 插值，但可以作为后备方案。
        """
        from moviepy import VideoFileClip

        local_path = self._resolve_path(request.video_path)
        clip = VideoFileClip(local_path)

        try:
            original_fps = clip.fps or 24
            target_fps = original_fps * request.multiplier

            # 创建临时输出文件
            temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_output.close()

            # 使用更高的帧率写入
            # 注意：这只是简单的帧复制，不是真正的插值
            clip.write_videofile(
                temp_output.name,
                fps=target_fps,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )

            return InterpolationResult(
                video_path=temp_output.name,
                original_fps=original_fps,
                output_fps=target_fps,
                duration=clip.duration,
                metadata={
                    "method": "simple_fps_increase",
                    "note": "Not true RIFE interpolation, just frame duplication",
                }
            )
        finally:
            clip.close()

    def _resolve_path(self, path: str) -> str:
        """解析路径"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=120)
            response.raise_for_status()

            temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
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
            response = requests.get(path, timeout=120)
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

    def _get_video_info(self, video_path: str) -> tuple:
        """获取视频信息"""
        from moviepy import VideoFileClip

        local_path = self._resolve_path(video_path)
        clip = VideoFileClip(local_path)
        fps = clip.fps or 24
        duration = clip.duration
        clip.close()

        return fps, duration


class FILMInterpolator(BaseInterpolator):
    """
    FILM 帧插值器

    FILM (Frame Interpolation for Large Motion) 专门处理大运动场景的帧插值。
    """

    method_name = "film"

    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("FILM_API_URL")

    def interpolate(self, request: InterpolationRequest) -> InterpolationResult:
        """使用 FILM 进行帧插值"""
        logger.info(f"[FILM] Interpolating video: {request.video_path}")

        if not self.api_url:
            logger.warning("FILM API not configured, falling back to RIFE")
            rife = RIFEInterpolator()
            return rife.interpolate(request)

        import requests

        files = {
            "video": self._open_file(request.video_path),
        }
        data = {
            "multiplier": request.multiplier,
        }

        response = requests.post(
            f"{self.api_url}/interpolate",
            files=files,
            data=data,
            timeout=600
        )
        response.raise_for_status()

        result = response.json()
        return InterpolationResult(
            video_path=result["video_url"],
            original_fps=result.get("original_fps", 24),
            output_fps=result.get("output_fps", 48),
            duration=result.get("duration", 0),
            metadata={"method": self.method_name}
        )

    def _open_file(self, path: str):
        """打开文件"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=120)
            response.raise_for_status()
            return response.content
        return open(path, "rb")


class SimpleInterpolator(BaseInterpolator):
    """
    简单帧插值器

    使用帧复制实现简单的帧率提升。
    """

    method_name = "simple"

    def interpolate(self, request: InterpolationRequest) -> InterpolationResult:
        """简单帧插值"""
        from moviepy import VideoFileClip

        logger.info(f"[Simple] Interpolating video: {request.video_path}")

        local_path = self._resolve_path(request.video_path)
        clip = VideoFileClip(local_path)

        try:
            original_fps = clip.fps or 24
            target_fps = min(request.target_fps, original_fps * request.multiplier)

            temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_output.close()

            clip.write_videofile(
                temp_output.name,
                fps=target_fps,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )

            return InterpolationResult(
                video_path=temp_output.name,
                original_fps=original_fps,
                output_fps=target_fps,
                duration=clip.duration,
                metadata={"method": self.method_name}
            )
        finally:
            clip.close()

    def _resolve_path(self, path: str) -> str:
        """解析路径"""
        if path.startswith("http://") or path.startswith("https://"):
            import requests
            response = requests.get(path, timeout=120)
            response.raise_for_status()

            temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
        return path


class FrameInterpolatorFactory:
    """帧插值器工厂"""

    _interpolators: Dict[InterpolationMethod, BaseInterpolator] = {}

    @classmethod
    def get_interpolator(
        cls,
        method: InterpolationMethod = InterpolationMethod.RIFE,
        **kwargs
    ) -> BaseInterpolator:
        """
        获取帧插值器

        Args:
            method: 插值方法
            **kwargs: 配置参数

        Returns:
            BaseInterpolator: 帧插值器实例
        """
        if method not in cls._interpolators:
            if method == InterpolationMethod.RIFE:
                cls._interpolators[method] = RIFEInterpolator(**kwargs)
            elif method == InterpolationMethod.FILM:
                cls._interpolators[method] = FILMInterpolator(**kwargs)
            elif method == InterpolationMethod.SIMPLE:
                cls._interpolators[method] = SimpleInterpolator()
            else:
                raise ValueError(f"Unknown interpolation method: {method}")

        return cls._interpolators[method]

    @classmethod
    def get_default_interpolator(cls) -> BaseInterpolator:
        """获取默认的帧插值器"""
        return cls.get_interpolator(InterpolationMethod.RIFE)


def smooth_slow_motion(
    video_path: str,
    speed_factor: float,
    method: InterpolationMethod = InterpolationMethod.RIFE
) -> str:
    """
    平滑慢放视频

    先进行帧插值，再进行慢放，避免帧率不足导致的卡顿。

    Args:
        video_path: 输入视频路径
        speed_factor: 速度因子 (0.5 = 2倍慢放)
        method: 插值方法

    Returns:
        str: 输出视频路径
    """
    from moviepy import VideoFileClip

    logger.info(f"Smooth slow motion: speed_factor={speed_factor}")

    # 计算需要的帧率倍数
    # 如果慢放 2 倍，需要 2 倍的帧率来保持流畅
    multiplier = max(2, int(1 / speed_factor))

    # 先进行帧插值
    interpolator = FrameInterpolatorFactory.get_interpolator(method)
    interpolation_result = interpolator.interpolate(InterpolationRequest(
        video_path=video_path,
        multiplier=multiplier,
        method=method
    ))

    # 再进行慢放
    interpolated_clip = VideoFileClip(interpolation_result.video_path)

    try:
        slowed_clip = interpolated_clip.with_speed_scaled(speed_factor)

        temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_output.close()

        slowed_clip.write_videofile(
            temp_output.name,
            fps=24,  # 输出标准帧率
            codec="libx264",
            audio_codec="aac",
            logger=None
        )

        logger.info(f"Smooth slow motion complete: {temp_output.name}")
        return temp_output.name
    finally:
        interpolated_clip.close()
        slowed_clip.close()
        # 清理中间文件
        if os.path.exists(interpolation_result.video_path):
            try:
                os.unlink(interpolation_result.video_path)
            except Exception:
                pass
