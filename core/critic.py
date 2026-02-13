"""
AI 影评人模块 (Video Critic)

使用 VLM (Vision Language Model) 对生成的视频进行质量评分，
实现闭环反馈机制，自动拦截低质量画面并触发重绘。

支持的 VLM 后端:
- Google Gemini 1.5 Pro (推荐，视频理解能力强)
- OpenAI GPT-4o

评分维度:
- 解剖学错误 (多指、扭曲的肢体)
- 时间闪烁 (背景不一致)
- 提示词匹配度 (是否符合剧本描述)
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class VideoReview:
    """视频评审结果"""
    score: int  # 0-10 分
    has_glitches: bool  # 是否存在明显缺陷
    feedback: str  # 修正建议（可添加到 Prompt 中）
    details: Dict[str, Any] = field(default_factory=dict)  # 详细评分
    raw_response: str = ""  # 原始响应


class VideoCritic:
    """
    AI 影评人

    使用视觉语言模型对生成的视频进行质量评分，
    扮演"导演"角色审查视频质量。
    """

    # 评分阈值
    DEFAULT_PASS_SCORE = 8  # 默认通过分数

    # 系统提示词
    SYSTEM_PROMPT = """You are a top-tier anime director with decades of experience.
You are in Critical Review Mode, evaluating AI-generated anime video clips.

Analyze the video carefully for these specific issues:

1. **Anatomy Errors** (Critical)
   - Extra fingers, missing fingers, twisted limbs
   - Unnatural body proportions
   - Face distortions, asymmetric features

2. **Temporal Flickering** (Important)
   - Inconsistent background elements between frames
   - Sudden color/lighting changes
   - Object position jumps

3. **Prompt Adherence** (Important)
   - Does the video match the scene description?
   - Are the characters positioned correctly?
   - Is the mood/atmosphere correct?

4. **Animation Quality** (Moderate)
   - Smooth motion vs jerky movement
   - Natural character movements
   - Proper physics (hair, clothing flow)

Return your evaluation as a JSON object with this exact structure:
{
    "score": <integer 0-10>,
    "has_glitches": <boolean>,
    "feedback": "<short, actionable fix for the prompt if score < 8>",
    "details": {
        "anatomy": <0-10>,
        "temporal_consistency": <0-10>,
        "prompt_match": <0-10>,
        "animation_quality": <0-10>
    }
}

Scoring Guide:
- 10: Perfect, broadcast quality
- 8-9: Minor issues, acceptable for production
- 6-7: Noticeable issues, may need re-generation
- 4-5: Significant problems, definitely needs re-generation
- 0-3: Severe issues, unusable

