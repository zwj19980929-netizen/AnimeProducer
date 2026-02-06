"""Transitions - 智能转场系统

根据场景类型自动选择合适的转场效果。
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TransitionType(str, Enum):
    """转场类型"""
    CUT = "cut"                    # 硬切
    CROSSFADE = "crossfade"        # 交叉淡化
    FADE_BLACK = "fade_black"      # 淡入淡出黑场
    FADE_WHITE = "fade_white"      # 淡入淡出白场
    WIPE_LEFT = "wipe_left"        # 左擦除
    WIPE_RIGHT = "wipe_right"      # 右擦除
    WIPE_UP = "wipe_up"            # 上擦除
    WIPE_DOWN = "wipe_down"        # 下擦除
    ZOOM_IN = "zoom_in"            # 缩放进入
    ZOOM_OUT = "zoom_out"          # 缩放退出
    SLIDE_LEFT = "slide_left"      # 左滑动
    SLIDE_RIGHT = "slide_right"    # 右滑动


@dataclass
class TransitionConfig:
    """转场配置"""
    transition_type: TransitionType
    duration: float  # 转场时长（秒）
    easing: str = "linear"  # 缓动函数


class TransitionSelector:
    """
    智能转场选择器

    根据前后镜头的场景类型、动作类型等信息，
    自动选择最合适的转场效果。
    """

    # 场景类型到推荐转场的映射
    # (前一场景类型, 后一场景类型) -> (转场类型, 时长)
    SCENE_TRANSITION_MAP: Dict[Tuple[str, str], Tuple[TransitionType, float]] = {
        # 对话场景之间：硬切
        ("dialogue", "dialogue"): (TransitionType.CUT, 0.0),

        # 对话到动作：硬切
        ("dialogue", "action"): (TransitionType.CUT, 0.0),

        # 动作场景之间：硬切（保持节奏）
        ("action", "action"): (TransitionType.CUT, 0.0),

        # 动作到对话：短交叉淡化
        ("action", "dialogue"): (TransitionType.CROSSFADE, 0.3),

        # 进入闪回：白场淡化
        ("any", "flashback"): (TransitionType.FADE_WHITE, 0.8),
        ("flashback", "any"): (TransitionType.FADE_WHITE, 0.8),

        # 进入梦境：长交叉淡化
        ("any", "dream"): (TransitionType.CROSSFADE, 1.0),
        ("dream", "any"): (TransitionType.CROSSFADE, 1.0),

        # 室内外切换：黑场淡化
        ("interior", "exterior"): (TransitionType.FADE_BLACK, 0.5),
        ("exterior", "interior"): (TransitionType.FADE_BLACK, 0.5),

        # 日夜切换
        ("day", "night"): (TransitionType.FADE_BLACK, 0.8),
        ("night", "day"): (TransitionType.FADE_WHITE, 0.8),

        # 时间跳跃
        ("any", "time_skip"): (TransitionType.FADE_BLACK, 1.0),
        ("time_skip", "any"): (TransitionType.FADE_BLACK, 1.0),

        # 场景切换（不同地点）
        ("location_a", "location_b"): (TransitionType.FADE_BLACK, 0.5),

        # 情绪转换
        ("happy", "sad"): (TransitionType.CROSSFADE, 0.8),
        ("sad", "happy"): (TransitionType.CROSSFADE, 0.8),

        # 高潮/转折点
        ("any", "climax"): (TransitionType.FADE_WHITE, 0.3),
        ("climax", "any"): (TransitionType.FADE_BLACK, 0.5),

        # 结尾
        ("any", "ending"): (TransitionType.FADE_BLACK, 1.5),
    }

    # 动作类型关键词
    ACTION_KEYWORDS = ["fight", "battle", "run", "chase", "action", "combat", "attack"]
    DIALOGUE_KEYWORDS = ["talk", "speak", "conversation", "dialogue", "chat"]
    FLASHBACK_KEYWORDS = ["flashback", "memory", "remember", "past"]
    DREAM_KEYWORDS = ["dream", "nightmare", "vision", "imagine"]

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.TransitionSelector")

    def select_transition(
        self,
        prev_scene_type: Optional[str] = None,
        next_scene_type: Optional[str] = None,
        prev_prompt: Optional[str] = None,
        next_prompt: Optional[str] = None,
        prev_action_type: Optional[str] = None,
        next_action_type: Optional[str] = None
    ) -> TransitionConfig:
        """
        根据前后镜头信息选择合适的转场

        Args:
            prev_scene_type: 前一场景类型
            next_scene_type: 后一场景类型
            prev_prompt: 前一镜头的视觉提示词
            next_prompt: 后一镜头的视觉提示词
            prev_action_type: 前一镜头的动作类型
            next_action_type: 后一镜头的动作类型

        Returns:
            TransitionConfig: 转场配置
        """
        # 如果没有提供场景类型，尝试从提示词推断
        if not prev_scene_type and prev_prompt:
            prev_scene_type = self._infer_scene_type(prev_prompt, prev_action_type)
        if not next_scene_type and next_prompt:
            next_scene_type = self._infer_scene_type(next_prompt, next_action_type)

        # 默认类型
        prev_type = prev_scene_type or "dialogue"
        next_type = next_scene_type or "dialogue"

        # 精确匹配
        key = (prev_type, next_type)
        if key in self.SCENE_TRANSITION_MAP:
            transition_type, duration = self.SCENE_TRANSITION_MAP[key]
            self.logger.debug(f"Exact match: {key} -> {transition_type.value}")
            return TransitionConfig(transition_type=transition_type, duration=duration)

        # 通配符匹配
        for (p, n), (t_type, duration) in self.SCENE_TRANSITION_MAP.items():
            if (p == "any" or p == prev_type) and (n == "any" or n == next_type):
                self.logger.debug(f"Wildcard match: ({p}, {n}) -> {t_type.value}")
                return TransitionConfig(transition_type=t_type, duration=duration)

        # 默认：交叉淡化
        self.logger.debug(f"Default transition for ({prev_type}, {next_type})")
        return TransitionConfig(
            transition_type=TransitionType.CROSSFADE,
            duration=0.5
        )

    def _infer_scene_type(
        self,
        prompt: str,
        action_type: Optional[str] = None
    ) -> str:
        """从提示词推断场景类型"""
        prompt_lower = prompt.lower()

        # 检查动作类型
        if action_type:
            return action_type

        # 检查关键词
        for keyword in self.FLASHBACK_KEYWORDS:
            if keyword in prompt_lower:
                return "flashback"

        for keyword in self.DREAM_KEYWORDS:
            if keyword in prompt_lower:
                return "dream"

        for keyword in self.ACTION_KEYWORDS:
            if keyword in prompt_lower:
                return "action"

        for keyword in self.DIALOGUE_KEYWORDS:
            if keyword in prompt_lower:
                return "dialogue"

        # 检查时间/地点
        if "night" in prompt_lower:
            return "night"
        if "day" in prompt_lower or "morning" in prompt_lower:
            return "day"
        if "indoor" in prompt_lower or "room" in prompt_lower:
            return "interior"
        if "outdoor" in prompt_lower or "outside" in prompt_lower:
            return "exterior"

        return "dialogue"  # 默认


class TransitionApplier:
    """
    转场效果应用器

    将转场效果应用到视频片段上，结果上传到 OSS。
    支持从 OSS URL 下载视频进行处理。
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.TransitionApplier")

    def _resolve_path(self, path: str) -> str:
        """解析路径，如果是 OSS URL 则下载到临时文件"""
        if path.startswith("http://") or path.startswith("https://"):
            self.logger.info(f"Downloading video from OSS: {path}")
            from integrations.oss_service import OSSService
            return OSSService.get_instance().download_to_temp(path)
        return path

    def apply(
        self,
        clip1_path: str,
        clip2_path: str,
        transition_config: TransitionConfig
    ) -> str:
        """
        应用转场效果并拼接两个视频

        Args:
            clip1_path: 第一个视频路径（本地或 OSS URL）
            clip2_path: 第二个视频路径（本地或 OSS URL）
            transition_config: 转场配置

        Returns:
            输出视频的 OSS URL
        """
        from moviepy import VideoFileClip, concatenate_videoclips, CompositeVideoClip
        from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
        import tempfile

        self.logger.info(
            f"Applying {transition_config.transition_type.value} transition "
            f"(duration={transition_config.duration}s)"
        )

        # 解析路径（可能需要从 OSS 下载）
        local_clip1 = self._resolve_path(clip1_path)
        local_clip2 = self._resolve_path(clip2_path)
        temp_files = []

        clip1 = VideoFileClip(local_clip1)
        clip2 = VideoFileClip(local_clip2)

        try:
            if transition_config.transition_type == TransitionType.CUT:
                # 硬切：直接拼接
                final = concatenate_videoclips([clip1, clip2])

            elif transition_config.transition_type == TransitionType.CROSSFADE:
                # 交叉淡化
                duration = transition_config.duration
                clip1 = clip1.with_effects([CrossFadeOut(duration)])
                clip2 = clip2.with_effects([CrossFadeIn(duration)])
                final = concatenate_videoclips(
                    [clip1, clip2],
                    padding=-duration,
                    method="compose"
                )

            elif transition_config.transition_type == TransitionType.FADE_BLACK:
                # 淡入淡出黑场
                duration = transition_config.duration / 2
                clip1 = clip1.with_effects([FadeOut(duration)])
                clip2 = clip2.with_effects([FadeIn(duration)])
                final = concatenate_videoclips([clip1, clip2])

            elif transition_config.transition_type == TransitionType.FADE_WHITE:
                # 淡入淡出白场
                duration = transition_config.duration / 2
                clip1 = self._fade_to_color(clip1, duration, (255, 255, 255), fade_out=True)
                clip2 = self._fade_from_color(clip2, duration, (255, 255, 255))
                final = concatenate_videoclips([clip1, clip2])

            else:
                # 其他转场类型：默认使用交叉淡化
                self.logger.warning(
                    f"Transition type {transition_config.transition_type.value} "
                    f"not fully implemented, using crossfade"
                )
                duration = transition_config.duration
                clip1 = clip1.with_effects([CrossFadeOut(duration)])
                clip2 = clip2.with_effects([CrossFadeIn(duration)])
                final = concatenate_videoclips(
                    [clip1, clip2],
                    padding=-duration,
                    method="compose"
                )

            # 写入临时文件
            temp_output = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            temp_output.close()
            temp_files.append(temp_output.name)

            final.write_videofile(
                temp_output.name,
                fps=24,
                codec="libx264",
                audio_codec="aac",
                logger=None
            )

            # 上传到 OSS
            from integrations.oss_service import require_oss
            oss = require_oss()

            import uuid
            filename = f"transition_{uuid.uuid4().hex[:8]}"
            output_url = oss.upload_file(temp_output.name, folder="videos")
            self.logger.info(f"Transition video uploaded to OSS: {output_url}")

            return output_url

        finally:
            clip1.close()
            clip2.close()
            # 清理临时文件
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception:
                        pass
            # 清理下载的临时文件
            if local_clip1 != clip1_path and os.path.exists(local_clip1):
                try:
                    os.unlink(local_clip1)
                except Exception:
                    pass
            if local_clip2 != clip2_path and os.path.exists(local_clip2):
                try:
                    os.unlink(local_clip2)
                except Exception:
                    pass

    def _fade_to_color(
        self,
        clip,
        duration: float,
        color: Tuple[int, int, int],
        fade_out: bool = True
    ):
        """淡出到指定颜色"""
        from moviepy import ColorClip, CompositeVideoClip
        import numpy as np

        # 创建颜色层
        color_clip = ColorClip(
            size=clip.size,
            color=color,
            duration=clip.duration
        )

        def make_frame(t):
            if fade_out:
                # 淡出：从 0 到 1
                if t < clip.duration - duration:
                    alpha = 0
                else:
                    alpha = (t - (clip.duration - duration)) / duration
            else:
                # 淡入：从 1 到 0
                if t > duration:
                    alpha = 0
                else:
                    alpha = 1 - t / duration

            return alpha

        color_clip = color_clip.with_opacity(make_frame)

        return CompositeVideoClip([clip, color_clip])

    def _fade_from_color(
        self,
        clip,
        duration: float,
        color: Tuple[int, int, int]
    ):
        """从指定颜色淡入"""
        return self._fade_to_color(clip, duration, color, fade_out=False)

    def apply_to_sequence(
        self,
        clip_paths: List[str],
        transitions: List[TransitionConfig]
    ) -> str:
        """
        对一系列视频应用转场效果

        Args:
            clip_paths: 视频路径列表（本地或 OSS URL）
            transitions: 转场配置列表（长度应为 len(clip_paths) - 1）

        Returns:
            输出视频的 OSS URL
        """
        if len(clip_paths) < 2:
            if clip_paths:
                # 只有一个视频，如果是本地文件则上传到 OSS
                if not clip_paths[0].startswith("http"):
                    from integrations.oss_service import require_oss
                    oss = require_oss()
                    return oss.upload_file(clip_paths[0], folder="videos")
                return clip_paths[0]
            else:
                raise ValueError("No clips provided")

        if len(transitions) != len(clip_paths) - 1:
            raise ValueError(
                f"Expected {len(clip_paths) - 1} transitions, got {len(transitions)}"
            )

        # 逐个应用转场
        current_url = clip_paths[0]

        for i, (next_path, transition) in enumerate(zip(clip_paths[1:], transitions)):
            # 应用转场，结果会自动上传到 OSS
            current_url = self.apply(current_url, next_path, transition)

        return current_url


# 全局实例
transition_selector = TransitionSelector()
transition_applier = TransitionApplier()
