import logging
import io
import base64
import os
from typing import Optional
from PIL import Image

# [核心变化] 引入新的 SDK 包名
from google import genai
from google.genai import types

from config import settings

# 配置日志
logger = logging.getLogger(__name__)


class GenClient:
    """
    Image Generation Client using the new Google GenAI SDK (v1.0+).
    Wraps the 'google.genai' library to access Imagen 3 models.
    """

    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.client = None

        if not self.api_key:
            logger.warning("GOOGLE_API_KEY is not set. Image generation will fail.")
        else:
            try:
                # [核心变化] 新版客户端初始化方式
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI Client: {e}")

        # 指定 Imagen 模型版本
        self.model_name = "imagen-3.0-generate-001"

    def _load_reference_image(self, reference_image_path: str) -> Optional[bytes]:
        """加载参考图片并返回字节数据"""
        if not reference_image_path or not os.path.exists(reference_image_path):
            return None
        try:
            with Image.open(reference_image_path) as img:
                output_buffer = io.BytesIO()
                img.save(output_buffer, format="PNG")
                return output_buffer.getvalue()
        except Exception as e:
            logger.warning(f"Failed to load reference image: {e}")
            return None

    def _build_prompt_with_reference(self, prompt: str, reference_image_path: Optional[str]) -> str:
        """
        构建包含参考图片描述的提示词
        注意：Imagen 3 目前不支持直接的图像输入，所以我们通过增强提示词来保持一致性
        """
        enhanced_prompt = f"{prompt}, anime style, high quality, detailed, 2d animation cel shading"

        if reference_image_path and os.path.exists(reference_image_path):
            # 添加一致性提示，告诉模型保持角色特征
            enhanced_prompt = f"maintain character consistency, {enhanced_prompt}"
            logger.debug(f"Reference image provided: {reference_image_path}")

        return enhanced_prompt

    def generate_image(self, prompt: str, reference_image_path: str = None) -> Optional[bytes]:
        """
        Generates an image using Google's Imagen model via new SDK.

        Args:
            prompt: 图像生成提示词
            reference_image_path: 参考图片路径（用于保持角色一致性）

        Returns:
            生成的图片字节数据，失败返回 None
        """
        if not self.client:
            logger.error("Cannot generate image: Client not initialized.")
            return None

        # 构建增强提示词（包含参考图片的一致性提示）
        enhanced_prompt = self._build_prompt_with_reference(prompt, reference_image_path)

        logger.info(f"Generating image with Google GenAI ({self.model_name})...")
        logger.debug(f"Prompt: {enhanced_prompt}")
        if reference_image_path:
            logger.debug(f"Reference image: {reference_image_path}")

        try:
            # [核心变化] 新版生成接口调用方式
            response = self.client.models.generate_image(
                model=self.model_name,
                prompt=enhanced_prompt,
                config=types.GenerateImageConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="BLOCK_ONLY_HIGH",
                )
            )

            # [核心变化] 处理新版响应结构
            # response.generated_images 是一个列表
            if response.generated_images:
                image_data = response.generated_images[0]

                # 新版 SDK 通常返回 PIL Image 对象或者包含 image_bytes 的对象
                # 如果是 PIL Image 对象:
                if hasattr(image_data, 'image'):
                    # 这是一个 GeneratedImage 对象，里面有个 .image (PIL Image)
                    pil_img = image_data.image
                    output_buffer = io.BytesIO()
                    pil_img.save(output_buffer, format="PNG")
                    return output_buffer.getvalue()

                # 如果直接是 bytes
                elif isinstance(image_data, bytes):
                    return image_data

                # 兜底：检查是否有 image_bytes 属性
                elif hasattr(image_data, 'image_bytes'):
                    return image_data.image_bytes

                else:
                    logger.error(f"Unknown image data format: {type(image_data)}")
                    return None
            else:
                logger.error("Google Imagen returned no images.")
                return None

        except Exception as e:
            logger.error(f"Error generating image with Google GenAI: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                logger.error(f"Model '{self.model_name}' not found. Check your API key permissions.")
            return None


# 单例实例
gen_client = GenClient()


# 占位符类，防止 ImportError
class NanoBananaClient:
    def __init__(self):
        logger.warning("NanoBananaClient is deprecated and replaced by Google GenAI.")

    def generate_image(self, *args, **kwargs):
        logger.error("NanoBananaClient is disabled.")
        return None