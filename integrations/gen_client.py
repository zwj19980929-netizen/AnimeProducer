import logging
import io
import os
from PIL import Image

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("Please install the Google GenAI SDK: pip install google-genai")

from config import settings

logger = logging.getLogger(__name__)


class GenClient:
    """
    Real Image Generation Client using Google GenAI SDK.
    Strict mode: No mocks.
    """

    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        # 使用之前检测到的可用模型
        self.model_name = "imagen-4.0-generate-001"

        if not self.api_key:
            logger.error("GOOGLE_API_KEY is not set. Image generation will fail.")
            self.client = None
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI Client: {e}")
                self.client = None

    def generate_image(self, prompt: str, reference_image_path: str = None) -> bytes:
        """
        Generates a real image using Google's Imagen model.
        """
        if not self.client:
            raise RuntimeError("Google GenAI Client not initialized (Missing API Key).")

        enhanced_prompt = f"{prompt}, anime style, high quality, detailed, 2d animation cel shading"

        logger.info(f"🎨 Generating REAL image with {self.model_name}...")

        try:
            response = self.client.models.generate_images(
                model=self.model_name,
                prompt=enhanced_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    output_mime_type="image/png",
                )
            )

            if response.generated_images:
                image_entry = response.generated_images[0]

                # -------------------------------------------------------
                # 🛠️ 修复逻辑：更强壮的数据提取方式
                # -------------------------------------------------------

                # 1. 尝试直接从 GeneratedImage 条目获取 bytes
                if hasattr(image_entry, 'image_bytes') and image_entry.image_bytes:
                    return image_entry.image_bytes

                # 2. 检查 image 属性
                if hasattr(image_entry, 'image'):
                    img_obj = image_entry.image

                    # 情况 A: image 是 Google 的 types.Image 包装器 (有 image_bytes 属性)
                    if hasattr(img_obj, 'image_bytes') and img_obj.image_bytes:
                        return img_obj.image_bytes

                    # 情况 B: image 是 PIL.Image 对象 (这是旧版或某些调用的行为)
                    if isinstance(img_obj, Image.Image):
                        output_buffer = io.BytesIO()
                        img_obj.save(output_buffer, format="PNG")
                        return output_buffer.getvalue()

                    # 情况 C: image 是 types.Image 但没有 image_bytes，尝试手动处理
                    # 有些版本的 SDK 可能把数据藏在 .data 或其他地方，或者这是一个我们未知的对象
                    # 但通常上面的步骤已经能覆盖了。

                    # 最后尝试：如果它看起来像 PIL 但不是 PIL，打印类型以供调试
                    logger.warning(f"Unknown image object type: {type(img_obj)}")

                # 如果都拿不到，抛出详细错误
                raise RuntimeError(f"Could not extract bytes from response. Entry dir: {dir(image_entry)}")
            else:
                raise RuntimeError("API returned success but no images found.")

        except Exception as e:
            logger.error(f"❌ Google Image Generation Failed: {e}")
            raise e


# 单例实例
gen_client = GenClient()