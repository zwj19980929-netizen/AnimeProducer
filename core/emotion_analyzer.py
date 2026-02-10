"""
对白情感分析器

分析对白文本的情感，用于生成情感一致的语音和视频。
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# 情感类型定义
EMOTION_TYPES = [
    "happy",      # 开心、愉悦
    "sad",        # 悲伤、失落
    "angry",      # 愤怒、恼怒
    "fearful",    # 恐惧、害怕
    "surprised",  # 惊讶、震惊
    "excited",    # 激动、热血
    "tense",      # 紧张、悬疑
    "neutral",    # 平静、中性
]


@dataclass
class EmotionResult:
    """情感分析结果"""
    emotion: str  # 主要情感
    intensity: float  # 情感强度 0-1
    confidence: float  # 置信度 0-1
    secondary_emotion: Optional[str] = None  # 次要情感
    context: Optional[str] = None  # 情感上下文描述


class EmotionAnalysisResponse(BaseModel):
    """LLM 情感分析响应"""
    emotion: str = Field(description="主要情感类型")
    intensity: float = Field(ge=0, le=1, description="情感强度")
    secondary_emotion: Optional[str] = Field(default=None, description="次要情感")
    reasoning: str = Field(description="分析理由")


class DialogueEmotionAnalyzer:
    """对白情感分析器"""

    # 情感关键词映射（用于快速分析）
    EMOTION_KEYWORDS: Dict[str, List[str]] = {
        "happy": [
            "哈哈", "嘿嘿", "呵呵", "太好了", "太棒了", "开心", "高兴", "快乐",
            "耶", "好耶", "万岁", "真好", "太开心", "笑", "乐", "喜",
            "wonderful", "great", "happy", "joy", "excited"
        ],
        "sad": [
            "唉", "呜呜", "哭", "泪", "难过", "伤心", "悲伤", "痛苦",
            "可惜", "遗憾", "失落", "沮丧", "绝望", "心痛", "难受",
            "sad", "cry", "tears", "sorrow", "grief"
        ],
        "angry": [
            "混蛋", "可恶", "该死", "去死", "滚", "闭嘴", "愤怒", "恼火",
            "气死", "可恨", "讨厌", "烦", "怒", "火大", "岂有此理",
            "damn", "angry", "furious", "hate"
        ],
        "fearful": [
            "救命", "不要", "害怕", "恐惧", "可怕", "吓", "怕", "恐",
            "糟了", "完了", "危险", "小心", "逃", "躲",
            "help", "scared", "afraid", "fear", "terror"
        ],
        "surprised": [
            "什么", "怎么可能", "不可能", "竟然", "居然", "天哪", "我的天",
            "啊", "哇", "咦", "嗯", "这", "真的吗", "不会吧",
            "what", "how", "impossible", "really", "wow"
        ],
        "excited": [
            "冲啊", "来吧", "上", "杀", "战", "燃", "热血", "激动",
            "太燃了", "爽", "痛快", "带劲", "过瘾", "刺激",
            "go", "fight", "come on", "let's go"
        ],
        "tense": [
            "小心", "注意", "危险", "快", "赶紧", "紧张", "严肃",
            "安静", "别动", "等等", "停", "慢",
            "careful", "watch out", "danger", "wait"
        ],
    }

    # 标点符号情感强度修正
    PUNCTUATION_INTENSITY = {
        "！": 0.15,
        "!": 0.15,
        "？": 0.1,
        "?": 0.1,
        "...": -0.1,
        "……": -0.1,
        "！！": 0.25,
        "!!": 0.25,
        "？！": 0.2,
        "?!": 0.2,
        "！？": 0.2,
        "!?": 0.2,
    }

    # 情感到 TTS 参数的映射
    EMOTION_TTS_PARAMS: Dict[str, Dict] = {
        "happy": {
            "speed_modifier": 0.1,   # 语速加快
            "pitch_modifier": 2,     # 音调升高
            "tts_emotion": "happy",
        },
        "sad": {
            "speed_modifier": -0.1,  # 语速放慢
            "pitch_modifier": -2,    # 音调降低
            "tts_emotion": "sad",
        },
        "angry": {
            "speed_modifier": 0.2,   # 语速加快
            "pitch_modifier": 3,     # 音调升高
            "tts_emotion": "angry",
        },
        "fearful": {
            "speed_modifier": 0.15,  # 语速加快（紧张）
            "pitch_modifier": 1,     # 音调略升
            "tts_emotion": "fearful",
        },
        "surprised": {
            "speed_modifier": 0.1,
            "pitch_modifier": 4,     # 音调明显升高
            "tts_emotion": "surprised",
        },
        "excited": {
            "speed_modifier": 0.2,
            "pitch_modifier": 3,
            "tts_emotion": "happy",  # 大多数 TTS 用 happy 代替
        },
        "tense": {
            "speed_modifier": 0.05,
            "pitch_modifier": 0,
            "tts_emotion": "neutral",
        },
        "neutral": {
            "speed_modifier": 0,
            "pitch_modifier": 0,
            "tts_emotion": "neutral",
        },
    }

    # 情感到视觉标签的映射
    EMOTION_VISUAL_TAGS: Dict[str, Dict[str, List[str]]] = {
        "happy": {
            "expression": ["smile", "laughing", "happy", "bright eyes", "grin"],
            "body_language": ["relaxed posture", "open arms", "bouncy movement"],
            "atmosphere": ["warm lighting", "bright colors"],
        },
        "sad": {
            "expression": ["tears", "crying", "downcast eyes", "frown", "sad"],
            "body_language": ["slumped shoulders", "head down", "slow movement"],
            "atmosphere": ["dim lighting", "muted colors", "melancholy"],
        },
        "angry": {
            "expression": ["angry", "furrowed brows", "clenched teeth", "glaring", "scowl"],
            "body_language": ["tense posture", "clenched fists", "aggressive stance"],
            "atmosphere": ["red tint", "dramatic shadows", "intense"],
        },
        "fearful": {
            "expression": ["scared", "wide eyes", "trembling", "pale face", "fearful"],
            "body_language": ["cowering", "defensive posture", "backing away"],
            "atmosphere": ["dark shadows", "cold colors", "ominous"],
        },
        "surprised": {
            "expression": ["shocked", "wide eyes", "open mouth", "raised eyebrows"],
            "body_language": ["frozen", "stepping back", "hands up"],
            "atmosphere": ["dramatic lighting", "motion blur"],
        },
        "excited": {
            "expression": ["excited", "sparkling eyes", "grin", "flushed cheeks"],
            "body_language": ["dynamic pose", "jumping", "pumping fist"],
            "atmosphere": ["vibrant colors", "energy effects", "speed lines"],
        },
        "tense": {
            "expression": ["serious", "focused", "narrowed eyes", "determined"],
            "body_language": ["ready stance", "alert posture", "still"],
            "atmosphere": ["dramatic shadows", "contrast lighting"],
        },
        "neutral": {
            "expression": ["calm", "neutral expression", "serene"],
            "body_language": ["relaxed", "natural posture"],
            "atmosphere": ["normal lighting", "balanced colors"],
        },
    }

    def __init__(self, use_llm: bool = True):
        """
        初始化情感分析器

        Args:
            use_llm: 是否使用 LLM 进行深度分析（更准确但更慢）
        """
        self.use_llm = use_llm

    def analyze(
        self,
        dialogue: str,
        context: str = "",
        scene_description: str = "",
    ) -> EmotionResult:
        """
        分析对白的情感

        Args:
            dialogue: 对白文本
            context: 上下文信息（如前后对白）
            scene_description: 场景描述

        Returns:
            EmotionResult: 情感分析结果
        """
        if not dialogue or not dialogue.strip():
            return EmotionResult(
                emotion="neutral",
                intensity=0.5,
                confidence=1.0,
            )

        # 1. 快速关键词分析
        keyword_result = self._analyze_by_keywords(dialogue)

        # 2. 如果启用 LLM 且关键词分析置信度不高，使用 LLM 深度分析
        if self.use_llm and keyword_result.confidence < 0.7:
            try:
                llm_result = self._analyze_by_llm(dialogue, context, scene_description)
                if llm_result.confidence > keyword_result.confidence:
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM 情感分析失败，使用关键词分析结果: {e}")

        return keyword_result

    def _analyze_by_keywords(self, dialogue: str) -> EmotionResult:
        """基于关键词的快速情感分析"""
        dialogue_lower = dialogue.lower()

        # 统计各情感的匹配分数
        emotion_scores: Dict[str, float] = {emotion: 0.0 for emotion in EMOTION_TYPES}

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in dialogue_lower:
                    # 关键词匹配，增加分数
                    emotion_scores[emotion] += 1.0

        # 计算标点符号的情感强度修正
        intensity_modifier = 0.0
        for punct, modifier in self.PUNCTUATION_INTENSITY.items():
            if punct in dialogue:
                intensity_modifier += modifier

        # 找出最高分的情感
        max_emotion = max(emotion_scores, key=emotion_scores.get)
        max_score = emotion_scores[max_emotion]

        if max_score == 0:
            # 没有匹配到任何关键词
            return EmotionResult(
                emotion="neutral",
                intensity=0.5,
                confidence=0.3,  # 低置信度
            )

        # 计算置信度（基于匹配数量和是否有明显的主导情感）
        total_score = sum(emotion_scores.values())
        confidence = min(0.9, max_score / max(total_score, 1) * 0.5 + min(max_score, 3) * 0.15)

        # 计算情感强度
        base_intensity = min(0.9, 0.4 + max_score * 0.15)
        intensity = max(0.1, min(1.0, base_intensity + intensity_modifier))

        # 找次要情感
        sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
        secondary = sorted_emotions[1][0] if len(sorted_emotions) > 1 and sorted_emotions[1][1] > 0 else None

        return EmotionResult(
            emotion=max_emotion,
            intensity=intensity,
            confidence=confidence,
            secondary_emotion=secondary,
        )

    def _analyze_by_llm(
        self,
        dialogue: str,
        context: str,
        scene_description: str,
    ) -> EmotionResult:
        """使用 LLM 进行深度情感分析"""
        from integrations.llm_client import llm_client

        prompt = f"""分析以下对白的情感。

