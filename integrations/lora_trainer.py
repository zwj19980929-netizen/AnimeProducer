"""
LoRA Trainer Client - 动态 LoRA 训练模块

支持通过云端 API 训练角色 LoRA 模型：
- Fal.ai: flux-lora-fast-training
- Replicate: ostris/flux-dev-lora-trainer

实现 "资产即模型" (Asset-as-Model) 策略，
让每个角色都有专属的 LoRA 模型以保持一致性。
"""

import io
import logging
import os
import tempfile
import time
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TrainingProvider(str, Enum):
    """训练提供商"""
    FAL = "fal"
    REPLICATE = "replicate"


@dataclass
class TrainingConfig:
    """LoRA 训练配置"""
    trigger_word: str  # 触发词
    base_model: str = "flux"  # flux, sdxl
    steps: int = 1000  # 训练步数
    learning_rate: float = 1e-4
    lora_rank: int = 16  # LoRA rank
    resolution: int = 512  # 训练分辨率
    batch_size: int = 1

    # 高级配置
    use_face_detection: bool = True  # 自动裁剪人脸
    caption_prefix: str = ""  # 标注前缀


@dataclass
class TrainingJob:
    """训练任务"""
    job_id: str
    provider: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    lora_url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetImage:
    """数据集图片"""
    image_data: bytes
    caption: str
    filename: str


class BaseLoRATrainer(ABC):
    """LoRA 训练器基类"""

    provider_name: str = "base"

    @abstractmethod
    def start_training(
        self,
        dataset_url: str,
        config: TrainingConfig
    ) -> TrainingJob:
        """启动训练任务"""
        pass

    @abstractmethod
    def get_training_status(self, job_id: str) -> TrainingJob:
        """获取训练状态"""
        pass

    @abstractmethod
    def cancel_training(self, job_id: str) -> bool:
        """取消训练任务"""
        pass

    def health_check(self) -> bool:
        """检查服务是否可用"""
        return True


