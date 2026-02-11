"""
LoRA Manager - LoRA 训练流水线管理器

整合数据集生成、云端训练、模型加载的完整流程。
实现 agent.md 中的 "资产即模型" (Asset-as-Model) 策略。
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from config import settings
from core.database import engine
from core.models import Character, CharacterImage, CharacterLoRA, LoRATrainingStatus
from integrations.lora_trainer import (
    DatasetGenerator,
    DatasetImage,
    LoRATrainerFactory,
    TrainingConfig,
    TrainingProvider,
    dataset_generator,
)

logger = logging.getLogger(__name__)


class LoRAManager:
    """
    LoRA 训练流水线管理器

    完整流程：
    1. 从始祖图生成 20+ 张多角度素材
    2. 打包上传到 OSS
    3. 调用云端 API 训练 LoRA
    4. 轮询训练状态
    5. 下载并缓存 LoRA 权重
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self._dataset_generator = dataset_generator

    def start_lora_training(
        self,
        character_id: str,
        ancestor_image_path: Optional[str] = None,
        image_ids: Optional[List[str]] = None,
        use_selected_images: bool = True,
        num_dataset_images: int = 20,
        training_steps: int = 1000,
        provider: str = "fal",
        session: Optional[Session] = None
    ) -> CharacterLoRA:
        """
        启动角色 LoRA 训练流水线

        训练图片来源（按优先级）：
        1. 如果指定了 image_ids，使用这些图片
        2. 如果 use_selected_images=True，使用图片库中标记为训练的图片
        3. 如果图片不足，基于锚定图自动生成补充图片
        4. 如果没有锚定图，使用 ancestor_image_path 或参考图

        Args:
            character_id: 角色 ID
            ancestor_image_path: 始祖图路径（可选，默认使用锚定图或参考图）
            image_ids: 指定用于训练的图片 ID 列表
            use_selected_images: 是否使用图片库中标记为训练的图片
            num_dataset_images: 数据集图片数量（当需要额外生成时）
            training_steps: 训练步数
            provider: 训练提供商 (fal/replicate)
            session: 数据库会话

        Returns:
            CharacterLoRA: LoRA 训练记录
        """
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            # 1. 获取角色信息
            character = db.get(Character, character_id)
            if not character:
                raise ValueError(f"Character not found: {character_id}")

            # 2. 收集训练图片
            training_images: List[CharacterImage] = []

            # 2.1 如果指定了 image_ids，使用这些图片
            if image_ids:
                for img_id in image_ids:
                    img = db.get(CharacterImage, img_id)
                    if img and img.character_id == character_id:
                        training_images.append(img)

            # 2.2 如果使用标记的训练图片
            if use_selected_images and not training_images:
                statement = (
                    select(CharacterImage)
                    .where(CharacterImage.character_id == character_id)
                    .where(CharacterImage.is_selected_for_training == True)
                )
                training_images = list(db.exec(statement).all())

            logger.info(f"Found {len(training_images)} training images from gallery")

            # 3. 确定始祖图（用于生成补充图片）
            base_image_path = ancestor_image_path
            if not base_image_path:
                # 优先使用锚定图
                base_image_path = character.anchor_image_url or character.anchor_image_path
            if not base_image_path:
                # 其次使用参考图
                base_image_path = character.reference_image_url or character.reference_image_path

            if not base_image_path and not training_images:
                raise ValueError(f"No reference image or training images for character: {character_id}")

            # 4. 生成触发词
            trigger_word = self._generate_trigger_word(character.name)

            # 5. 创建 LoRA 记录
            lora = CharacterLoRA(
                character_id=character_id,
                base_model="flux",
                trigger_word=trigger_word,
                training_provider=provider,
                status=LoRATrainingStatus.GENERATING_DATASET,
                training_steps=training_steps,
                dataset_size=max(len(training_images), num_dataset_images),
            )
            db.add(lora)
            db.commit()
            db.refresh(lora)

            logger.info(f"Created LoRA training record: {lora.id}")

            # 6. 准备数据集
            dataset: List[DatasetImage] = []

            # 6.1 从图片库中的图片创建 DatasetImage
            for img in training_images:
                img_path = img.image_url or img.image_path
                if img_path:
                    # 读取图片数据
                    image_data = self._read_image_data(img_path)
                    if image_data:
                        # 使用图片的 prompt 作为 caption
                        caption = f"a photo of {trigger_word}"
                        if img.pose:
                            caption += f", {img.pose}"
                        if img.expression:
                            caption += f", {img.expression}"
                        if img.angle:
                            caption += f", {img.angle}"

                        dataset.append(DatasetImage(
                            image_data=image_data,
                            caption=caption,
                            filename=f"{img.id}.png"
                        ))

            logger.info(f"Prepared {len(dataset)} images from gallery")

            # 6.2 如果图片不足，生成补充图片
            if len(dataset) < num_dataset_images and base_image_path:
                num_to_generate = num_dataset_images - len(dataset)
                logger.info(f"Generating {num_to_generate} additional images...")

                character_prompt = character.appearance_prompt or character.prompt_base or character.name
                additional_dataset = self._dataset_generator.generate_dataset(
                    ancestor_image_path=base_image_path,
                    character_name=trigger_word,
                    character_prompt=character_prompt,
                    num_images=num_to_generate,
                )

                if additional_dataset:
                    dataset.extend(additional_dataset)

            if not dataset:
                lora.status = LoRATrainingStatus.FAILED
                lora.error_message = "Failed to prepare dataset"
                db.add(lora)
                db.commit()
                raise RuntimeError("Failed to prepare dataset")

            lora.status = LoRATrainingStatus.DATASET_READY
            lora.dataset_size = len(dataset)
            db.add(lora)
            db.commit()

            # 7. 打包并上传数据集
            logger.info("Packaging and uploading dataset...")
            lora.status = LoRATrainingStatus.UPLOADING
            db.add(lora)
            db.commit()

            zip_data = self._dataset_generator.package_dataset(dataset)
            dataset_url = self._upload_dataset(zip_data, lora.id)

            lora.dataset_url = dataset_url
            db.add(lora)
            db.commit()

            # 8. 启动训练
            logger.info(f"Starting LoRA training on {provider}...")
            lora.status = LoRATrainingStatus.TRAINING
            db.add(lora)
            db.commit()

            trainer = LoRATrainerFactory.get_trainer(TrainingProvider(provider))
            config = TrainingConfig(
                trigger_word=trigger_word,
                base_model="flux",
                steps=training_steps,
                learning_rate=lora.learning_rate,
                lora_rank=lora.lora_rank,
            )

            job = trainer.start_training(dataset_url, config)
            lora.training_job_id = job.job_id
            lora.training_metadata = {
                "job": job.metadata,
                "gallery_images": len(training_images),
                "generated_images": len(dataset) - len(training_images),
            }
            db.add(lora)
            db.commit()

            logger.info(f"LoRA training started: job_id={job.job_id}")
            return lora

        except Exception as e:
            logger.error(f"Error starting LoRA training: {e}")
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def _read_image_data(self, image_path: str) -> Optional[bytes]:
        """读取图片数据（支持本地路径和 URL）"""
        import requests

        try:
            if image_path.startswith(("http://", "https://")):
                # 从 URL 下载
                response = requests.get(image_path, timeout=30)
                response.raise_for_status()
                return response.content
            else:
                # 读取本地文件
                if os.path.exists(image_path):
                    with open(image_path, "rb") as f:
                        return f.read()
        except Exception as e:
            logger.warning(f"Failed to read image {image_path}: {e}")

        return None

    def check_training_status(
        self,
        lora_id: str,
        session: Optional[Session] = None
    ) -> CharacterLoRA:
        """
        检查 LoRA 训练状态

        Args:
            lora_id: LoRA 记录 ID
            session: 数据库会话

        Returns:
            CharacterLoRA: 更新后的 LoRA 记录
        """
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            lora = db.get(CharacterLoRA, lora_id)
            if not lora:
                raise ValueError(f"LoRA not found: {lora_id}")

            if lora.status not in [LoRATrainingStatus.TRAINING, LoRATrainingStatus.UPLOADING]:
                return lora

            if not lora.training_job_id:
                return lora

            # 查询训练状态
            trainer = LoRATrainerFactory.get_trainer(TrainingProvider(lora.training_provider))
            job = trainer.get_training_status(lora.training_job_id)

            lora.progress = job.progress
            lora.updated_at = datetime.utcnow()

            if job.status == "completed":
                lora.status = LoRATrainingStatus.READY
                lora.lora_url = job.lora_url
                logger.info(f"LoRA training completed: {lora.lora_url}")

            elif job.status == "failed":
                lora.status = LoRATrainingStatus.FAILED
                lora.error_message = job.error_message
                logger.error(f"LoRA training failed: {job.error_message}")

            db.add(lora)
            db.commit()
            db.refresh(lora)

            return lora

        finally:
            if should_close:
                db.close()

    def get_character_lora(
        self,
        character_id: str,
        session: Optional[Session] = None
    ) -> Optional[CharacterLoRA]:
        """
        获取角色的可用 LoRA

        Args:
            character_id: 角色 ID
            session: 数据库会话

        Returns:
            CharacterLoRA: 可用的 LoRA 记录，如果没有则返回 None
        """
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            # 查找状态为 READY 的最新 LoRA
            statement = (
                select(CharacterLoRA)
                .where(CharacterLoRA.character_id == character_id)
                .where(CharacterLoRA.status == LoRATrainingStatus.READY)
                .order_by(CharacterLoRA.created_at.desc())
            )
            lora = db.exec(statement).first()
            return lora

        finally:
            if should_close:
                db.close()

    def get_lora_for_shot(
        self,
        character_ids: List[str],
        session: Optional[Session] = None
    ) -> Dict[str, Optional[str]]:
        """
        获取镜头中所有角色的 LoRA URL

        Args:
            character_ids: 角色 ID 列表
            session: 数据库会话

        Returns:
            Dict[str, Optional[str]]: {character_id: lora_url}
        """
        result = {}
        for char_id in character_ids:
            lora = self.get_character_lora(char_id, session)
            result[char_id] = lora.lora_url if lora else None
        return result

    def _generate_trigger_word(self, character_name: str) -> str:
        """生成触发词"""
        # 清理名称，生成唯一触发词
        clean_name = character_name.lower().replace(" ", "_")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
        return f"ohwx_{clean_name}"

    def _upload_dataset(self, zip_data: bytes, lora_id: str) -> str:
        """上传数据集到 OSS"""
        from integrations.oss_service import is_oss_configured, require_oss

        if not is_oss_configured():
            # 云端训练需要公网可访问的 URL，本地路径无法使用
            raise RuntimeError(
                "OSS is not configured. LoRA training requires OSS to upload dataset. "
                "Please configure ALIYUN_OSS_BUCKET and related settings."
            )

        oss = require_oss()
        filename = f"lora_dataset_{lora_id}"
        url = oss.upload_bytes(zip_data, filename=filename, folder="lora_datasets", ext=".zip")
        logger.info(f"Dataset uploaded to OSS: {url}")
        return url

    def list_character_loras(
        self,
        character_id: str,
        session: Optional[Session] = None
    ) -> List[CharacterLoRA]:
        """列出角色的所有 LoRA 记录"""
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            statement = (
                select(CharacterLoRA)
                .where(CharacterLoRA.character_id == character_id)
                .order_by(CharacterLoRA.created_at.desc())
            )
            return list(db.exec(statement).all())

        finally:
            if should_close:
                db.close()

    def cancel_training(
        self,
        lora_id: str,
        session: Optional[Session] = None
    ) -> bool:
        """取消训练任务"""
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            lora = db.get(CharacterLoRA, lora_id)
            if not lora:
                raise ValueError(f"LoRA not found: {lora_id}")

            if lora.status != LoRATrainingStatus.TRAINING:
                return False

            if not lora.training_job_id:
                return False

            trainer = LoRATrainerFactory.get_trainer(TrainingProvider(lora.training_provider))
            success = trainer.cancel_training(lora.training_job_id)

            if success:
                lora.status = LoRATrainingStatus.FAILED
                lora.error_message = "Training cancelled by user"
                db.add(lora)
                db.commit()

            return success

        finally:
            if should_close:
                db.close()


# 便捷实例
lora_manager = LoRAManager()
