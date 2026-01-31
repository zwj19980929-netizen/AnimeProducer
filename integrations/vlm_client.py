import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScoreDetails:
    """Detailed scoring breakdown for a keyframe candidate."""
    prompt_match_score: float = 0.0
    character_consistency_score: float = 0.0
    composition_score: float = 0.0
    reasoning: str = ""


@dataclass
class ScoredCandidate:
    """A keyframe candidate with its evaluation scores."""
    candidate_id: str
    image_path: str
    scores: ScoreDetails = field(default_factory=ScoreDetails)
    weighted_total: float = 0.0
    raw_response: Dict[str, Any] = field(default_factory=dict)


class VLMClient:
    """视觉语言模型客户端，用于关键帧评分。"""

    SCORE_WEIGHTS = {
        "prompt_match": 0.4,
        "character_consistency": 0.35,
        "composition": 0.25,
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        """初始化 VLM 客户端。"""
        self.provider = provider or settings.VLM_BACKEND
        self.model = model or settings.VLM_MODEL
        self._mock_mode = mock_mode
        self._client = None

        if not self._is_mock_mode():
            self._init_client()

    def _is_mock_mode(self) -> bool:
        """检查是否为模拟模式。"""
        if self._mock_mode is not None:
            return self._mock_mode

        if self.provider == "openai":
            import os
            return not os.getenv("OPENAI_API_KEY")
        return not settings.GOOGLE_API_KEY

    def _init_client(self) -> None:
        """初始化 VLM 客户端。"""
        try:
            if self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI()
            else:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self._client = ChatGoogleGenerativeAI(
                    google_api_key=settings.GOOGLE_API_KEY,
                    model=self.model,
                    temperature=0.2,
                )
        except Exception as e:
            logger.warning(f"Failed to initialize VLM client: {e}. Falling back to mock mode.")
            self._mock_mode = True

    def _encode_image(self, image_path: str) -> str:
        """将图像编码为 base64。"""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with open(path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _get_mime_type(self, image_path: str) -> str:
        """根据文件扩展名获取 MIME 类型。"""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/jpeg")

    def _build_scoring_prompt(
        self,
        scene_description: str,
        characters: List[Dict[str, Any]],
    ) -> str:
        """构建 VLM 评分提示词。"""
        char_desc = "\n".join([
            f"- {c.get('name', 'Unknown')}: {c.get('description', 'No description')}"
            for c in characters
        ])

        return f"""You are an expert anime art director evaluating keyframe candidates.

Scene Description:
{scene_description}

Characters in scene:
{char_desc}

Evaluate this image on three dimensions (score 0-100):

1. **prompt_match_score**: How well does this image match the scene description?
   - Consider: scene elements, mood, action, setting accuracy

2. **character_consistency_score**: How accurately are the characters depicted?
   - Consider: visual appearance, poses, expressions matching the scene

3. **composition_score**: How good is the overall visual composition?
   - Consider: framing, balance, visual flow, anime art quality

Return your evaluation as valid JSON:
{{
    "prompt_match_score": <0-100>,
    "character_consistency_score": <0-100>,
    "composition_score": <0-100>,
    "reasoning": "<brief explanation of scores>"
}}

Only return the JSON, no other text."""

    def _parse_score_response(self, response_text: str) -> Dict[str, Any]:
        """解析 VLM 响应以提取分数。"""
        try:
            text = response_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
                text = text.strip()

            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse VLM response: {e}")
            return {
                "prompt_match_score": 50,
                "character_consistency_score": 50,
                "composition_score": 50,
                "reasoning": f"Parse error: {e}",
            }

    def _score_single_gemini(
        self,
        image_path: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """使用 Gemini Vision 评分。"""
        from langchain_core.messages import HumanMessage

        image_data = self._encode_image(image_path)
        mime_type = self._get_mime_type(image_path)

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                },
            ]
        )

        response = self._client.invoke([message])
        return self._parse_score_response(response.content)

    def _score_single_openai(
        self,
        image_path: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """使用 GPT-4o 评分。"""
        image_data = self._encode_image(image_path)
        mime_type = self._get_mime_type(image_path)

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=500,
        )

        return self._parse_score_response(response.choices[0].message.content)

    def _generate_mock_scores(self, candidate_id: str) -> Dict[str, Any]:
        """生成测试用的模拟分数。"""
        import random
        random.seed(hash(candidate_id) % 2**32)

        return {
            "prompt_match_score": random.randint(60, 95),
            "character_consistency_score": random.randint(55, 90),
            "composition_score": random.randint(65, 92),
            "reasoning": f"[MOCK] Auto-generated scores for candidate {candidate_id}",
        }

    def _calculate_weighted_total(self, scores: ScoreDetails) -> float:
        """计算加权总分。"""
        return (
            scores.prompt_match_score * self.SCORE_WEIGHTS["prompt_match"]
            + scores.character_consistency_score * self.SCORE_WEIGHTS["character_consistency"]
            + scores.composition_score * self.SCORE_WEIGHTS["composition"]
        )

    def score_keyframes(
        self,
        candidates: List[Dict[str, str]],
        scene_description: str,
        characters: List[Dict[str, Any]],
    ) -> List[ScoredCandidate]:
        """对多个关键帧候选进行评分。"""
        prompt = self._build_scoring_prompt(scene_description, characters)
        results: List[ScoredCandidate] = []

        for candidate in candidates:
            candidate_id = candidate.get("id", "unknown")
            image_path = candidate.get("image_path", "")

            try:
                if self._is_mock_mode():
                    logger.info(f"[MOCK] Scoring candidate: {candidate_id}")
                    raw_scores = self._generate_mock_scores(candidate_id)
                else:
                    logger.info(f"Scoring candidate: {candidate_id} with {self.provider}")
                    if self.provider == "openai":
                        raw_scores = self._score_single_openai(image_path, prompt)
                    else:
                        raw_scores = self._score_single_gemini(image_path, prompt)

                scores = ScoreDetails(
                    prompt_match_score=float(raw_scores.get("prompt_match_score", 0)),
                    character_consistency_score=float(raw_scores.get("character_consistency_score", 0)),
                    composition_score=float(raw_scores.get("composition_score", 0)),
                    reasoning=raw_scores.get("reasoning", ""),
                )

                scored = ScoredCandidate(
                    candidate_id=candidate_id,
                    image_path=image_path,
                    scores=scores,
                    weighted_total=self._calculate_weighted_total(scores),
                    raw_response=raw_scores,
                )
                results.append(scored)

            except FileNotFoundError as e:
                logger.error(f"Image not found for candidate {candidate_id}: {e}")
                results.append(ScoredCandidate(
                    candidate_id=candidate_id,
                    image_path=image_path,
                    weighted_total=0.0,
                ))
            except Exception as e:
                logger.error(f"Error scoring candidate {candidate_id}: {e}")
                results.append(ScoredCandidate(
                    candidate_id=candidate_id,
                    image_path=image_path,
                    weighted_total=0.0,
                ))

        results.sort(key=lambda x: x.weighted_total, reverse=True)
        return results


vlm_client = VLMClient()