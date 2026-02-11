"""视觉叙事重构系统 - 将小说文本转换为视觉节拍脚本。

将慢节奏的网文改编为可在短时间内表演的视觉脚本，
遵循 [Hook → Conflict → Climax → Cliffhanger] 结构。
"""

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VisualBeat(BaseModel):
    """视觉节拍 - 单个可视化动作单元"""
    action: str = Field(description="屏幕上的视觉动作")
    dialogue: Optional[str] = Field(default=None, description="精简对白（可选）")
    estimated_duration: float = Field(default=3.0, description="预估时长（秒）")
    beat_type: str = Field(
        default="action",
        description="节拍类型: hook, conflict, climax, cliffhanger, transition, action"
    )


class MicroScript(BaseModel):
    """微脚本 - 视觉节拍列表"""
    visual_beats: List[VisualBeat] = Field(default_factory=list)
    total_duration: float = Field(default=0.0, description="总时长（秒）")
    structure_notes: str = Field(default="", description="结构说明")


class ScreenwriterConfig(BaseModel):
    """编剧配置"""
    target_duration_seconds: float = Field(default=150.0, description="目标时长（秒）")
    max_beats: int = Field(default=30, description="最大节拍数")
    min_beats: int = Field(default=5, description="最小节拍数")


class Screenwriter:
    """
    视觉编剧 - 将小说文本重构为视觉节拍脚本

    核心职责：
    1. 删减：移除心理描写、环境描写、无效对话
    2. 转化：将"他感到害怕"转化为"他手中的茶杯掉落摔碎"（Show, Don't Tell）
    3. 重构：按 [Hook → Conflict → Climax → Cliffhanger] 结构重组
    """

    def __init__(self):
        from integrations.llm_client import llm_client
        self.llm = llm_client

    def refactor_story(
        self,
        original_text: str,
        config: Optional[ScreenwriterConfig] = None
    ) -> MicroScript:
        """
        将原始小说文本重构为视觉节拍脚本。

        Args:
            original_text: 原始小说文本
            config: 编剧配置

        Returns:
            MicroScript: 包含视觉节拍列表的微脚本
        """
        if config is None:
            config = ScreenwriterConfig()

        prompt = f"""You are a top Hollywood short drama screenwriter. Your task is to adapt this slow-paced web novel into a visual script that can be performed within {config.target_duration_seconds} seconds.

Strictly execute the following operations:

1. **[Reduction]**: Remove all psychological descriptions and environmental descriptions. Remove all trivial small talk and unnecessary dialogue.

2. **[Transformation]**: Transform "he felt scared" into "the teacup in his hand drops to the ground and shatters." (Show, Don't Tell)
   - Every emotion must be expressed through VISIBLE ACTION
   - No internal monologue - only external behavior
   - Replace "she was angry" with specific physical actions

3. **[Restructuring]**: Must reorganize the plot according to the [Hook → Conflict → Climax → Cliffhanger] structure. If this chapter has no climax, indicate that it should be merged with the next chapter.
   - Hook: An attention-grabbing opening (first 10-15 seconds)
   - Conflict: Rising tension and obstacles
   - Climax: The peak moment of action/emotion
   - Cliffhanger: Leave the audience wanting more

**Output Requirements:**
- Generate {config.min_beats}-{config.max_beats} Visual Beats
- Each beat should be 2-8 seconds
- Total duration should be approximately {config.target_duration_seconds} seconds
- Mark each beat's type (hook/conflict/climax/cliffhanger/transition/action)

**Original Text:**
{original_text}
"""

        try:
            logger.info("Refactoring story to visual beats...")
            result = self.llm.generate_structured_output(prompt, MicroScript)

            if result and result.visual_beats:
                # 计算总时长
                result.total_duration = sum(
                    beat.estimated_duration for beat in result.visual_beats
                )
                logger.info(
                    f"Generated {len(result.visual_beats)} visual beats, "
                    f"total duration: {result.total_duration:.1f}s"
                )
                return result
            else:
                logger.warning("LLM returned empty micro script")
                return MicroScript()

        except Exception as e:
            logger.error(f"Failed to refactor story: {e}")
            return MicroScript()

    def merge_chapters_for_climax(
        self,
        chapters: List[str],
        config: Optional[ScreenwriterConfig] = None
    ) -> MicroScript:
        """
        合并多个章节直到形成完整的高潮结构。

        当单个章节没有高潮时，合并相邻章节直到形成完整的叙事弧。

        Args:
            chapters: 章节文本列表
            config: 编剧配置

        Returns:
            MicroScript: 合并后的微脚本
        """
        if config is None:
            config = ScreenwriterConfig()

        combined_text = "\n\n---\n\n".join(chapters)
        return self.refactor_story(combined_text, config)

    def count_effective_beats(self, script: MicroScript) -> int:
        """
        统计有效视觉节拍数量。

        有效节拍 = 包含实际视觉动作的节拍（排除纯过渡）

        Args:
            script: 微脚本

        Returns:
            有效节拍数量
        """
        effective_types = {"hook", "conflict", "climax", "cliffhanger", "action"}
        return sum(
            1 for beat in script.visual_beats
            if beat.beat_type in effective_types
        )


# 单例
screenwriter = Screenwriter()
