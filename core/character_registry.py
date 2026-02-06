"""Character Registry - 角色资产注册系统

管理角色的参考图像、特征标签和一致性验证。
用于在多镜头生成中保持角色外观的一致性。
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class CharacterAsset:
    """角色资产"""
    character_id: str                                    # 角色唯一标识
    name: str                                            # 角色名称
    description: str = ""                                # 角色描述
    reference_images: List[str] = field(default_factory=list)  # 多角度参考图路径
    style_tags: List[str] = field(default_factory=list)        # 风格标签 (Danbooru 格式)
    negative_tags: List[str] = field(default_factory=list)     # 负面标签
    voice_id: Optional[str] = None                       # TTS 语音 ID
    lora_path: Optional[str] = None                      # 角色 LoRA 权重路径
    face_embedding: Optional[Any] = None                 # 人脸特征向量 (用于一致性验证)
    metadata: Dict[str, Any] = field(default_factory=dict)     # 其他元数据

    def get_primary_reference(self) -> Optional[str]:
        """获取主参考图"""
        if self.reference_images:
            return self.reference_images[0]
        return None

    def get_prompt_tags(self) -> str:
        """获取用于提示词的标签字符串"""
        return ", ".join(self.style_tags) if self.style_tags else ""

    def get_negative_tags(self) -> str:
        """获取负面标签字符串"""
        return ", ".join(self.negative_tags) if self.negative_tags else ""


class CharacterRegistry:
    """
    角色注册表

    管理项目中所有角色的资产，支持：
    - 角色注册和查询
    - 根据姿态/场景选择最合适的参考图
    - 角色一致性验证
    """

    def __init__(self, project_id: Optional[str] = None):
        """
        初始化角色注册表

        Args:
            project_id: 项目 ID，用于确定角色资产存储路径
        """
        self._characters: Dict[str, CharacterAsset] = {}
        self._project_id = project_id
        self._face_encoder = None  # 延迟加载人脸编码器

        if project_id:
            self._characters_dir = settings.get_project_dir(project_id) / "characters"
        else:
            self._characters_dir = settings.CHARACTERS_DIR

    def register(self, asset: CharacterAsset) -> None:
        """
        注册角色资产

        Args:
            asset: 角色资产对象
        """
        # 验证参考图是否存在
        valid_refs = []
        for ref_path in asset.reference_images:
            if os.path.exists(ref_path):
                valid_refs.append(ref_path)
            else:
                logger.warning(f"Reference image not found: {ref_path}")

        asset.reference_images = valid_refs

        self._characters[asset.character_id] = asset
        logger.info(
            f"Registered character: {asset.name} (id={asset.character_id}, "
            f"refs={len(asset.reference_images)}, tags={len(asset.style_tags)})"
        )

    def get(self, character_id: str) -> Optional[CharacterAsset]:
        """
        获取角色资产

        Args:
            character_id: 角色 ID

        Returns:
            角色资产，如果不存在则返回 None
        """
        return self._characters.get(character_id)

    def get_by_name(self, name: str) -> Optional[CharacterAsset]:
        """
        根据名称获取角色资产

        Args:
            name: 角色名称

        Returns:
            角色资产，如果不存在则返回 None
        """
        for asset in self._characters.values():
            if asset.name.lower() == name.lower():
                return asset
        return None

    def list_characters(self) -> List[CharacterAsset]:
        """列出所有已注册的角色"""
        return list(self._characters.values())

    def get_reference_for_shot(
        self,
        character_id: str,
        pose_hint: Optional[str] = None,
        scene_type: Optional[str] = None
    ) -> Optional[str]:
        """
        根据姿态/场景提示选择最合适的参考图

        Args:
            character_id: 角色 ID
            pose_hint: 姿态提示 (如 "front", "side", "back", "close-up")
            scene_type: 场景类型 (如 "action", "dialogue", "emotional")

        Returns:
            最合适的参考图路径，如果没有则返回 None
        """
        asset = self.get(character_id)
        if not asset or not asset.reference_images:
            return None

        # 如果只有一张参考图，直接返回
        if len(asset.reference_images) == 1:
            return asset.reference_images[0]

        # 根据姿态提示选择参考图
        # 假设参考图命名规范: character_front.png, character_side.png 等
        if pose_hint:
            pose_hint_lower = pose_hint.lower()
            for ref_path in asset.reference_images:
                filename = os.path.basename(ref_path).lower()
                if pose_hint_lower in filename:
                    return ref_path

        # 默认返回第一张（主参考图）
        return asset.reference_images[0]

    def get_combined_tags_for_shot(
        self,
        character_ids: List[str]
    ) -> tuple:
        """
        获取多个角色的组合标签

        Args:
            character_ids: 角色 ID 列表

        Returns:
            (positive_tags, negative_tags) 元组
        """
        positive_tags: List[str] = []
        negative_tags: List[str] = []

        for char_id in character_ids:
            asset = self.get(char_id)
            if asset:
                positive_tags.extend(asset.style_tags)
                negative_tags.extend(asset.negative_tags)

        # 去重
        positive_tags = list(dict.fromkeys(positive_tags))
        negative_tags = list(dict.fromkeys(negative_tags))

        return positive_tags, negative_tags

    def unregister(self, character_id: str) -> bool:
        """
        注销角色

        Args:
            character_id: 角色 ID

        Returns:
            是否成功注销
        """
        if character_id in self._characters:
            del self._characters[character_id]
            logger.info(f"Unregistered character: {character_id}")
            return True
        return False

    def clear(self) -> None:
        """清空所有角色"""
        self._characters.clear()
        logger.info("Cleared all characters from registry")

    def load_from_directory(self, directory: Optional[str] = None) -> int:
        """
        从目录加载角色资产

        期望目录结构:
        characters/
        ├── character_1/
        │   ├── config.json  # 角色配置
        │   ├── front.png    # 正面参考图
        │   ├── side.png     # 侧面参考图
        │   └── ...
        ├── character_2/
        │   └── ...

        Args:
            directory: 角色目录，默认使用 _characters_dir

        Returns:
            加载的角色数量
        """
        import json

        directory = directory or str(self._characters_dir)
        if not os.path.exists(directory):
            logger.warning(f"Characters directory not found: {directory}")
            return 0

        loaded_count = 0

        for char_dir_name in os.listdir(directory):
            char_dir = os.path.join(directory, char_dir_name)
            if not os.path.isdir(char_dir):
                continue

            config_path = os.path.join(char_dir, "config.json")
            if not os.path.exists(config_path):
                logger.debug(f"No config.json found in {char_dir}, skipping")
                continue

            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # 收集参考图
                reference_images = []
                for filename in os.listdir(char_dir):
                    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        reference_images.append(os.path.join(char_dir, filename))

                asset = CharacterAsset(
                    character_id=config.get("id", char_dir_name),
                    name=config.get("name", char_dir_name),
                    description=config.get("description", ""),
                    reference_images=reference_images,
                    style_tags=config.get("style_tags", []),
                    negative_tags=config.get("negative_tags", []),
                    voice_id=config.get("voice_id"),
                    lora_path=config.get("lora_path"),
                    metadata=config.get("metadata", {})
                )

                self.register(asset)
                loaded_count += 1

            except Exception as e:
                logger.error(f"Failed to load character from {char_dir}: {e}")

        logger.info(f"Loaded {loaded_count} characters from {directory}")
        return loaded_count

    def save_character(self, character_id: str, directory: Optional[str] = None) -> bool:
        """
        保存角色配置到目录

        Args:
            character_id: 角色 ID
            directory: 保存目录，默认使用 _characters_dir

        Returns:
            是否成功保存
        """
        import json

        asset = self.get(character_id)
        if not asset:
            logger.error(f"Character not found: {character_id}")
            return False

        directory = directory or str(self._characters_dir)
        char_dir = os.path.join(directory, character_id)
        os.makedirs(char_dir, exist_ok=True)

        config = {
            "id": asset.character_id,
            "name": asset.name,
            "description": asset.description,
            "style_tags": asset.style_tags,
            "negative_tags": asset.negative_tags,
            "voice_id": asset.voice_id,
            "lora_path": asset.lora_path,
            "metadata": asset.metadata
        }

        config_path = os.path.join(char_dir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved character config: {config_path}")
        return True


def create_character_from_description(
    character_id: str,
    name: str,
    description: str,
    reference_image: Optional[str] = None
) -> CharacterAsset:
    """
    从描述创建角色资产的便捷函数

    自动从描述中提取 Danbooru 风格标签。

    Args:
        character_id: 角色 ID
        name: 角色名称
        description: 角色描述（自然语言）
        reference_image: 参考图路径

    Returns:
        CharacterAsset 对象
    """
    from core.prompt_translator import prompt_translator

    # 使用提示词翻译器提取标签
    structured = prompt_translator.translate(description, include_quality_tags=False)

    reference_images = [reference_image] if reference_image else []

    return CharacterAsset(
        character_id=character_id,
        name=name,
        description=description,
        reference_images=reference_images,
        style_tags=structured.tags,
        negative_tags=[]
    )


# 全局实例
character_registry = CharacterRegistry()
