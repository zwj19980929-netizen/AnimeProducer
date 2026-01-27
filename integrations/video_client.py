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
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.model_name = "veo-2.0-generate-001" # 或者 veo-3.0-generate-001
        self.client = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Google Video Client 初始化失败: {e}")

    def image_to_video(self, image_path: str, camera_movement: str = "static", duration: float = 3.0) -> bytes:
        # 🟢 调试：如果你在日志里看不到这一行，说明代码没更新！
        logger.info(f"🎬 [VEO API] 准备为图片生成真实视频: {image_path}")

        if not self.client:
            raise RuntimeError("API Key 未配置，无法生成真实视频。")

        try:
            from PIL import Image
            pil_image = Image.open(image_path)

            prompt = f"Anime style animation, {camera_movement} camera motion, high quality."

            # 调用真实的 Google API
            logger.info(f"📡 正在请求 Google Veo (模型: {self.model_name})...")
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
            logger.error(f"❌ 视频生成 API 调用失败: {e}")
            raise e

    def save_video(self, video_data: bytes, output_path: str) -> bool:
        try:
            if not video_data or len(video_data) < 100: # 视频不可能只有几十个字节
                raise ValueError("收到的视频数据过小或为空，可能已损坏。")

            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "wb") as f:
                f.write(video_data)
                f.flush()
                os.fsync(f.fileno()) # 强制写入磁盘，防止 Windows 缓存导致文件损坏

            logger.info(f"✅ 真实视频已保存: {output_path} (大小: {len(video_data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"💾 保存视频失败: {e}")
            return False

video_client = VideoClient()