import logging
from typing import List, Optional
from pydantic import BaseModel

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

Novel Text:
{novel_text}
"""

        try:
            logger.info("Parsing novel to storyboard via LLM...")
            storyboard = self.llm.generate_structured_output(prompt, Storyboard)
            if storyboard and storyboard.shots:
                logger.info(f"Successfully parsed {len(storyboard.shots)} shots")
                return storyboard.shots
            else:
                logger.warning("LLM returned empty storyboard")
                return []
        except Exception as e:
            logger.error(f"Failed to parse script: {e}")
            return []


script_parser = ScriptParser()
