"""
Seedance Pipeline - Seedance 视频生成流水线

将 Seedance 集成到现有的渲染流程中，支持：
- 图生视频（首帧模式）保持角色一致性
- 有声视频生成（1.5 Pro）
- 参考图模式（1-4张）

当前版本：Seedance 1.5 Pro
未来版本：Seedance 2.0（支持音色克隆）
"""
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import settings
from integrations.seedance_client import (
    SeedanceClient,
    SeedanceModel,
    SeedanceRatio,
    SeedanceResult,
    get_seedance_client
)

logger = logging.getLogger(__name__)


@dataclass
class SeedanceShotRequest:
    """Seedance 镜头生成请求"""
    shot_id: int
    visual_prompt: str
    dialogue: Optional[str] = None
    character_id: Optional[str] = None
    character_image: Optional[str] = None  # 角色参考图路径/URL
    duration: int = 5
    camera_movement: Optional[str] = None
    scene_description: Optional[str] = None
    ratio: str = "16:9"


@dataclass
class SeedanceShotResult:
    """Seedance 镜头生成结果"""
    shot_id: int
    video_path: str
    audio_path: Optional[str] = None
    duration: float = 0.0
    has_dialogue: bool = False
    video_url: Optional[str] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SeedancePipeline:
    """
    Seedance 生成流水线

    核心功能：
    1. 图生视频（首帧）保持角色视觉一致性
    2. 有声视频生成（对白注入 prompt）
    3. 多镜头序列生成
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        model: Optional[SeedanceModel] = None
    ):
        self.project_id = project_id
        self.output_dir = output_dir or str(settings.OUTPUT_DIR)
        self.model = model

        # Seedance 客户端
        self.client = get_seedance_client()
        if model:
            self.client.default_model = model

    def generate_shot(
        self,
        request: SeedanceShotRequest,
        voice_sample: Optional[str] = None
    ) -> SeedanceShotResult:
        """
        生成单个镜头

        Args:
            request: 镜头请求
            voice_sample: 音色样本路径（预留给 2.0）

        Returns:
            SeedanceShotResult
        """
        # 构建完整 prompt
        prompt_parts = []

        if request.scene_description:
            prompt_parts.append(f"场景：{request.scene_description}")

        prompt_parts.append(request.visual_prompt)

        if request.camera_movement:
            prompt_parts.append(f"镜头：{request.camera_movement}")

        full_prompt = "\n".join(prompt_parts)

        # 调用 Seedance
        result = self.client.generate_shot_with_voice(
            prompt=full_prompt,
            character_image=request.character_image,
            voice_sample=voice_sample,
            dialogue=request.dialogue,
            duration=request.duration,
            ratio=request.ratio
        )

        # 保存结果
        os.makedirs(self.output_dir, exist_ok=True)
        video_path = os.path.join(self.output_dir, f"shot_{request.shot_id}.mp4")

        if result.video_data:
            with open(video_path, "wb") as f:
                f.write(result.video_data)
        elif result.video_url:
            import requests
            resp = requests.get(result.video_url, timeout=120)
            resp.raise_for_status()
            with open(video_path, "wb") as f:
                f.write(resp.content)

        # 提取音频（如果有对白）
        audio_path = None
        if request.dialogue:
            try:
                from moviepy import VideoFileClip
                clip = VideoFileClip(video_path)
                if clip.audio:
                    audio_path = os.path.join(self.output_dir, f"shot_{request.shot_id}_audio.mp3")
                    clip.audio.write_audiofile(audio_path, logger=None)
                clip.close()
            except Exception as e:
                logger.warning(f"提取音频失败: {e}")

        return SeedanceShotResult(
            shot_id=request.shot_id,
            video_path=video_path,
            audio_path=audio_path,
            duration=result.duration,
            has_dialogue=bool(request.dialogue),
            video_url=result.video_url,
            metadata=result.metadata
        )

    def generate_multi_shot_sequence(
        self,
        requests: List[SeedanceShotRequest],
        character_images: Optional[Dict[str, str]] = None,
        voice_samples: Optional[Dict[str, str]] = None
    ) -> List[SeedanceShotResult]:
        """
        生成多镜头序列

        Args:
            requests: 镜头请求列表
            character_images: 角色参考图字典 {character_id: image_path}
            voice_samples: 音色样本字典 {character_id: sample_path}（预留给 2.0）

        Returns:
            SeedanceShotResult 列表
        """
        character_images = character_images or {}
        voice_samples = voice_samples or {}
        results = []

        for req in requests:
            # 获取角色参考图
            if req.character_id and req.character_id in character_images:
                req.character_image = character_images[req.character_id]

            # 获取音色样本
            voice_sample = None
            if req.character_id and req.character_id in voice_samples:
                voice_sample = voice_samples[req.character_id]

            try:
                result = self.generate_shot(req, voice_sample)
                results.append(result)
                logger.info(f"镜头 {req.shot_id} 生成完成: {result.video_path}")
            except Exception as e:
                logger.error(f"镜头 {req.shot_id} 生成失败: {e}")
                results.append(SeedanceShotResult(
                    shot_id=req.shot_id,
                    video_path="",
                    metadata={"error": str(e)}
                ))

        return results


def create_seedance_pipeline(
    project_id: Optional[str] = None,
    model: Optional[SeedanceModel] = None
) -> SeedancePipeline:
    """创建 Seedance 流水线实例"""
    return SeedancePipeline(project_id=project_id, model=model)
