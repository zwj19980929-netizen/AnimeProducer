import logging
import io
import base64
from PIL import Image

# 引入新的 SDK 包名
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
                # 新版客户端初始化方式
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI Client: {e}")

        # 指定 Imagen 模型版本
        self.model_name = "imagen-3.0-generate-001"

    def generate_image(self, prompt: str, reference_image_path: str = None) -> bytes:
        """
        Generates an image using Google's Imagen model via new SDK.
        """
        if not self.client:
            logger.error("Cannot generate image: Client not initialized.")
            return None

        # 优化提示词
        enhanced_prompt = f"{prompt}, anime style, high quality, detailed, 2d animation cel shading"

        logger.info(f"Generating image with Google GenAI ({self.model_name})...")
        logger.debug(f"Prompt: {enhanced_prompt}")

        try:
            # [修复核心] 方法名和配置类必须是复数形式 (generate_images)
            response = self.client.models.generate_images(
                model=self.model_name,
                prompt=enhanced_prompt,
                config=types.GenerateImagesConfig(  # <-- 注意这里也是 GenerateImagesConfig
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="BLOCK_ONLY_HIGH",
                )
            )

            # 处理响应
            if response.generated_images:
                image_data = response.generated_images[0]

                # SDK 返回的对象通常包含 image 属性 (PIL Image)
                if hasattr(image_data, 'image'):
                    pil_img = image_data.image
                    output_buffer = io.BytesIO()
                    pil_img.save(output_buffer, format="PNG")
                    return output_buffer.getvalue()

                # 或者直接是 bytes
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