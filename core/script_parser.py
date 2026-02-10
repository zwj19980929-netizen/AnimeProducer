import logging
from typing import List, Optional
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


class ScriptParser:
    def __init__(self):
        from integrations.llm_client import llm_client
        self.llm = llm_client

    def parse_novel_to_storyboard(self, novel_text: str) -> List[ShotDraft]:
        """将小说文本解析为分镜列表"""
        prompt = f"""
You are a professional movie director and storyboard artist.
Convert the following novel text into a detailed storyboard (list of shots).

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