class FalLoRATrainer(BaseLoRATrainer):
    """
    Fal.ai LoRA 训练器

    使用 fal-ai/flux-lora-fast-training 模型进行快速 LoRA 训练。
    文档: https://fal.ai/models/fal-ai/flux-lora-fast-training
    """

    provider_name = "fal"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FAL_KEY")
        self._client = None

    def _get_client(self):
        """获取 Fal 客户端"""
        if self._client is None:
            try:
                import fal_client
                if self.api_key:
                    os.environ["FAL_KEY"] = self.api_key
                self._client = fal_client
            except ImportError:
                raise ImportError("请安装 fal-client: pip install fal-client")
        return self._client

    def start_training(
        self,
        dataset_url: str,
        config: TrainingConfig
    ) -> TrainingJob:
        """
        启动 Fal.ai LoRA 训练

        Args:
            dataset_url: 数据集 ZIP 文件的 URL
            config: 训练配置

        Returns:
            TrainingJob: 训练任务信息
        """
        logger.info(f"[Fal] Starting LoRA training with trigger word: {config.trigger_word}")

        fal = self._get_client()

        # 构建训练参数
        training_args = {
            "images_data_url": dataset_url,
            "trigger_word": config.trigger_word,
            "steps": config.steps,
            "learning_rate": config.learning_rate,
            "rank": config.lora_rank,
            "caption_prefix": config.caption_prefix or f"a photo of {config.trigger_word}, ",
        }

        # 提交训练任务
        handler = fal.submit(
            "fal-ai/flux-lora-fast-training",
            arguments=training_args
        )

        request_id = handler.request_id
        logger.info(f"[Fal] Training job submitted: {request_id}")

        return TrainingJob(
            job_id=request_id,
            provider=self.provider_name,
            status="pending",
            progress=0.0,
            metadata={"training_args": training_args}
        )

    def get_training_status(self, job_id: str) -> TrainingJob:
        """获取训练状态"""
        fal = self._get_client()

        try:
            status = fal.status("fal-ai/flux-lora-fast-training", job_id, with_logs=True)

            if hasattr(status, "status"):
                if status.status == "COMPLETED":
                    # 获取结果
                    result = fal.result("fal-ai/flux-lora-fast-training", job_id)
                    lora_url = result.get("diffusers_lora_file", {}).get("url")

                    return TrainingJob(
                        job_id=job_id,
                        provider=self.provider_name,
                        status="completed",
                        progress=1.0,
                        lora_url=lora_url,
                        metadata={"result": result}
                    )
                elif status.status == "FAILED":
                    return TrainingJob(
                        job_id=job_id,
                        provider=self.provider_name,
                        status="failed",
                        error_message=str(getattr(status, "error", "Unknown error"))
                    )
                elif status.status == "IN_PROGRESS":
                    # 尝试从日志估算进度
                    progress = self._estimate_progress_from_logs(getattr(status, "logs", []))
                    return TrainingJob(
                        job_id=job_id,
                        provider=self.provider_name,
                        status="running",
                        progress=progress
                    )
                else:
                    return TrainingJob(
                        job_id=job_id,
                        provider=self.provider_name,
                        status="pending",
                        progress=0.0
                    )

            return TrainingJob(
                job_id=job_id,
                provider=self.provider_name,
                status="pending"
            )

        except Exception as e:
            logger.error(f"[Fal] Error getting training status: {e}")
            return TrainingJob(
                job_id=job_id,
                provider=self.provider_name,
                status="failed",
                error_message=str(e)
            )

    def _estimate_progress_from_logs(self, logs: List, total_steps: int = 1000) -> float:
        """从日志估算训练进度"""
        if not logs:
            return 0.1

        # 尝试从日志中解析步数
        for log in reversed(logs):
            log_text = str(log)
            if "step" in log_text.lower():
                # 尝试提取步数
                import re
                match = re.search(r"step\s*[:\s]*(\d+)", log_text, re.IGNORECASE)
                if match:
                    current_step = int(match.group(1))
                    return min(0.95, current_step / total_steps)

        return 0.5  # 默认返回 50%

    def cancel_training(self, job_id: str) -> bool:
        """取消训练任务"""
        fal = self._get_client()
        try:
            fal.cancel("fal-ai/flux-lora-fast-training", job_id)
            logger.info(f"[Fal] Training job cancelled: {job_id}")
            return True
        except Exception as e:
            logger.error(f"[Fal] Error cancelling training: {e}")
            return False


