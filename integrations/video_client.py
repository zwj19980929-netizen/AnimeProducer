import logging
import os
import time
from pathlib import Path
from typing import Optional, Literal

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("请运行: pip install google-genai")

from config import settings

logger = logging.getLogger(__name__)


class VideoClient:
    """Google Veo 视频生成客户端。"""

    def __init__(self):
        """初始化客户端。"""
        self.api_key = settings.GOOGLE_API_KEY
        self.model_name = "veo-2.0-generate-001"
        self.client = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Google Video Client 初始化失败: {e}")

    def image_to_video(self, image_path: str, camera_movement: str = "static", duration: float = 3.0) -> bytes:
        """将图片转换为视频。"""
        logger.info(f"[VEO API] 准备从图片生成视频: {image_path}")

        if not self.client:
            raise RuntimeError("API Key 未配置，无法生成视频。")

        try:
            from PIL import Image
            pil_image = Image.open(image_path)

            prompt = f"Anime style animation, {camera_movement} camera motion, high quality."

            logger.info(f"正在请求 Google Veo (模型: {self.model_name})...")
            response = self.client.models.generate_videos(
                model=self.model_name,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    image=pil_image,
                    number_of_videos=1,
                )
            )

            if response.generated_videos:
                video_data = response.generated_videos[0]
                if hasattr(video_data, 'video_bytes'):
                    return video_data.video_bytes
                elif hasattr(video_data, 'video'):
                    return video_data.video

            raise RuntimeError("Google API 未返回视频数据。")

        except Exception as e:
            logger.error(f"视频生成 API 调用失败: {e}")
            raise e

    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        image_url: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """生成视频（符合 BaseVideoClient 接口）。

        Args:
            image_path: 本地图片路径
            motion_prompt: 运动提示词
            duration: 视频时长
            image_url: 图片 URL（Google Veo 不支持，会被忽略）
        """
        # Google Veo 需要本地文件，如果只有 URL 需要先下载
        if image_url and not image_path:
            import requests
            import tempfile
            logger.info(f"从 URL 下载图片: {image_url[:80]}...")
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                f.write(response.content)
                image_path = f.name

        camera_movement = motion_prompt or "smooth camera movement"
        return self.image_to_video(image_path, camera_movement, duration)

    def save_video(self, video_data: bytes, output_path: str) -> bool:
        """保存视频到文件。"""
        try:
            if not video_data or len(video_data) < 100:
                raise ValueError("收到的视频数据过小或为空，可能已损坏。")

            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "wb") as f:
                f.write(video_data)
                f.flush()
                os.fsync(f.fileno())

            logger.info(f"视频已保存: {output_path} (大小: {len(video_data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"保存视频失败: {e}")
            return False


video_client = VideoClient()