IMPORTANT: Only return the JSON object, no other text."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        pass_score: Optional[int] = None,
    ):
        """
        初始化 AI 影评人

        Args:
            provider: VLM 提供商 (gemini, openai)
            model: 模型名称
            pass_score: 通过分数阈值 (默认从配置读取 CRITIC_MIN_SCORE)
        """
        self.provider = provider or getattr(settings, 'CRITIC_PROVIDER', settings.VLM_BACKEND)
        self.model = model or getattr(settings, 'CRITIC_MODEL', self._get_default_model())
        # 优先使用传入的 pass_score，否则从配置读取，最后使用默认值
        self.pass_score = pass_score if pass_score is not None else getattr(
            settings, 'CRITIC_MIN_SCORE', self.DEFAULT_PASS_SCORE
        )
        self._client = None

        self._init_client()

    def _get_default_model(self) -> str:
        """获取默认模型"""
        if self.provider == "openai":
            return "gpt-4o"
        else:
            # Gemini 1.5 Pro 对视频理解能力更强
            return "gemini-1.5-pro"

    def _init_client(self) -> None:
        """初始化 VLM 客户端"""
        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError(
                    "OpenAI API Key 未配置。请在 .env 中设置 OPENAI_API_KEY"
                )
            from openai import OpenAI
            self._client = OpenAI()
            logger.info(f"VideoCritic initialized with OpenAI ({self.model})")
        else:
            if not settings.GOOGLE_API_KEY:
                raise RuntimeError(
                    "Google API Key 未配置。请在 .env 中设置 GOOGLE_API_KEY"
                )
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            self._client = genai.GenerativeModel(self.model)
            logger.info(f"VideoCritic initialized with Gemini ({self.model})")

    def evaluate_shot(
        self,
        video_path: str,
        original_prompt: str,
        characters: Optional[List[str]] = None,
    ) -> VideoReview:
        """
        评估视频质量

        Args:
            video_path: 视频文件路径或 URL
            original_prompt: 原始视觉提示词
            characters: 出场角色列表（可选）

        Returns:
            VideoReview: 评审结果
        """
        logger.info(f"Evaluating video: {video_path}")

        # 构建评估提示词
        eval_prompt = self._build_eval_prompt(original_prompt, characters)

        # 解析视频路径
        local_path = self._resolve_video_path(video_path)

        try:
            if self.provider == "openai":
                result = self._evaluate_with_openai(local_path, eval_prompt)
            else:
                result = self._evaluate_with_gemini(local_path, eval_prompt)

            logger.info(
                f"Video evaluation complete: score={result.score}, "
                f"has_glitches={result.has_glitches}"
            )
            return result

        finally:
            # 清理临时文件
            if local_path != video_path and os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                except Exception:
                    pass

    def _build_eval_prompt(
        self,
        original_prompt: str,
        characters: Optional[List[str]] = None,
    ) -> str:
        """构建评估提示词"""
        parts = [f"Scene Description:\n{original_prompt}"]

        if characters:
            char_list = ", ".join(characters)
            parts.append(f"\nCharacters in scene: {char_list}")

        parts.append("\nPlease evaluate this video clip.")

        return "\n".join(parts)

    def _resolve_video_path(self, video_path: str) -> str:
        """
        解析视频路径，如果是 URL 则下载到临时文件

        Args:
            video_path: 视频路径或 URL

        Returns:
            本地文件路径
        """
        if video_path.startswith("http://") or video_path.startswith("https://"):
            logger.info(f"Downloading video from URL for evaluation...")
            from integrations.oss_service import OSSService
            return OSSService.get_instance().download_to_temp(video_path)
        else:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video not found: {video_path}")
            return video_path

    def _evaluate_with_gemini(self, video_path: str, eval_prompt: str) -> VideoReview:
        """使用 Gemini 评估视频"""
        import google.generativeai as genai

        # 上传视频文件
        logger.info("Uploading video to Gemini...")
        video_file = genai.upload_file(video_path)

        # 等待处理完成
        import time
        while video_file.state.name == "PROCESSING":
            logger.debug("Waiting for video processing...")
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise RuntimeError(f"Video processing failed: {video_file.state.name}")

        # 发送评估请求
        response = self._client.generate_content(
            [self.SYSTEM_PROMPT, video_file, eval_prompt],
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=1000,
            )
        )

        # 清理上传的文件
        try:
            genai.delete_file(video_file.name)
        except Exception:
            pass

        return self._parse_response(response.text)

    def _evaluate_with_openai(self, video_path: str, eval_prompt: str) -> VideoReview:
        """
        使用 OpenAI GPT-4o 评估视频

        注意: GPT-4o 目前不直接支持视频输入，
        我们通过提取关键帧来模拟视频分析。
        """
        # 提取视频关键帧
        frames = self._extract_key_frames(video_path, num_frames=8)

        # 构建消息内容
        content = [{"type": "text", "text": self.SYSTEM_PROMPT + "\n\n" + eval_prompt}]

        # 添加帧图像
        import base64
        for frame_path in frames:
            with open(frame_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
            })

        # 发送请求
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            max_tokens=1000,
            temperature=0.2,
        )

        # 清理临时帧文件
        for frame_path in frames:
            try:
                os.unlink(frame_path)
            except Exception:
                pass

        return self._parse_response(response.choices[0].message.content)

    def _extract_key_frames(self, video_path: str, num_frames: int = 8) -> List[str]:
        """
        从视频中提取关键帧

        Args:
            video_path: 视频路径
            num_frames: 提取帧数

        Returns:
            帧图像路径列表
        """
        from moviepy import VideoFileClip

        clip = VideoFileClip(video_path)
        duration = clip.duration

        frame_paths = []
        try:
            # 均匀采样帧
            for i in range(num_frames):
                t = (i / (num_frames - 1)) * duration if num_frames > 1 else 0
                t = min(t, duration - 0.01)  # 避免边界问题

                temp_frame = tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                )
                temp_frame.close()

                clip.save_frame(temp_frame.name, t=t)
                frame_paths.append(temp_frame.name)
        except Exception as e:
            # 清理已创建的临时文件
            for path in frame_paths:
                try:
                    os.unlink(path)
                except Exception:
                    pass
            raise e
        finally:
            clip.close()

        return frame_paths

    def _parse_response(self, response_text: str) -> VideoReview:
        """解析 VLM 响应"""
        try:
            # 清理响应文本
            text = response_text.strip()

            # 移除 markdown 代码块标记
            if text.startswith("```"):
                lines = text.split("\n")
                # 移除第一行和最后一行
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            data = json.loads(text)

            return VideoReview(
                score=int(data.get("score", 5)),
                has_glitches=bool(data.get("has_glitches", True)),
                feedback=str(data.get("feedback", "")),
                details=data.get("details", {}),
                raw_response=response_text,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse VLM response: {e}")
            logger.debug(f"Raw response: {response_text}")

            # 返回保守的默认值
            return VideoReview(
                score=5,
                has_glitches=True,
                feedback="Unable to parse evaluation response",
                raw_response=response_text,
            )

    def is_acceptable(self, review: VideoReview) -> bool:
        """
        判断视频是否达到质量标准

        Args:
            review: 评审结果

        Returns:
            是否通过质量检查
        """
        return review.score >= self.pass_score


# 单例实例
video_critic: Optional[VideoCritic] = None


def get_video_critic() -> VideoCritic:
    """获取 VideoCritic 单例"""
    global video_critic
    if video_critic is None:
        video_critic = VideoCritic()
    return video_critic
