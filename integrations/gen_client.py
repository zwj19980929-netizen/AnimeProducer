import logging
import io
import base64
import os
from typing import Optional
from PIL import Image

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)


class GenClient:
    """图像生成客户端，使用 Google GenAI SDK (v1.0+) 访问 Imagen 模型。"""

    def __init__(self):
        """初始化客户端。"""
        self.api_key = settings.GOOGLE_API_KEY
        self.client = None

        if not self.api_key:
            logger.warning("GOOGLE_API_KEY is not set. Image generation will fail.")
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI Client: {e}")

        self.model_name = "imagen-4.0-generate-001"

    def _load_reference_image(self, reference_image_path: str) -> Optional[bytes]:
        """加载参考图片并返回字节数据。"""
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
        """构建包含参考图片描述的提示词。"""
        enhanced_prompt = f"{prompt}, anime style, high quality, detailed, 2d animation cel shading"

        if reference_image_path and os.path.exists(reference_image_path):
            enhanced_prompt = f"maintain character consistency, {enhanced_prompt}"
            logger.debug(f"Reference image provided: {reference_image_path}")

        return enhanced_prompt

    def generate_image(
        self,
        prompt: str,
        reference_image_path: str = None,
        style_preset: str = None,
        negative_prompt: str = None,
        seed: int = None,
        **kwargs
    ) -> Optional[bytes]:
        """使用 Google Imagen 模型生成图像。

        Args:
            prompt: 主提示词
            reference_image_path: 参考图路径（可选）
            style_preset: 风格预设（可选）
            negative_prompt: 负面提示词，描述不想要的内容（可选）
            seed: 随机种子，用于复现结果（可选）
        """
        if not self.client:
            logger.error("Cannot generate image: Client not initialized.")
            return None

        enhanced_prompt = self._build_prompt_with_reference(prompt, reference_image_path)

        if style_preset:
            enhanced_prompt = f"{enhanced_prompt}, {style_preset}"

        logger.info(f"Generating image with Google GenAI ({self.model_name})...")
        logger.debug(f"Prompt: {enhanced_prompt}")
        if negative_prompt:
            logger.debug(f"Negative prompt: {negative_prompt}")
        if seed is not None:
            logger.debug(f"Seed: {seed}")
        if reference_image_path:
            logger.debug(f"Reference image: {reference_image_path}")

        try:
            # 构建配置
            config_params = {
                "number_of_images": 1,
                "aspect_ratio": "1:1",
                "safety_filter_level": "BLOCK_LOW_AND_ABOVE",
            }

            # Google Imagen API 不支持 negative_prompt 参数
            # 将 negative_prompt 融入主 prompt 中
            final_prompt = enhanced_prompt
            if negative_prompt:
                final_prompt = f"{enhanced_prompt}. Avoid: {negative_prompt}"
                logger.debug(f"Negative prompt merged into main prompt")

            # 注意：Google Imagen API 不支持 seed 参数
            # seed 参数仅用于日志记录，不传递给 API

            response = self.client.models.generate_images(
                model=self.model_name,
                prompt=final_prompt,
                config=types.GenerateImagesConfig(**config_params)
            )

            if response.generated_images:
                image_data = response.generated_images[0]

                # 优先使用 image_bytes（原始字节数据）
                if hasattr(image_data, 'image_bytes') and image_data.image_bytes:
                    return image_data.image_bytes

                # 如果有 image 属性，可能是 PIL Image 或 Google SDK Image 对象
                if hasattr(image_data, 'image') and image_data.image is not None:
                    img_obj = image_data.image
                    # 检查是否是 PIL Image
                    if isinstance(img_obj, Image.Image):
                        output_buffer = io.BytesIO()
                        img_obj.save(output_buffer, format="PNG")
                        return output_buffer.getvalue()
                    # Google SDK Image 对象可能有 _pil_image 属性
                    elif hasattr(img_obj, '_pil_image'):
                        output_buffer = io.BytesIO()
                        img_obj._pil_image.save(output_buffer, format="PNG")
                        return output_buffer.getvalue()
                    # 尝试直接转换为 bytes
                    elif hasattr(img_obj, 'data'):
                        return img_obj.data
                    else:
                        # 尝试用 PIL 打开（如果是类文件对象）
                        try:
                            output_buffer = io.BytesIO()
                            pil_img = Image.open(io.BytesIO(bytes(img_obj)))
                            pil_img.save(output_buffer, format="PNG")
                            return output_buffer.getvalue()
                        except Exception:
                            logger.error(f"Cannot convert image object: {type(img_obj)}")
                            return None

                elif isinstance(image_data, bytes):
                    return image_data

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


gen_client = GenClient()


class NanoBananaClient:
    """已弃用的占位符类。"""

    def __init__(self):
        """初始化。"""
        logger.warning("NanoBananaClient is deprecated and replaced by Google GenAI.")

    def generate_image(self, *args, **kwargs):
        """生成图像（已禁用）。"""
        logger.error("NanoBananaClient is disabled.")
        return None