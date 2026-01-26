import logging
import io
import google.generativeai as genai
from config import settings

# 配置日志
logger = logging.getLogger(__name__)


class NanoBananaClient:
    """
    Image Generation Client.

    原名 NanoBananaClient，现已重构为使用 Google Imagen 3 模型。
    保留类名以维持与其他模块的兼容性。
    """

    def __init__(self):
        # 使用 settings 中的 GOOGLE_API_KEY 进行配置
        self.api_key = settings.GOOGLE_API_KEY

        if not self.api_key:
            logger.warning("GOOGLE_API_KEY is not set. Image generation will fail.")
        else:
            try:
                genai.configure(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to configure Google AI: {e}")

        # 指定 Google Imagen 模型版本
        # 常用模型: "imagen-3.0-generate-001" 或 "imagen-2"
        self.model_name = "imagen-3.0-generate-001"

    def generate_image(self, prompt: str, reference_image_path: str = None) -> bytes:
        """
        Generates an image using Google's Imagen model.

        Args:
            prompt: 图像描述提示词
            reference_image_path: (可选) 参考图路径，目前 Imagen API 对参考图的支持取决于具体版本，
                                基础版本主要基于文本生成。

        Returns:
            bytes: 图片的二进制数据 (PNG格式)
        """
        if not self.api_key:
            logger.error("Cannot generate image: GOOGLE_API_KEY is missing.")
            return None

        # 优化提示词，确保风格一致性 (可以根据需要调整)
        enhanced_prompt = f"{prompt}, anime style, high quality, detailed, 2d animation cel shading"

        logger.info(f"Generating image with Google Imagen ({self.model_name})...")
        logger.debug(f"Prompt: {enhanced_prompt}")

        try:
            # 实例化图片生成模型
            # 注意：如果您的 API Key 所在地区不支持 Imagen，这里可能会报错
            image_model = genai.ImageGenerationModel(self.model_name)

            # 调用生成接口
            response = image_model.generate_images(
                prompt=enhanced_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_only_high",
            )

            # 处理响应
            if response and response.images:
                generated_image = response.images[0]

                # 将图片保存到内存缓冲区并转为 bytes
                # Google SDK 的 GeneratedImage 对象通常有 save 方法或可以直接操作
                output_buffer = io.BytesIO()
                generated_image.save(output_buffer, "PNG")
                image_bytes = output_buffer.getvalue()

                logger.info("Image generated successfully.")
                return image_bytes
            else:
                logger.error("Google Imagen returned no images.")
                return None

        except Exception as e:
            logger.error(f"Error generating image with Google Imagen: {e}")
            # 如果是模型不存在的错误，可能是账号权限问题
            if "404" in str(e) or "not found" in str(e).lower():
                logger.error(f"Model '{self.model_name}' not found. Please check if your Google Cloud project has access to Imagen.")

                # 尝试降级或使用 mock (如果真的无法调用)
                # logger.info("Attempting fallback to mock image...")
                # return self._generate_mock_black_image()

            return None

    def _generate_mock_black_image(self) -> bytes:
        """生成一个 1x1 黑色像素图片作为最后的兜底（仅用于测试流程）"""
        return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'


# 单例实例
gen_client = NanoBananaClient()