对白: "{dialogue}"
{f'场景: {scene_description}' if scene_description else ''}
{f'上下文: {context}' if context else ''}

请分析这段对白表达的情感，返回 JSON 格式：
{{
    "emotion": "情感类型，从以下选择: happy, sad, angry, fearful, surprised, excited, tense, neutral",
    "intensity": 0.0-1.0 之间的数字，表示情感强度,
    "secondary_emotion": "次要情感（可选）",
    "reasoning": "简短的分析理由"
}}

注意：
- happy: 开心、愉悦、满足
- sad: 悲伤、失落、沮丧
- angry: 愤怒、恼怒、不满
- fearful: 恐惧、害怕、担忧
- surprised: 惊讶、震惊、意外
- excited: 激动、热血、兴奋
- tense: 紧张、严肃、警惕
- neutral: 平静、中性、陈述

只返回 JSON，不要其他内容。"""

        try:
            result = llm_client.generate_structured_output(
                prompt,
                EmotionAnalysisResponse,
                temperature=0.1
            )

            if result:
                return EmotionResult(
                    emotion=result.emotion if result.emotion in EMOTION_TYPES else "neutral",
                    intensity=result.intensity,
                    confidence=0.85,  # LLM 分析的置信度较高
                    secondary_emotion=result.secondary_emotion,
                    context=result.reasoning,
                )
        except Exception as e:
            logger.error(f"LLM 情感分析出错: {e}")

        # 失败时返回中性
        return EmotionResult(
            emotion="neutral",
            intensity=0.5,
            confidence=0.3,
        )

    def get_tts_params(
        self,
        emotion: str,
        intensity: float,
        base_speed: float = 1.0,
        base_pitch: float = 0.0,
    ) -> Dict:
        """
        根据情感获取 TTS 参数

        Args:
            emotion: 情感类型
            intensity: 情感强度
            base_speed: 基础语速
            base_pitch: 基础音调

        Returns:
            TTS 参数字典
        """
        params = self.EMOTION_TTS_PARAMS.get(emotion, self.EMOTION_TTS_PARAMS["neutral"])

        # 根据强度调整参数
        speed_mod = params["speed_modifier"] * intensity
        pitch_mod = params["pitch_modifier"] * intensity

        return {
            "speed": max(0.5, min(2.0, base_speed + speed_mod)),
            "pitch": max(-12, min(12, base_pitch + pitch_mod)),
            "emotion": params["tts_emotion"],
        }

    def get_visual_tags(
        self,
        emotion: str,
        intensity: float,
    ) -> str:
        """
        根据情感获取视觉标签

        Args:
            emotion: 情感类型
            intensity: 情感强度

        Returns:
            视觉标签字符串
        """
        tags = self.EMOTION_VISUAL_TAGS.get(emotion, self.EMOTION_VISUAL_TAGS["neutral"])

        # 根据强度选择标签数量
        num_expression = int(1 + intensity * 2)  # 1-3 个表情标签
        num_body = int(intensity * 2)  # 0-2 个肢体标签

        selected_tags = []
        selected_tags.extend(tags["expression"][:num_expression])
        if num_body > 0:
            selected_tags.extend(tags["body_language"][:num_body])

        return ", ".join(selected_tags)

    def enhance_visual_prompt(
        self,
        visual_prompt: str,
        emotion: str,
        intensity: float,
    ) -> str:
        """
        增强视觉提示词，加入情感标签

        Args:
            visual_prompt: 原始视觉提示词
            emotion: 情感类型
            intensity: 情感强度

        Returns:
            增强后的视觉提示词
        """
        emotion_tags = self.get_visual_tags(emotion, intensity)

        if emotion_tags:
            return f"{visual_prompt}, {emotion_tags}"
        return visual_prompt


# 全局实例
emotion_analyzer = DialogueEmotionAnalyzer(use_llm=True)
