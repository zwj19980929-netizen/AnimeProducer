"""
Seedance Client - 火山引擎 Seedance 视频生成客户端

基于火山引擎官方 SDK (volcengine-python-sdk[ark]) 实现。
支持 Seedance 1.5 Pro（当前）和 2.0（未来）。

功能：
- 文生视频 (Text-to-Video)
- 图生视频-首帧 (Image-to-Video with first frame)
- 图生视频-首尾帧 (Image-to-Video with first and last frame)
- 图生视频-参考图 (Image-to-Video with reference images, 1-4张)
- 有声视频生成 (generate_audio=True, 仅 1.5 Pro 支持)

API 文档: https://www.volcengine.com/docs/82379/1366799
"""
import logging
import os
import time
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import requests

from config import settings

logger = logging.getLogger(__name__)


class SeedanceModel(str, Enum):
    """Seedance 模型版本"""
    # Seedance 1.5 Pro - 支持有声视频、首帧、首尾帧、样片模式
    SEEDANCE_1_5_PRO = "doubao-seedance-1-5-pro-251215"
    # Seedance 1.0 Pro
    SEEDANCE_1_0_PRO = "doubao-seedance-1-0-pro-250528"
    # Seedance 1.0 Pro Fast
    SEEDANCE_1_0_PRO_FAST = "doubao-seedance-1-0-pro-fast-251015"
    # Seedance 1.0 Lite I2V - 支持参考图模式 (1-4张)
    SEEDANCE_1_0_LITE_I2V = "doubao-seedance-1-0-lite-i2v-250428"
    # Seedance 1.0 Lite T2V
    SEEDANCE_1_0_LITE_T2V = "doubao-seedance-1-0-lite-t2v-250428"
    # Seedance 2.0 (预留，API 上线后更新 Model ID)
    SEEDANCE_2_0 = "doubao-seedance-2-0"


class SeedanceResolution(str, Enum):
    """输出分辨率"""
    RES_480P = "480p"
    RES_720P = "720p"
    RES_1080P = "1080p"


class SeedanceRatio(str, Enum):
    """输出宽高比"""
    RATIO_21_9 = "21:9"
    RATIO_16_9 = "16:9"
    RATIO_4_3 = "4:3"
    RATIO_1_1 = "1:1"
    RATIO_3_4 = "3:4"
    RATIO_9_16 = "9:16"
    ADAPTIVE = "adaptive"


class ImageRole(str, Enum):
    """图片角色"""
    FIRST_FRAME = "first_frame"
    LAST_FRAME = "last_frame"
    REFERENCE_IMAGE = "reference_image"