class ReplicateLoRATrainer(BaseLoRATrainer):
    """
    Replicate LoRA 训练器

    使用 ostris/flux-dev-lora-trainer 模型进行 LoRA 训练。
    """

    provider_name = "replicate"

    def __init__(self, api_token: Optional[str] = None, destination_owner: Optional[str] = None):
        self.api_token = api_token or os.getenv("REPLICATE_API_TOKEN")
        # destination_owner 是 Replicate 用户名，用于存储训练好的模型
        self.destination_owner = destination_owner or os.getenv("REPLICATE_USERNAME", "")
        self._client = None

    def _get_client(self):
        """获取 Replicate 客户端"""
        if self._client is None:
            try:
                import replicate
                if self.api_token:
                    os.environ["REPLICATE_API_TOKEN"] = self.api_token
                self._client = replicate
            except ImportError:
                raise ImportError("请安装 replicate: pip install replicate")
        return self._client

    def start_training(
        self,
        dataset_url: str,
        config: TrainingConfig
    ) -> TrainingJob:
        """启动 Replicate LoRA 训练"""
        logger.info(f"[Replicate] Starting LoRA training with trigger word: {config.trigger_word}")

        replicate = self._get_client()

        # 构建 destination
        # 如果没有配置 destination_owner，则不指定 destination（使用默认）
        destination = None
        if self.destination_owner:
            destination = f"{self.destination_owner}/lora-{config.trigger_word}"

        # 构建训练参数
        training_input = {
            "input_images": dataset_url,
            "trigger_word": config.trigger_word,
            "steps": config.steps,
            "learning_rate": config.learning_rate,
            "lora_rank": config.lora_rank,
            "resolution": config.resolution,
            "batch_size": config.batch_size,
            "autocaption": True,
            "autocaption_prefix": config.caption_prefix or f"a photo of {config.trigger_word}, ",
        }

        try:
            # 创建训练任务
            if destination:
                training = replicate.trainings.create(
                    version="ostris/flux-dev-lora-trainer:d995297071a44dcb72244e6c19462111649ec86a9646c32df56daa7f14801944",
                    input=training_input,
                    destination=destination
                )
            else:
                # 不指定 destination，让 Replicate 自动处理
                training = replicate.trainings.create(
                    version="ostris/flux-dev-lora-trainer:d995297071a44dcb72244e6c19462111649ec86a9646c32df56daa7f14801944",
                    input=training_input
                )

            logger.info(f"[Replicate] Training job created: {training.id}")

            return TrainingJob(
                job_id=training.id,
                provider=self.provider_name,
                status="pending",
                progress=0.0,
                metadata={"training_id": training.id, "destination": destination}
            )

        except Exception as e:
            logger.error(f"[Replicate] Failed to create training: {e}")
            raise

    def get_training_status(self, job_id: str) -> TrainingJob:
        """获取训练状态"""
        replicate = self._get_client()

        try:
            training = replicate.trainings.get(job_id)

            status_map = {
                "starting": "pending",
                "processing": "running",
                "succeeded": "completed",
                "failed": "failed",
                "canceled": "failed"
            }

            status = status_map.get(training.status, "pending")

            lora_url = None
            if status == "completed" and training.output:
                # Replicate 训练完成后会创建一个新的模型版本
                lora_url = training.output.get("weights")

            return TrainingJob(
                job_id=job_id,
                provider=self.provider_name,
                status=status,
                progress=1.0 if status == "completed" else 0.5,
                lora_url=lora_url,
                error_message=training.error if status == "failed" else None,
                metadata={"training": training.__dict__}
            )

        except Exception as e:
            logger.error(f"[Replicate] Error getting training status: {e}")
            return TrainingJob(
                job_id=job_id,
                provider=self.provider_name,
                status="failed",
                error_message=str(e)
            )

    def cancel_training(self, job_id: str) -> bool:
        """取消训练任务"""
        replicate = self._get_client()
        try:
            replicate.trainings.cancel(job_id)
            logger.info(f"[Replicate] Training job cancelled: {job_id}")
            return True
        except Exception as e:
            logger.error(f"[Replicate] Error cancelling training: {e}")
            return False


