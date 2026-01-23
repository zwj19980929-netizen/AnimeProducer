"""
Editor - 视频编辑与合成模块

职责：
- 镜头拼接与转场
- 音视频对齐（slow-motion / loop 策略）
- 字幕生成与嵌入
"""
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from moviepy import (
    VideoFileClip,
    AudioFileClip,
    concatenate_videoclips,
    CompositeVideoClip,
)
from moviepy.video.fx import Loop, CrossFadeIn, CrossFadeOut
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.VideoClip import TextClip

logger = logging.getLogger(__name__)


class AlignmentStrategy(str, Enum):
    """时长对齐策略"""
    SLOW_MOTION = "slow_motion"
    LOOP = "loop"


@dataclass
class ShotArtifact:
    """单个镜头的产出物"""
    shot_id: int
    video_path: str
    audio_path: Optional[str] = None
    dialogue: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    
    @property
    def duration(self) -> float:
        """计算镜头时长"""
        return self.end_time - self.start_time


@dataclass
class SubtitleEntry:
    """字幕条目"""
    start_time: float
    end_time: float
    text: str


def generate_srt(
    entries: List[SubtitleEntry],
    output_path: str
) -> str:
    """
    生成 SRT 字幕文件
    
    Args:
        entries: 字幕条目列表
        output_path: 输出文件路径
        
    Returns:
        生成的 SRT 文件路径
    """
    def format_time(seconds: float) -> str:
        """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    lines: List[str] = []
    for idx, entry in enumerate(entries, start=1):
        lines.append(str(idx))
        lines.append(f"{format_time(entry.start_time)} --> {format_time(entry.end_time)}")
        lines.append(entry.text)
        lines.append("")
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    logger.info(f"Generated SRT file: {output_path} with {len(entries)} entries")
    return output_path


def _align_video_to_audio(
    video_clip: VideoFileClip,
    audio_duration: float,
    strategy: AlignmentStrategy
) -> VideoFileClip:
    """
    对齐视频时长到音频时长
    
    Args:
        video_clip: 视频片段
        audio_duration: 目标音频时长
        strategy: 对齐策略
        
    Returns:
        对齐后的视频片段
    """
    video_duration = video_clip.duration
    
    if abs(video_duration - audio_duration) < 0.1:
        return video_clip
    
    if video_duration < audio_duration:
        if strategy == AlignmentStrategy.SLOW_MOTION:
            speed_factor = video_duration / audio_duration
            logger.debug(f"Applying slow-motion: speed={speed_factor:.2f}x")
            return video_clip.with_speed_scaled(speed_factor)
        else:
            logger.debug(f"Applying loop to extend from {video_duration:.2f}s to {audio_duration:.2f}s")
            return video_clip.with_effects([Loop(duration=audio_duration)])
    else:
        logger.debug(f"Trimming video from {video_duration:.2f}s to {audio_duration:.2f}s")
        return video_clip.subclipped(0, audio_duration)


def assemble_shots(
    shots: List[ShotArtifact],
    output_path: str,
    alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP,
    crossfade_duration: float = 0.5,
    fps: int = 24
) -> str:
    """
    逐镜头拼接视频
    
    Args:
        shots: 镜头产出物列表
        output_path: 输出视频路径
        alignment_strategy: 时长对齐策略
        crossfade_duration: 转场时长（秒）
        fps: 输出帧率
        
    Returns:
        生成的视频文件路径
    """
    if not shots:
        raise ValueError("No shots provided for assembly")
    
    logger.info(f"Assembling {len(shots)} shots with {alignment_strategy.value} strategy")
    
    clips: List[VideoFileClip] = []
    
    for i, shot in enumerate(shots):
        logger.debug(f"Processing shot {shot.shot_id}: {shot.video_path}")
        
        try:
            video_clip = VideoFileClip(shot.video_path)
        except Exception as e:
            logger.error(f"Failed to load video for shot {shot.shot_id}: {e}")
            raise
        
        if shot.audio_path and os.path.exists(shot.audio_path):
            try:
                audio_clip = AudioFileClip(shot.audio_path)
                video_clip = _align_video_to_audio(
                    video_clip, 
                    audio_clip.duration, 
                    alignment_strategy
                )
                video_clip = video_clip.with_audio(audio_clip)
                logger.debug(f"Shot {shot.shot_id}: aligned to audio duration {audio_clip.duration:.2f}s")
            except Exception as e:
                logger.warning(f"Failed to load audio for shot {shot.shot_id}: {e}")
        
        if crossfade_duration > 0 and len(shots) > 1:
            if i > 0:
                video_clip = video_clip.with_effects([CrossFadeIn(crossfade_duration)])
            if i < len(shots) - 1:
                video_clip = video_clip.with_effects([CrossFadeOut(crossfade_duration)])
        
        clips.append(video_clip)
    
    if crossfade_duration > 0 and len(clips) > 1:
        final_clip = concatenate_videoclips(
            clips, 
            method="compose",
            padding=-crossfade_duration
        )
    else:
        final_clip = concatenate_videoclips(clips, method="compose")
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    logger.info(f"Writing final video: {output_path} (duration: {final_clip.duration:.2f}s)")
    final_clip.write_videofile(
        output_path, 
        fps=fps, 
        codec="libx264",
        audio_codec="aac",
        logger=None
    )
    
    for clip in clips:
        clip.close()
    final_clip.close()
    
    logger.info(f"Successfully assembled video: {output_path}")
    return output_path


def generate_srt_from_shots(
    shots: List[ShotArtifact],
    output_path: str
) -> str:
    """
    从镜头列表生成 SRT 字幕文件
    
    Args:
        shots: 镜头产出物列表（需包含 dialogue 和时间信息）
        output_path: 输出 SRT 文件路径
        
    Returns:
        生成的 SRT 文件路径
    """
    entries: List[SubtitleEntry] = []
    current_time = 0.0
    
    for shot in shots:
        if shot.dialogue:
            duration = shot.duration if shot.duration > 0 else 3.0
            entries.append(SubtitleEntry(
                start_time=current_time,
                end_time=current_time + duration,
                text=shot.dialogue
            ))
        if shot.audio_path and os.path.exists(shot.audio_path):
            try:
                audio = AudioFileClip(shot.audio_path)
                current_time += audio.duration
                audio.close()
            except Exception:
                current_time += shot.duration if shot.duration > 0 else 3.0
        else:
            current_time += shot.duration if shot.duration > 0 else 3.0
    
    return generate_srt(entries, output_path)


def add_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    font: str = "Arial",
    font_size: int = 24,
    font_color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2
) -> str:
    """
    将 SRT 字幕嵌入视频
    
    Args:
        video_path: 输入视频路径
        srt_path: SRT 字幕文件路径
        output_path: 输出视频路径
        font: 字体名称
        font_size: 字体大小
        font_color: 字体颜色
        stroke_color: 描边颜色
        stroke_width: 描边宽度
        
    Returns:
        生成的视频文件路径
    """
    logger.info(f"Adding subtitles to video: {video_path}")
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")
    
    video = VideoFileClip(video_path)
    
    def make_text_clip(txt: str) -> TextClip:
        return TextClip(
            text=txt,
            font=font,
            font_size=font_size,
            color=font_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method="caption",
            size=(video.w * 0.9, None)
        )
    
    subtitles = SubtitlesClip(srt_path, make_text_clip)
    subtitles = subtitles.with_position(("center", 0.85), relative=True)
    
    final = CompositeVideoClip([video, subtitles])
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    final.write_videofile(
        output_path,
        fps=video.fps or 24,
        codec="libx264",
        audio_codec="aac",
        logger=None
    )
    
    video.close()
    final.close()
    
    logger.info(f"Successfully added subtitles: {output_path}")
    return output_path


def assemble_video(
    video_paths: List[str], 
    audio_path: str, 
    output_path: str,
    alignment_strategy: AlignmentStrategy = AlignmentStrategy.LOOP
) -> str:
    """
    拼接视频并与音频对齐（兼容旧接口）
    
    Args:
        video_paths: 视频文件路径列表
        audio_path: 音频文件路径
        output_path: 输出视频路径
        alignment_strategy: 对齐策略
        
    Returns:
        生成的视频文件路径
    """
    logger.info(f"Assembling {len(video_paths)} videos with audio: {audio_path}")
    
    try:
        clips = [VideoFileClip(p) for p in video_paths]
        final_video_clip = concatenate_videoclips(clips)

        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        video_duration = final_video_clip.duration

        logger.debug(f"Video Duration: {video_duration}s, Audio Duration: {audio_duration}s")

        final_video_clip = _align_video_to_audio(
            final_video_clip, 
            audio_duration, 
            alignment_strategy
        )

        final_video_clip = final_video_clip.with_audio(audio_clip)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        final_video_clip.write_videofile(output_path, fps=24, logger=None)
        
        for clip in clips:
            clip.close()
        final_video_clip.close()
        audio_clip.close()
        
        logger.info(f"Successfully created: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error assembling video: {e}")
        raise
