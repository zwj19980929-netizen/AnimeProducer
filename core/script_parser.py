import logging
from typing import List
from pydantic import BaseModel
from core.models import Shot
from integrations.llm_client import llm_client

logger = logging.getLogger(__name__)


class Storyboard(BaseModel):
    shots: List[Shot]


class ScriptParser:
    def __init__(self):
        self.llm = llm_client

    def parse_novel_to_storyboard(self, novel_text: str) -> List[Shot]:
        """将小说文本解析为分镜列表"""
        prompt = f"""
        You are a professional movie director and storyboard artist.
        Convert the following novel text into a detailed storyboard (list of shots).

        Rules:
        1. Break down the text into visual shots.
        2. Estimate duration for each shot.
        3. Provide detailed visual prompts for image generation (in English).
        4. Specify camera movements.
        5. Extract dialogue if any.
        6. Identify characters present in the shot.

        Novel Text:
        {novel_text}
        """

        try:
            storyboard = self.llm.generate_structured_output(prompt, Storyboard)
            return storyboard.shots
        except Exception as e:
            logger.error(f"Failed to parse script: {e}")
            return []


script_parser = ScriptParser()