class TaskStatus(str, Enum):
    """任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class SeedanceResult:
    """Seedance 生成结果"""
    task_id: str
    status: str
    video_url: Optional[str] = None
    video_data: Optional[bytes] = None
    audio_data: Optional[bytes] = None
    duration: float = 0.0
    resolution: Optional[str] = None
    ratio: Optional[str] = None
    seed: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class SeedanceClient:
    """
    火山引擎 Seedance 视频生成客户端

    使用官方 SDK: pip install 'volcengine-python-sdk[ark]'

    支持功能：
    - 文生视频（T2V）
    - 图生视频-首帧（I2V with first frame）
    - 图生视频-首尾帧（I2V with first & last frame）
    - 图生视频-参考图（I2V with 1-4 reference images）
    - 有声视频生成（仅 1.5 Pro）
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        default_model: SeedanceModel = SeedanceModel.SEEDANCE_1_5_PRO,
        poll_interval: int = 10,
        max_poll_time: int = 600
    ):
        self.api_key = api_key or os.environ.get("ARK_API_KEY") or getattr(settings, "ARK_API_KEY", None)
        self.base_url = base_url
        self.default_model = default_model
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self._client = None

    def _get_client(self):
        """获取或创建 Ark 客户端（懒加载）"""
        if self._client is None:
            if not self.api_key:
                raise ValueError("ARK_API_KEY 未配置，请设置环境变量或在 config 中配置")
            try:
                from volcenginesdkarkruntime import Ark
                self._client = Ark(
                    base_url=self.base_url,
                    api_key=self.api_key
                )
                logger.info("火山引擎 Ark 客户端初始化成功")
            except ImportError:
                raise ImportError(
                    "请安装火山引擎 SDK: pip install 'volcengine-python-sdk[ark]'"
                )
        return self._client

    def _upload_image_to_tos(self, image_path: str) -> str:
        """
        将本地图片上传到临时存储并返回 URL

        注意：火山引擎 API 需要图片 URL，不支持 base64
        实际项目中应使用 OSS/TOS 上传，这里提供一个简化实现
        """
        # 如果已经是 URL，直接返回
        if image_path.startswith("http://") or image_path.startswith("https://"):
            return image_path

        # 尝试使用项目的 OSS 服务上传
        try:
            from integrations.oss_service import OSSService, is_oss_configured
            if is_oss_configured():
                oss = OSSService.get_instance()
                url = oss.upload_file(image_path, folder="seedance_refs")
                logger.info(f"图片已上传到 OSS: {url[:60]}...")
                return url
        except Exception as e:
            logger.warning(f"OSS 上传失败: {e}")

        # 如果没有 OSS，抛出错误提示
        raise ValueError(
            f"火山引擎 Seedance API 需要图片 URL，请配置 OSS 服务或提供图片 URL。"
            f"本地路径: {image_path}"
        )

    def _wait_for_task(self, task_id: str) -> SeedanceResult:
        """轮询等待任务完成"""
        client = self._get_client()
        start_time = time.time()

        while time.time() - start_time < self.max_poll_time:
            result = client.content_generation.tasks.get(task_id=task_id)
            status = result.status

            if status == "succeeded":
                logger.info(f"Seedance 任务成功: {task_id}")
                return SeedanceResult(
                    task_id=task_id,
                    status=status,
                    video_url=result.content.video_url if result.content else None,
                    duration=result.duration or 0.0,
                    resolution=result.resolution,
                    ratio=result.ratio,
                    seed=result.seed,
                    metadata={
                        "usage": result.usage.__dict__ if result.usage else {},
                        "created_at": result.created_at,
                        "updated_at": result.updated_at,
                    }
                )
            elif status == "failed":
                error_msg = str(result.error) if result.error else "未知错误"
                logger.error(f"Seedance 任务失败: {task_id}, 错误: {error_msg}")
                return SeedanceResult(
                    task_id=task_id,
                    status=status,
                    error=error_msg
                )
            else:
                logger.debug(f"Seedance 任务状态: {status}, 等待 {self.poll_interval}s...")
                time.sleep(self.poll_interval)

        raise TimeoutError(f"Seedance 任务超时 (>{self.max_poll_time}s): {task_id}")

    def _download_video(self, video_url: str) -> bytes:
        """下载视频文件"""
        logger.info(f"下载视频: {video_url[:60]}...")
        response = requests.get(video_url, timeout=120)
        response.raise_for_status()
        return response.content

    def generate_text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        ratio: Union[str, SeedanceRatio] = SeedanceRatio.RATIO_16_9,
        generate_audio: bool = True,
        model: Optional[SeedanceModel] = None,
        watermark: bool = False,
        resolution: Optional[str] = None
    ) -> SeedanceResult:
        """
        文生视频 (Text-to-Video)

        Args:
            prompt: 视频描述文本
            duration: 视频时长 (4-12秒 for 1.5 Pro)
            ratio: 宽高比
            generate_audio: 是否生成音频 (仅 1.5 Pro 支持)
            model: 模型版本
            watermark: 是否添加水印
            resolution: 分辨率 (480p/720p/1080p)

        Returns:
            SeedanceResult
        """
        client = self._get_client()
        model = model or self.default_model

        content = [{"type": "text", "text": prompt}]

        logger.info(f"创建文生视频任务: model={model.value}, duration={duration}s")
        result = client.content_generation.tasks.create(
            model=model.value,
            content=content,
            generate_audio=generate_audio,
            ratio=ratio.value if isinstance(ratio, SeedanceRatio) else ratio,
            duration=duration,
            watermark=watermark,
            **({"resolution": resolution} if resolution else {})
        )

        task_id = result.id
        logger.info(f"任务已创建: {task_id}")

        return self._wait_for_task(task_id)

    def generate_image_to_video(
        self,
        prompt: str,
        first_frame_url: str,
        last_frame_url: Optional[str] = None,
        duration: int = 5,
        ratio: Union[str, SeedanceRatio] = SeedanceRatio.ADAPTIVE,
        generate_audio: bool = True,
        model: Optional[SeedanceModel] = None,
        watermark: bool = False
    ) -> SeedanceResult:
        """
        图生视频 - 基于首帧（或首尾帧）

        Args:
            prompt: 视频描述
            first_frame_url: 首帧图片 URL
            last_frame_url: 尾帧图片 URL（可选，用于首尾帧模式）
            duration: 视频时长
            ratio: 宽高比 (adaptive 会根据图片自动适配)
            generate_audio: 是否生成音频
            model: 模型版本
            watermark: 是否添加水印

        Returns:
            SeedanceResult
        """
        client = self._get_client()
        model = model or self.default_model

        # 处理图片 URL
        first_frame_url = self._upload_image_to_tos(first_frame_url)

        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": first_frame_url},
                "role": ImageRole.FIRST_FRAME.value
            }
        ]

        # 如果有尾帧，添加尾帧
        if last_frame_url:
            last_frame_url = self._upload_image_to_tos(last_frame_url)
            content.append({
                "type": "image_url",
                "image_url": {"url": last_frame_url},
                "role": ImageRole.LAST_FRAME.value
            })

        mode = "首尾帧" if last_frame_url else "首帧"
        logger.info(f"创建图生视频任务({mode}): model={model.value}, duration={duration}s")

        result = client.content_generation.tasks.create(
            model=model.value,
            content=content,
            generate_audio=generate_audio,
            ratio=ratio.value if isinstance(ratio, SeedanceRatio) else ratio,
            duration=duration,
            watermark=watermark
        )

        task_id = result.id
        logger.info(f"任务已创建: {task_id}")

        return self._wait_for_task(task_id)

    def generate_with_reference_images(
        self,
        prompt: str,
        reference_images: List[str],
        duration: int = 5,
        ratio: Union[str, SeedanceRatio] = SeedanceRatio.RATIO_16_9,
        model: Optional[SeedanceModel] = None,
        watermark: bool = False
    ) -> SeedanceResult:
        """
        图生视频 - 基于参考图 (1-4张)

        模型会提取参考图中对象的关键特征，在视频中还原形态、色彩和纹理。
        Prompt 中使用 [图1]、[图2] 等引用参考图。

        Args:
            prompt: 视频描述，使用 [图1] [图2] 等引用参考图
            reference_images: 参考图 URL 列表 (1-4张)
            duration: 视频时长
            ratio: 宽高比
            model: 模型版本 (推荐 SEEDANCE_1_0_LITE_I2V)
            watermark: 是否添加水印

        Returns:
            SeedanceResult

        Example:
            >>> client.generate_with_reference_images(
            ...     prompt="[图1]的女孩在[图2]的场景中跳舞",
            ...     reference_images=["girl.png", "background.png"]
            ... )
        """
        if not reference_images:
            raise ValueError("至少需要提供 1 张参考图")
        if len(reference_images) > 4:
            raise ValueError("最多支持 4 张参考图")

        client = self._get_client()
        # 参考图模式推荐使用 lite-i2v 模型
        model = model or SeedanceModel.SEEDANCE_1_0_LITE_I2V

        content = [{"type": "text", "text": prompt}]

        for img_path in reference_images:
            img_url = self._upload_image_to_tos(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": img_url},
                "role": ImageRole.REFERENCE_IMAGE.value
            })

        logger.info(f"创建参考图视频任务: model={model.value}, refs={len(reference_images)}")

        result = client.content_generation.tasks.create(
            model=model.value,
            content=content,
            ratio=ratio.value if isinstance(ratio, SeedanceRatio) else ratio,
            duration=duration,
            watermark=watermark
        )

        task_id = result.id
        logger.info(f"任务已创建: {task_id}")

        return self._wait_for_task(task_id)

    def generate_shot_with_voice(
        self,
        prompt: str,
        character_image: Optional[str] = None,
        voice_sample: Optional[Union[str, bytes]] = None,
        dialogue: Optional[str] = None,
        duration: int = 5,
        ratio: Union[str, SeedanceRatio] = SeedanceRatio.ADAPTIVE,
        resolution: Optional[str] = None,
        audio_language: str = "zh",
        model: Optional[SeedanceModel] = None
    ) -> SeedanceResult:
        """
        生成带角色的镜头（方案C核心方法）

        这是为 AnimeProducer 流水线设计的高级方法，整合了：
        - 角色参考图（首帧）保持视觉一致性
        - 有声视频生成（1.5 Pro 原生支持）
        - 对白注入到 prompt

        注意：Seedance 1.5 Pro 的音频是根据 prompt 内容生成的，
        不支持音色克隆。音色一致性需要等待 2.0 版本。

        Args:
            prompt: 视觉描述
            character_image: 角色参考图路径/URL（作为首帧）
            voice_sample: 音色样本（预留给 2.0，当前版本忽略）
            dialogue: 角色对白（会注入到 prompt）
            duration: 视频时长
            ratio: 宽高比
            resolution: 分辨率
            audio_language: 音频语言
            model: 模型版本

        Returns:
            SeedanceResult
        """
        model = model or self.default_model

        # 构建完整 prompt
        full_prompt = prompt
        if dialogue:
            # 将对白注入 prompt，让模型生成对应的音频
            full_prompt = f'{prompt}，角色说："{dialogue}"'

        # 如果有角色参考图，使用图生视频模式
        if character_image:
            result = self.generate_image_to_video(
                prompt=full_prompt,
                first_frame_url=character_image,
                duration=duration,
                ratio=ratio,
                generate_audio=True,
                model=model
            )
        else:
            # 纯文生视频
            result = self.generate_text_to_video(
                prompt=full_prompt,
                duration=duration,
                ratio=ratio,
                generate_audio=True,
                model=model,
                resolution=resolution
            )

        # 下载视频数据
        if result.video_url:
            result.video_data = self._download_video(result.video_url)

        # voice_sample 参数预留给 Seedance 2.0
        if voice_sample:
            logger.info("音色样本已记录，将在 Seedance 2.0 上线后启用音色克隆功能")

        return result

    def list_tasks(
        self,
        page_size: int = 10,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        查询视频生成任务列表

        Args:
            page_size: 每页数量
            status: 状态筛选 (queued/running/succeeded/failed)

        Returns:
            任务列表
        """
        client = self._get_client()
        # 使用 HTTP 请求，因为 SDK 可能没有封装这个接口
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        params = {"page_size": page_size}
        if status:
            params["filter.status"] = status

        response = requests.get(
            f"{self.base_url}/contents/generations/tasks",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def cancel_task(self, task_id: str) -> bool:
        """
        取消或删除视频生成任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        response = requests.delete(
            f"{self.base_url}/contents/generations/tasks/{task_id}",
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            logger.info(f"任务已取消/删除: {task_id}")
            return True
        else:
            logger.warning(f"取消任务失败: {task_id}, status={response.status_code}")
            return False

    def health_check(self) -> bool:
        """检查 API 是否可用"""
        try:
            self._get_client()
            return True
        except Exception as e:
            logger.error(f"Seedance 健康检查失败: {e}")
            return False

    @property
    def supports_audio(self) -> bool:
        """当前模型是否支持音频生成"""
        return self.default_model == SeedanceModel.SEEDANCE_1_5_PRO

    @property
    def supports_voice_cloning(self) -> bool:
        """当前模型是否支持音色克隆（2.0 特性）"""
        return self.default_model == SeedanceModel.SEEDANCE_2_0


# 便捷函数
def create_seedance_client(
    api_key: Optional[str] = None,
    model: SeedanceModel = SeedanceModel.SEEDANCE_1_5_PRO
) -> SeedanceClient:
    """创建 Seedance 客户端实例"""
    return SeedanceClient(api_key=api_key, default_model=model)


# 全局单例（懒加载）
_seedance_client: Optional[SeedanceClient] = None


def get_seedance_client() -> SeedanceClient:
    """获取全局 Seedance 客户端实例"""
    global _seedance_client
    if _seedance_client is None:
        _seedance_client = SeedanceClient()
    return _seedance_client


# 兼容旧代码的别名
seedance_client = property(lambda self: get_seedance_client())