class DatasetGenerator:
    """
    数据集生成器

    从单张始祖图自动生成多角度、多表情的训练数据集。
    """

    def __init__(self):
        self._image_client = None

    def _get_image_client(self):
        """获取图像生成客户端"""
        if self._image_client is None:
            from integrations.provider_factory import ProviderFactory
            self._image_client = ProviderFactory.get_image_client()
        return self._image_client

    def generate_dataset(
        self,
        ancestor_image_path: str,
        character_name: str,
        character_prompt: str,
        num_images: int = 20,
        style_preset: Optional[str] = None
    ) -> List[DatasetImage]:
        """
        从始祖图生成训练数据集

        Args:
            ancestor_image_path: 始祖图路径或 URL
            character_name: 角色名称
            character_prompt: 角色基础提示词
            num_images: 生成图片数量
            style_preset: 风格预设

        Returns:
            List[DatasetImage]: 数据集图片列表
        """
        logger.info(f"Generating dataset for {character_name}: {num_images} images")

        image_client = self._get_image_client()
        dataset: List[DatasetImage] = []

        # 定义多样化的变体
        variations = self._get_variations()

        for i in range(num_images):
            variation = variations[i % len(variations)]

            # 构建变体提示词
            prompt = f"{character_prompt}, {variation['pose']}, {variation['expression']}, {variation['angle']}"
            if style_preset:
                prompt = f"{prompt}, {style_preset}"
            prompt = f"{prompt}, high quality, detailed"

            # 生成图片
            try:
                image_data = image_client.generate_image(
                    prompt=prompt,
                    reference_image_path=ancestor_image_path
                )

                if image_data:
                    # 生成标注
                    caption = f"a photo of {character_name}, {variation['pose']}, {variation['expression']}"

                    dataset.append(DatasetImage(
                        image_data=image_data,
                        caption=caption,
                        filename=f"{character_name}_{i+1:03d}.png"
                    ))
                    logger.info(f"Generated image {i+1}/{num_images}")

            except Exception as e:
                logger.error(f"Error generating image {i+1}: {e}")
                continue

        logger.info(f"Dataset generation complete: {len(dataset)} images")
        return dataset

    def _get_variations(self) -> List[Dict[str, str]]:
        """获取变体列表"""
        poses = [
            "standing", "sitting", "walking", "running",
            "arms crossed", "hands on hips", "waving",
            "looking back", "side view", "three-quarter view"
        ]

        expressions = [
            "neutral expression", "smiling", "laughing",
            "serious", "surprised", "thinking",
            "determined", "gentle smile", "confident"
        ]

        angles = [
            "front view", "side view", "three-quarter view",
            "slight low angle", "slight high angle",
            "profile view", "back view looking over shoulder"
        ]

        variations = []
        for pose in poses:
            for expr in expressions[:3]:  # 限制组合数量
                for angle in angles[:3]:
                    variations.append({
                        "pose": pose,
                        "expression": expr,
                        "angle": angle
                    })

        return variations

    def package_dataset(
        self,
        images: List[DatasetImage],
        output_path: Optional[str] = None
    ) -> bytes:
        """
        将数据集打包为 ZIP 文件

        Args:
            images: 数据集图片列表
            output_path: 可选的输出路径

        Returns:
            bytes: ZIP 文件内容
        """
        logger.info(f"Packaging dataset: {len(images)} images")

        # 创建内存中的 ZIP 文件
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img in images:
                # 添加图片
                zf.writestr(img.filename, img.image_data)

                # 添加标注文件
                caption_filename = img.filename.rsplit('.', 1)[0] + '.txt'
                zf.writestr(caption_filename, img.caption)

        zip_data = zip_buffer.getvalue()

        # 如果指定了输出路径，保存到文件
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(zip_data)
            logger.info(f"Dataset saved to: {output_path}")

        return zip_data


class LoRATrainerFactory:
    """LoRA 训练器工厂"""

    _trainers: Dict[TrainingProvider, BaseLoRATrainer] = {}

    @classmethod
    def get_trainer(
        cls,
        provider: TrainingProvider = TrainingProvider.FAL,
        **kwargs
    ) -> BaseLoRATrainer:
        """获取 LoRA 训练器"""
        if provider not in cls._trainers:
            if provider == TrainingProvider.FAL:
                cls._trainers[provider] = FalLoRATrainer(**kwargs)
            elif provider == TrainingProvider.REPLICATE:
                cls._trainers[provider] = ReplicateLoRATrainer(**kwargs)
            else:
                raise ValueError(f"Unknown training provider: {provider}")

        return cls._trainers[provider]

    @classmethod
    def get_default_trainer(cls) -> BaseLoRATrainer:
        """获取默认训练器"""
        from config import settings

        provider_name = getattr(settings, "LORA_TRAINING_PROVIDER", "fal")
        try:
            provider = TrainingProvider(provider_name.lower())
        except ValueError:
            logger.warning(f"Unknown LoRA training provider: {provider_name}, using fal")
            provider = TrainingProvider.FAL

        return cls.get_trainer(provider)


# 便捷实例
dataset_generator = DatasetGenerator()
