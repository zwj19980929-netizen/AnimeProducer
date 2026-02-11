import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ShotDraft(BaseModel):
    """LLM 输出的分镜草稿"""
    duration: float = 3.0
    scene_description: str
    visual_prompt: str
    camera_movement: str = "static"
    characters_in_shot: List[str] = []
    dialogue: Optional[str] = None
    action_type: Optional[str] = None
    # 情感字段
    emotion: str = Field(
        default="neutral",
        description="镜头情感: happy, sad, angry, fearful, surprised, excited, tense, neutral"
    )
    emotion_intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="情感强度 0-1"
    )


class Storyboard(BaseModel):
    """LLM 输出的故事板"""
    shots: List[ShotDraft]


# 预设风格配置
STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "ancient_chinese_wuxia": {
        "name": "Ancient Chinese Wuxia",
        "guidelines": "Ancient Chinese Wuxia martial arts world",
        "forbidden": ["cars", "phones", "modern clothes", "glasses", "concrete walls", "electricity", "plastic", "modern buildings"],
        "mandatory_atmosphere": "Ethereal, misty, historical",
        "default_props": "wooden ming-dynasty furniture, silk robes, bamboo, paper lanterns, ink paintings",
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "guidelines": "Neon-lit dystopian future",
        "forbidden": ["nature", "clean environments", "traditional clothing"],
        "mandatory_atmosphere": "Dark, neon, rain-soaked",
        "default_props": "holographic displays, cybernetic implants, flying vehicles",
    },
    "modern_urban": {
        "name": "Modern Urban",
        "guidelines": "Contemporary city setting",
        "forbidden": [],
        "mandatory_atmosphere": "Realistic, contemporary",
        "default_props": "modern furniture, smartphones, cars",
    },
}


class ScriptParser:
    def __init__(self):
        from integrations.llm_client import llm_client
        self.llm = llm_client

    def parse_novel_to_storyboard(
        self,
        novel_text: str,
        style_config: Optional[Dict[str, Any]] = None
    ) -> List[ShotDraft]:
        """
        将小说文本解析为分镜列表。

        Args:
            novel_text: 小说文本
            style_config: 风格配置，可以是预设名称或自定义配置
                - preset: 预设名称 (ancient_chinese_wuxia, cyberpunk, modern_urban)
                - guidelines: 全局美术风格指导
                - forbidden: 禁止出现的元素列表
                - mandatory_atmosphere: 必须的氛围
                - default_props: 默认道具描述

        Returns:
            分镜列表
        """
        # 构建风格指导
        style_guidelines = self._build_style_guidelines(style_config)

        prompt = f"""{style_guidelines}

You are a professional movie director and storyboard artist.
Convert the following novel text into a detailed storyboard (list of shots).

**CRITICAL RULES (铁律):**
1. FORBIDDEN: Do not create shots where characters just stand and talk while a narrator speaks the internal monologue.
2. REQUIRED: Every shot must have MOVEMENT - characters must be DOING something visible.
3. REQUIRED: Every visual description MUST align with the GLOBAL ART STYLE above.
4. If the text is generic (e.g. "he sat down"), you MUST describe specific period-appropriate details.

Rules:
1. Break down the text into visual shots (aim for 5-15 shots depending on content length).
2. Estimate duration for each shot (typically 2-5 seconds).
3. Provide detailed visual prompts for image generation (in English, describe the scene visually).
4. Specify camera movements (e.g., "static", "pan left", "zoom in", "tracking shot").
5. Extract dialogue if any (keep original language).
6. Identify characters present in the shot by name.
7. Specify action_type if applicable (e.g., "dialogue", "action", "transition").

**IMPORTANT - Emotion Analysis:**
8. For each shot, analyze the emotional tone based on dialogue, action, and context:
   - emotion: Choose from: happy, sad, angry, fearful, surprised, excited, tense, neutral
   - emotion_intensity: A number from 0.0 to 1.0 indicating how strong the emotion is
     * 0.0-0.3: Mild emotion
     * 0.4-0.6: Moderate emotion
     * 0.7-1.0: Strong/intense emotion

Emotion Guidelines:
- happy: Joy, satisfaction, relief, amusement (笑、开心、满足)
- sad: Sorrow, disappointment, grief, melancholy (悲伤、失落、难过)
- angry: Rage, frustration, annoyance, hatred (愤怒、恼火、不满)
- fearful: Fear, anxiety, worry, dread (恐惧、害怕、担忧)
- surprised: Shock, astonishment, disbelief (惊讶、震惊、意外)
- excited: Enthusiasm, anticipation, thrill (激动、热血、兴奋)
- tense: Suspense, alertness, seriousness (紧张、严肃、警惕)
- neutral: Calm, matter-of-fact, descriptive (平静、中性、陈述)

Consider:
- The dialogue content and punctuation (！表示强烈情感，...表示犹豫或悲伤)
- The action being performed
- The context and what's happening in the story
- Character expressions and body language implied by the text

Novel Text:
{novel_text}
"""

        try:
            logger.info("Parsing novel to storyboard via LLM...")
            storyboard = self.llm.generate_structured_output(prompt, Storyboard)
            if storyboard and storyboard.shots:
                logger.info(f"Successfully parsed {len(storyboard.shots)} shots")
                # 记录情感分析结果
                for i, shot in enumerate(storyboard.shots):
                    logger.debug(
                        f"Shot {i+1}: emotion={shot.emotion}, "
                        f"intensity={shot.emotion_intensity:.2f}"
                    )
                return storyboard.shots
            else:
                logger.warning("LLM returned empty storyboard")
                return []
        except Exception as e:
            logger.error(f"Failed to parse script: {e}")
            return []

    def _build_style_guidelines(self, style_config: Optional[Dict[str, Any]]) -> str:
        """构建风格指导文本。"""
        if not style_config:
            return ""

        # 如果指定了预设
        preset_name = style_config.get("preset")
        if preset_name and preset_name in STYLE_PRESETS:
            config = STYLE_PRESETS[preset_name].copy()
            # 允许覆盖预设值
            config.update({k: v for k, v in style_config.items() if k != "preset" and v})
        else:
            config = style_config

        guidelines = config.get("guidelines", "")
        forbidden = config.get("forbidden", [])
        atmosphere = config.get("mandatory_atmosphere", "")
        default_props = config.get("default_props", "")

        parts = ["=== GLOBAL ART DIRECTION ==="]

        if guidelines:
            parts.append(f"GLOBAL ART STYLE: {guidelines}")

        if forbidden:
            forbidden_str = ", ".join(forbidden)
            parts.append(f"FORBIDDEN ELEMENTS (never include): {forbidden_str}")

        if atmosphere:
            parts.append(f"MANDATORY ATMOSPHERE: {atmosphere}")

        if default_props:
            parts.append(f"DEFAULT PROPS/SETTING: {default_props}")

        parts.append("=" * 30)

        return "\n".join(parts)

    def analyze_dialogue_emotion(self, dialogue: str, context: str = "") -> dict:
        """
        单独分析对白的情感（用于已有分镜但缺少情感信息的情况）

        Args:
            dialogue: 对白文本
            context: 上下文信息

        Returns:
            包含 emotion 和 emotion_intensity 的字典
        """
        from core.emotion_analyzer import emotion_analyzer

        result = emotion_analyzer.analyze(dialogue, context)
        return {
            "emotion": result.emotion,
            "emotion_intensity": result.intensity,
        }


script_parser = ScriptParser()
