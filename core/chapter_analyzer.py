"""章节分析服务 - 使用 LLM 分析章节内容。"""

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChapterAnalysis(BaseModel):
    """章节分析结果。"""
    key_events: List[str] = Field(
        default_factory=list,
        description="章节中的关键事件列表，每个事件用一句话描述"
    )
    emotional_arc: str = Field(
        default="neutral",
        description="章节的情感曲线类型: rising(上升), falling(下降), climax(高潮), resolution(解决), neutral(平稳)"
    )
    importance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="章节重要性评分 0-1，1 表示非常重要（如主角觉醒、重大转折）"
    )
    characters_appeared: List[str] = Field(
        default_factory=list,
        description="本章出现的角色名称列表"
    )
    is_good_break_point: bool = Field(
        default=False,
        description="本章结尾是否适合作为一集的结束点"
    )
    break_point_reason: Optional[str] = Field(
        default=None,
        description="如果是好的断点，说明原因"
    )


class ChapterAnalyzer:
    """章节分析器 - 使用 LLM 分析章节内容。"""

    def __init__(self):
        from integrations.llm_client import llm_client
        self.llm = llm_client

    def analyze_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
        chapter_title: Optional[str] = None,
        previous_summary: Optional[str] = None
    ) -> ChapterAnalysis:
        """
        分析单个章节，提取关键信息。

        Args:
            chapter_content: 章节内容
            chapter_number: 章节号
            chapter_title: 章节标题（可选）
            previous_summary: 前文摘要（可选，用于上下文理解）

        Returns:
            ChapterAnalysis: 分析结果
        """
        title_info = f"标题: {chapter_title}\n" if chapter_title else ""
        context_info = f"前文摘要: {previous_summary}\n\n" if previous_summary else ""

        prompt = f"""你是一位专业的小说分析师和动漫编剧。请分析以下小说章节，提取关键信息用于动漫制作规划。

{context_info}第 {chapter_number} 章
{title_info}
内容:
{chapter_content[:8000]}  # 限制长度避免超出 token 限制

请分析并提取以下信息:

1. **关键事件** (key_events): 列出本章发生的 3-5 个关键事件，每个事件用一句话描述。
   - 关注推动剧情发展的事件
   - 关注角色关系变化
   - 关注重要的战斗/冲突/对话

2. **情感曲线** (emotional_arc): 判断本章的情感走向
   - rising: 紧张感上升，冲突加剧
   - falling: 紧张感下降，冲突缓和
   - climax: 高潮，重大事件发生
   - resolution: 解决，问题得到处理
   - neutral: 平稳过渡，铺垫章节

3. **重要性评分** (importance_score): 0-1 之间的分数
   - 0.8-1.0: 非常重要（主角觉醒、重大转折、boss 战）
   - 0.5-0.8: 较重要（重要对话、关系发展、小高潮）
   - 0.3-0.5: 一般（日常、过渡、铺垫）
   - 0.0-0.3: 可压缩（纯描写、回忆、水章）

4. **出场角色** (characters_appeared): 列出本章出现的所有角色名称

5. **断点判断** (is_good_break_point): 本章结尾是否适合作为一集动漫的结束
   - 好的断点: 悬念、小高潮结束、场景转换
   - 不好的断点: 战斗中途、对话中途、紧张情节未完
"""

        try:
            logger.info(f"Analyzing chapter {chapter_number}...")
            result = self.llm.generate_structured_output(prompt, ChapterAnalysis)
            if result:
                logger.info(
                    f"Chapter {chapter_number} analyzed: "
                    f"importance={result.importance_score:.2f}, "
                    f"arc={result.emotional_arc}, "
                    f"events={len(result.key_events)}"
                )
                return result
            else:
                logger.warning(f"LLM returned empty result for chapter {chapter_number}")
                return ChapterAnalysis()
        except Exception as e:
            logger.error(f"Failed to analyze chapter {chapter_number}: {e}")
            return ChapterAnalysis()

    def analyze_chapters_batch(
        self,
        chapters: List[dict],
        include_context: bool = True
    ) -> List[ChapterAnalysis]:
        """
        批量分析多个章节。

        Args:
            chapters: 章节列表，每个元素包含 chapter_number, title, content
            include_context: 是否包含前文摘要作为上下文

        Returns:
            List[ChapterAnalysis]: 分析结果列表
        """
        results = []
        previous_summary = None

        for chapter in chapters:
            chapter_number = chapter.get("chapter_number", 0)
            title = chapter.get("title")
            content = chapter.get("content", "")

            analysis = self.analyze_chapter(
                chapter_content=content,
                chapter_number=chapter_number,
                chapter_title=title,
                previous_summary=previous_summary if include_context else None
            )
            results.append(analysis)

            # 更新前文摘要（用关键事件作为摘要）
            if include_context and analysis.key_events:
                previous_summary = "; ".join(analysis.key_events[:3])

        return results

    def suggest_episode_for_chapter(
        self,
        chapter_number: int,
        analysis: ChapterAnalysis,
        chapters_per_episode: float = 5.0
    ) -> int:
        """
        根据分析结果建议章节归属的集数。

        Args:
            chapter_number: 章节号
            analysis: 章节分析结果
            chapters_per_episode: 平均每集包含的章节数

        Returns:
            int: 建议的集数
        """
        # 基础计算：按章节号平均分配
        base_episode = int((chapter_number - 1) / chapters_per_episode) + 1

        # 如果是好的断点，可能是一集的结尾
        # 如果是高潮章节，可能需要单独成集或作为一集的结尾
        # 这里返回基础计算，更复杂的逻辑在 EpisodePlanner 中处理

        return base_episode


# 单例
chapter_analyzer = ChapterAnalyzer()
