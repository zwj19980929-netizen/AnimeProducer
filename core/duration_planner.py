"""Duration Planner - 时长规划器

解决 Audio-First Pipeline 中的时长规划问题。
先生成音频获取精确时长，再规划视频生成策略。
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DurationPlan:
    """时长规划结果"""
    audio_duration: float          # 音频实际时长
    target_video_duration: float   # 目标视频时长
    video_segments: int            # 需要生成的视频段数
    segment_duration: float        # 每段视频时长
    buffer: float                  # 缓冲时长

    @property
    def total_raw_video_duration(self) -> float:
        """原始视频总时长（未裁剪）"""
        return self.video_segments * self.segment_duration


class DurationPlanner:
    """
    时长规划器

    根据音频时长规划视频生成策略：
    - 如果音频时长在单次生成范围内，直接生成
    - 如果音频时长超过单次生成上限，规划多段生成
    """

    def __init__(
        self,
        max_single_video_duration: float = 5.0,
        min_single_video_duration: float = 2.0,
        default_buffer: float = 0.5
    ):
        """
        初始化时长规划器

        Args:
            max_single_video_duration: 单次视频生成的最大时长（受模型限制）
            min_single_video_duration: 单次视频生成的最小时长
            default_buffer: 默认缓冲时长（视频比音频长的部分）
        """
        self.max_single_video_duration = max_single_video_duration
        self.min_single_video_duration = min_single_video_duration
        self.default_buffer = default_buffer

    def plan(
        self,
        audio_duration: float,
        buffer: Optional[float] = None
    ) -> DurationPlan:
        """
        根据音频时长规划视频生成策略

        Args:
            audio_duration: 音频实际时长（秒）
            buffer: 缓冲时长，默认使用 default_buffer

        Returns:
            DurationPlan: 时长规划结果
        """
        buffer = buffer if buffer is not None else self.default_buffer
        target_duration = audio_duration + buffer

        # 确保目标时长不小于最小时长
        target_duration = max(target_duration, self.min_single_video_duration)

        if target_duration <= self.max_single_video_duration:
            # 单段视频即可满足
            plan = DurationPlan(
                audio_duration=audio_duration,
                target_video_duration=target_duration,
                video_segments=1,
                segment_duration=target_duration,
                buffer=buffer
            )
            logger.debug(
                f"Single segment plan: audio={audio_duration:.2f}s, "
                f"video={target_duration:.2f}s"
            )
        else:
            # 需要多段视频拼接
            segments = math.ceil(target_duration / self.max_single_video_duration)
            segment_duration = target_duration / segments

            # 确保每段时长在合理范围内
            segment_duration = max(segment_duration, self.min_single_video_duration)

            plan = DurationPlan(
                audio_duration=audio_duration,
                target_video_duration=target_duration,
                video_segments=segments,
                segment_duration=segment_duration,
                buffer=buffer
            )
            logger.info(
                f"Multi-segment plan: audio={audio_duration:.2f}s, "
                f"segments={segments}, each={segment_duration:.2f}s"
            )

        return plan

    def plan_for_no_dialogue(
        self,
        target_duration: float = 4.0
    ) -> DurationPlan:
        """
        为无对白镜头规划时长

        Args:
            target_duration: 目标时长

        Returns:
            DurationPlan: 时长规划结果
        """
        return self.plan(audio_duration=target_duration, buffer=0.0)


def get_audio_duration(audio_path: str) -> float:
    """
    获取音频文件的精确时长

    Args:
        audio_path: 音频文件路径

    Returns:
        float: 音频时长（秒）
    """
    try:
        from moviepy import AudioFileClip
        with AudioFileClip(audio_path) as clip:
            return clip.duration
    except Exception as e:
        logger.error(f"Failed to get audio duration: {e}")
        # 返回估算值
        return 3.0


# 全局实例
duration_planner = DurationPlanner()
