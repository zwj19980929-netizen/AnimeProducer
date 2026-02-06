"""Audio Layers - 多轨音频系统

支持对白、BGM、音效、环境音的多轨混合。
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)


class AudioLayerType(str, Enum):
    """音频层类型"""
    DIALOGUE = "dialogue"   # 对白
    BGM = "bgm"             # 背景音乐
    SFX = "sfx"             # 音效
    AMBIENT = "ambient"     # 环境音


@dataclass
class AudioClip:
    """音频片段"""
    path: str                    # 音频文件路径
    start_time: float = 0.0     # 开始时间（秒）
    duration: Optional[float] = None  # 持续时间（None 表示使用原始时长）
    volume: float = 1.0         # 音量 (0.0 - 1.0)
    fade_in: float = 0.0        # 淡入时长（秒）
    fade_out: float = 0.0       # 淡出时长（秒）
    loop: bool = False          # 是否循环


@dataclass
class AudioLayer:
    """音频层"""
    layer_type: AudioLayerType
    clips: List[AudioClip] = field(default_factory=list)
    base_volume: float = 1.0           # 基础音量
    ducking_enabled: bool = False      # 是否在对白时降低音量
    ducking_amount: float = 0.3        # 降低到原音量的比例 (0.3 = 降到 30%)
    ducking_attack: float = 0.1        # ducking 淡入时间
    ducking_release: float = 0.3       # ducking 淡出时间


@dataclass
class SFXTrigger:
    """音效触发点"""
    sfx_id: str                  # 音效 ID
    trigger_time: float          # 触发时间（秒）
    action_type: str             # 动作类型
    volume: float = 1.0          # 音量


@dataclass
class AudioMixRequest:
    """混音请求"""
    shot_id: int
    total_duration: float                           # 总时长
    dialogue_layer: Optional[AudioLayer] = None     # 对白层
    bgm_layer: Optional[AudioLayer] = None          # BGM 层
    sfx_layer: Optional[AudioLayer] = None          # 音效层
    ambient_layer: Optional[AudioLayer] = None      # 环境音层
    output_path: Optional[str] = None               # 输出路径


@dataclass
class AudioMixResult:
    """混音结果"""
    output_path: str
    duration: float
    layers_mixed: List[str]


class SFXLibrary:
    """音效库"""

    # 动作关键词到音效 ID 的映射
    ACTION_SFX_MAP: Dict[str, str] = {
        # 脚步声
        "walk": "footstep_normal",
        "walking": "footstep_normal",
        "run": "footstep_running",
        "running": "footstep_running",

        # 门
        "door": "door_open",
        "open door": "door_open",
        "close door": "door_close",
        "knock": "door_knock",

        # 天气
        "rain": "ambient_rain",
        "raining": "ambient_rain",
        "thunder": "thunder_strike",
        "lightning": "thunder_strike",
        "wind": "ambient_wind",
        "storm": "ambient_storm",

        # 战斗
        "sword": "sword_slash",
        "slash": "sword_slash",
        "punch": "impact_punch",
        "kick": "impact_kick",
        "hit": "impact_hit",
        "explosion": "explosion_medium",
        "gunshot": "gunshot",
        "gun": "gunshot",

        # 交通
        "car": "vehicle_car",
        "motorcycle": "vehicle_motorcycle",
        "train": "vehicle_train",

        # 环境
        "crowd": "ambient_crowd",
        "city": "ambient_city",
        "forest": "ambient_forest",
        "ocean": "ambient_ocean",
        "beach": "ambient_beach",
        "night": "ambient_night",

        # 其他
        "phone": "phone_ring",
        "bell": "bell_ring",
        "glass": "glass_break",
        "water": "water_splash",
        "fire": "fire_crackling",
    }

    def __init__(self, sfx_dir: Optional[str] = None):
        """
        初始化音效库

        Args:
            sfx_dir: 音效文件目录
        """
        self.sfx_dir = Path(sfx_dir) if sfx_dir else settings.ASSETS_DIR / "sfx"
        self._cache: Dict[str, str] = {}

    def get_sfx_path(self, sfx_id: str) -> Optional[str]:
        """
        获取音效文件路径

        Args:
            sfx_id: 音效 ID

        Returns:
            音效文件路径，如果不存在则返回 None
        """
        if sfx_id in self._cache:
            return self._cache[sfx_id]

        # 尝试不同的文件扩展名
        extensions = [".mp3", ".wav", ".ogg", ".flac"]
        for ext in extensions:
            path = self.sfx_dir / f"{sfx_id}{ext}"
            if path.exists():
                self._cache[sfx_id] = str(path)
                return str(path)

        logger.warning(f"SFX not found: {sfx_id}")
        return None

    def detect_sfx_from_prompt(self, visual_prompt: str) -> List[str]:
        """
        从视觉提示词中检测需要的音效

        Args:
            visual_prompt: 视觉提示词

        Returns:
            检测到的音效 ID 列表
        """
        detected: List[str] = []
        prompt_lower = visual_prompt.lower()

        for keyword, sfx_id in self.ACTION_SFX_MAP.items():
            if keyword in prompt_lower:
                if sfx_id not in detected:
                    detected.append(sfx_id)

        logger.debug(f"Detected SFX from prompt: {detected}")
        return detected

    def list_available_sfx(self) -> List[str]:
        """列出所有可用的音效"""
        if not self.sfx_dir.exists():
            return []

        available = []
        for file in self.sfx_dir.iterdir():
            if file.suffix.lower() in [".mp3", ".wav", ".ogg", ".flac"]:
                available.append(file.stem)

        return available


class BGMLibrary:
    """背景音乐库"""

    # 场景/情绪到 BGM 的映射
    MOOD_BGM_MAP: Dict[str, List[str]] = {
        "action": ["bgm_action_01", "bgm_action_02", "bgm_battle"],
        "tense": ["bgm_tense_01", "bgm_suspense"],
        "romantic": ["bgm_romantic_01", "bgm_love"],
        "sad": ["bgm_sad_01", "bgm_melancholy"],
        "happy": ["bgm_happy_01", "bgm_cheerful"],
        "peaceful": ["bgm_peaceful_01", "bgm_calm"],
        "mysterious": ["bgm_mysterious_01", "bgm_mystery"],
        "epic": ["bgm_epic_01", "bgm_dramatic"],
        "comedy": ["bgm_comedy_01", "bgm_funny"],
        "horror": ["bgm_horror_01", "bgm_scary"],
        "default": ["bgm_neutral_01"],
    }

    def __init__(self, bgm_dir: Optional[str] = None):
        """
        初始化 BGM 库

        Args:
            bgm_dir: BGM 文件目录
        """
        self.bgm_dir = Path(bgm_dir) if bgm_dir else settings.ASSETS_DIR / "bgm"
        self._cache: Dict[str, str] = {}

    def get_bgm_path(self, bgm_id: str) -> Optional[str]:
        """获取 BGM 文件路径"""
        if bgm_id in self._cache:
            return self._cache[bgm_id]

        extensions = [".mp3", ".wav", ".ogg", ".flac"]
        for ext in extensions:
            path = self.bgm_dir / f"{bgm_id}{ext}"
            if path.exists():
                self._cache[bgm_id] = str(path)
                return str(path)

        logger.warning(f"BGM not found: {bgm_id}")
        return None

    def select_bgm_for_mood(self, mood: str) -> Optional[str]:
        """
        根据情绪选择 BGM

        Args:
            mood: 情绪/场景类型

        Returns:
            BGM 文件路径
        """
        mood_lower = mood.lower()

        # 查找匹配的情绪
        bgm_candidates = self.MOOD_BGM_MAP.get(mood_lower, self.MOOD_BGM_MAP["default"])

        # 返回第一个存在的 BGM
        for bgm_id in bgm_candidates:
            path = self.get_bgm_path(bgm_id)
            if path:
                return path

        return None

    def detect_mood_from_prompt(self, visual_prompt: str) -> str:
        """
        从视觉提示词中检测情绪

        Args:
            visual_prompt: 视觉提示词

        Returns:
            检测到的情绪
        """
        prompt_lower = visual_prompt.lower()

        mood_keywords = {
            "action": ["fight", "battle", "action", "combat", "attack", "run"],
            "tense": ["tense", "danger", "threat", "chase", "escape"],
            "romantic": ["love", "romantic", "kiss", "hug", "couple", "date"],
            "sad": ["sad", "cry", "tears", "grief", "loss", "farewell"],
            "happy": ["happy", "joy", "laugh", "smile", "celebrate", "party"],
            "peaceful": ["peaceful", "calm", "relax", "quiet", "serene"],
            "mysterious": ["mystery", "secret", "hidden", "unknown", "strange"],
            "epic": ["epic", "dramatic", "grand", "heroic", "climax"],
            "horror": ["horror", "scary", "fear", "dark", "creepy"],
        }

        for mood, keywords in mood_keywords.items():
            for keyword in keywords:
                if keyword in prompt_lower:
                    return mood

        return "default"


class AudioMixer:
    """多轨混音器，混音结果上传到 OSS"""

    def __init__(self):
        """初始化混音器"""
        self.logger = logging.getLogger(f"{__name__}.AudioMixer")

    def mix(self, request: AudioMixRequest) -> AudioMixResult:
        """
        混合多个音频层

        Args:
            request: 混音请求

        Returns:
            混音结果（包含 OSS URL）
        """
        try:
            from pydub import AudioSegment
        except ImportError:
            self.logger.error("pydub not installed. Run: pip install pydub")
            raise

        import tempfile

        self.logger.info(f"Mixing audio for shot {request.shot_id}")

        # 创建空白音轨
        total_duration_ms = int(request.total_duration * 1000)
        mixed = AudioSegment.silent(duration=total_duration_ms)

        layers_mixed: List[str] = []

        # 1. 叠加环境音（最底层）
        if request.ambient_layer and request.ambient_layer.clips:
            self.logger.debug("Adding ambient layer...")
            ambient_audio = self._process_layer(request.ambient_layer, total_duration_ms)
            if ambient_audio:
                mixed = mixed.overlay(ambient_audio)
                layers_mixed.append("ambient")

        # 2. 叠加 BGM
        if request.bgm_layer and request.bgm_layer.clips:
            self.logger.debug("Adding BGM layer...")
            bgm_audio = self._process_layer(request.bgm_layer, total_duration_ms)
            if bgm_audio:
                # 如果启用了 ducking 且有对白层，应用 ducking
                if request.bgm_layer.ducking_enabled and request.dialogue_layer:
                    bgm_audio = self._apply_ducking(
                        bgm_audio,
                        request.dialogue_layer,
                        request.bgm_layer.ducking_amount
                    )
                mixed = mixed.overlay(bgm_audio)
                layers_mixed.append("bgm")

        # 3. 叠加音效
        if request.sfx_layer and request.sfx_layer.clips:
            self.logger.debug("Adding SFX layer...")
            sfx_audio = self._process_layer(request.sfx_layer, total_duration_ms)
            if sfx_audio:
                mixed = mixed.overlay(sfx_audio)
                layers_mixed.append("sfx")

        # 4. 叠加对白（最顶层）
        if request.dialogue_layer and request.dialogue_layer.clips:
            self.logger.debug("Adding dialogue layer...")
            dialogue_audio = self._process_layer(request.dialogue_layer, total_duration_ms)
            if dialogue_audio:
                mixed = mixed.overlay(dialogue_audio)
                layers_mixed.append("dialogue")

        # 导出到临时文件
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_file.close()

        try:
            mixed.export(temp_file.name, format="mp3")

            # 上传到 OSS
            from integrations.oss_service import require_oss
            oss = require_oss()

            filename = f"mixed_audio_shot_{request.shot_id}"
            output_url = oss.upload_file(temp_file.name, folder="audio")
            self.logger.info(f"Mixed audio uploaded to OSS: {output_url} (layers: {layers_mixed})")

            return AudioMixResult(
                output_path=output_url,
                duration=request.total_duration,
                layers_mixed=layers_mixed
            )
        finally:
            # 清理临时文件
            if os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass

    def _process_layer(
        self,
        layer: AudioLayer,
        total_duration_ms: int
    ) -> Optional["AudioSegment"]:
        """处理单个音频层"""
        from pydub import AudioSegment

        result = AudioSegment.silent(duration=total_duration_ms)

        for clip in layer.clips:
            if not os.path.exists(clip.path):
                self.logger.warning(f"Audio file not found: {clip.path}")
                continue

            try:
                audio = AudioSegment.from_file(clip.path)

                # 应用音量
                volume_db = 20 * (clip.volume * layer.base_volume)
                if volume_db < 0:
                    audio = audio + volume_db  # pydub 使用 dB

                # 应用淡入淡出
                if clip.fade_in > 0:
                    audio = audio.fade_in(int(clip.fade_in * 1000))
                if clip.fade_out > 0:
                    audio = audio.fade_out(int(clip.fade_out * 1000))

                # 处理循环
                if clip.loop and clip.duration:
                    target_duration_ms = int(clip.duration * 1000)
                    while len(audio) < target_duration_ms:
                        audio = audio + audio
                    audio = audio[:target_duration_ms]

                # 裁剪到指定时长
                if clip.duration:
                    audio = audio[:int(clip.duration * 1000)]

                # 叠加到结果
                start_ms = int(clip.start_time * 1000)
                result = result.overlay(audio, position=start_ms)

            except Exception as e:
                self.logger.error(f"Error processing audio clip {clip.path}: {e}")

        return result

    def _apply_ducking(
        self,
        bgm: "AudioSegment",
        dialogue_layer: AudioLayer,
        duck_amount: float
    ) -> "AudioSegment":
        """
        在对白时段降低 BGM 音量

        Args:
            bgm: BGM 音频
            dialogue_layer: 对白层
            duck_amount: 降低到原音量的比例

        Returns:
            处理后的 BGM
        """
        from pydub import AudioSegment

        result = bgm

        # 计算降低的 dB 值
        duck_db = 20 * duck_amount - 20  # 例如 0.3 -> -10.5 dB

        for clip in dialogue_layer.clips:
            start_ms = int(clip.start_time * 1000)
            duration_ms = int((clip.duration or 3.0) * 1000)
            end_ms = start_ms + duration_ms

            # 确保不超出范围
            end_ms = min(end_ms, len(result))

            if start_ms < len(result):
                # 分割并降低音量
                before = result[:start_ms]
                during = result[start_ms:end_ms] + duck_db
                after = result[end_ms:]

                result = before + during + after

        return result


# 全局实例
sfx_library = SFXLibrary()
bgm_library = BGMLibrary()
audio_mixer = AudioMixer()
