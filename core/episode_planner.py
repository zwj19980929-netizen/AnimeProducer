"""集规划服务 - 智能规划动漫集数。"""

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from core.chapter_analyzer import ChapterAnalysis

logger = logging.getLogger(__name__)


class EpisodeSuggestion(BaseModel):
    """AI 建议的集规划。"""
    episode_number: int
    title: str
    start_chapter: int
    end_chapter: int
    synopsis: str
    estimated_duration_minutes: float
    key_events: List[str] = Field(default_factory=list)


class EpisodePlan(BaseModel):
    """完整的集规划结果。"""
    episodes: List[EpisodeSuggestion]
    total_episodes: int
    total_estimated_duration: float
    reasoning: str


class EpisodePlannerConfig(BaseModel):
    """集规划配置。"""
    target_duration_minutes: float = Field(default=24.0, description="每集目标时长（分钟）")
    min_duration_minutes: float = Field(default=18.0, description="每集最短时长")
    max_duration_minutes: float = Field(default=30.0, description="每集最长时长")
    words_per_minute: float = Field(default=150.0, description="每分钟对应的小说字数")
    style: str = Field(default="standard", description="风格: standard/movie/short")


class EpisodePlanner:
    """集规划器 - 智能规划动漫集数。"""

    def __init__(self):
        from integrations.llm_client import llm_client
        self.llm = llm_client

    def plan_episodes(
        self,
        chapters: List[dict],
        chapter_analyses: Optional[List[ChapterAnalysis]] = None,
        config: Optional[EpisodePlannerConfig] = None
    ) -> EpisodePlan:
        """
        智能规划集数。

        Args:
            chapters: 章节列表，每个元素包含 chapter_number, title, content, word_count
            chapter_analyses: 章节分析结果（可选，如果没有会自动分析）
            config: 规划配置

        Returns:
            EpisodePlan: 集规划结果
        """
        if config is None:
            config = EpisodePlannerConfig()

        # 如果没有分析结果，先进行分析
        if chapter_analyses is None:
            from core.chapter_analyzer import chapter_analyzer
            chapter_analyses = chapter_analyzer.analyze_chapters_batch(chapters)

        # 计算总字数
        total_words = sum(ch.get("word_count", len(ch.get("content", ""))) for ch in chapters)

        # 估算总时长
        estimated_total_minutes = total_words / config.words_per_minute

        # 估算集数
        estimated_episodes = max(1, round(estimated_total_minutes / config.target_duration_minutes))

        logger.info(
            f"Planning episodes: {len(chapters)} chapters, "
            f"{total_words} words, ~{estimated_total_minutes:.1f} min, "
            f"~{estimated_episodes} episodes"
        )

        # 使用 LLM 进行智能规划
        return self._plan_with_llm(
            chapters=chapters,
            analyses=chapter_analyses,
            config=config,
            estimated_episodes=estimated_episodes
        )

    def _plan_with_llm(
        self,
        chapters: List[dict],
        analyses: List[ChapterAnalysis],
        config: EpisodePlannerConfig,
        estimated_episodes: int
    ) -> EpisodePlan:
        """使用 LLM 进行智能集规划。"""

        # 构建章节摘要
        chapter_summaries = []
        for i, (ch, analysis) in enumerate(zip(chapters, analyses)):
            chapter_num = ch.get("chapter_number", i + 1)
            title = ch.get("title", f"第{chapter_num}章")
            word_count = ch.get("word_count", len(ch.get("content", "")))
            events = "; ".join(analysis.key_events[:3]) if analysis.key_events else "无关键事件"
            arc = analysis.emotional_arc
            importance = analysis.importance_score
            is_break = "是" if analysis.is_good_break_point else "否"

            chapter_summaries.append(
                f"第{chapter_num}章 [{title}]: {word_count}字, "
                f"情感={arc}, 重要性={importance:.1f}, "
                f"适合断点={is_break}, 事件: {events}"
            )

        chapters_info = "\n".join(chapter_summaries)

        prompt = f"""你是一位专业的动漫编剧和制作人。请根据以下小说章节信息，规划动漫的集数划分。

## 配置要求
- 每集目标时长: {config.target_duration_minutes} 分钟
- 每集时长范围: {config.min_duration_minutes}-{config.max_duration_minutes} 分钟
- 预估总集数: 约 {estimated_episodes} 集
- 风格: {config.style}

## 章节信息
{chapters_info}

## 规划原则
1. **剧情完整性**: 每集应该有完整的起承转合，不要在高潮或紧张情节中间断开
2. **情感曲线**: 每集应该有情感起伏，最好以小高潮或悬念结尾
3. **时长均衡**: 各集时长应该相对均衡，避免某集过长或过短
4. **角色出场**: 重要角色首次出场最好在集的开头部分
5. **断点选择**: 优先选择标记为"适合断点"的章节作为一集的结尾

## 输出要求
为每一集提供:
1. 集数编号
2. 集标题（吸引人的标题）
3. 包含的章节范围（起始章节号-结束章节号）
4. 本集简介（2-3句话）
5. 预估时长
6. 本集关键事件（3-5个）
"""

        try:
            result = self.llm.generate_structured_output(prompt, EpisodePlan)
            if result and result.episodes:
                logger.info(f"LLM planned {len(result.episodes)} episodes")
                return result
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")

        # 如果 LLM 失败，使用规则引擎回退
        return self._plan_with_rules(chapters, analyses, config)

    def _plan_with_rules(
        self,
        chapters: List[dict],
        analyses: List[ChapterAnalysis],
        config: EpisodePlannerConfig
    ) -> EpisodePlan:
        """使用规则引擎进行集规划（LLM 失败时的回退方案）。"""
        logger.info("Using rule-based episode planning as fallback")

        episodes = []
        current_episode_start = 1
        current_words = 0
        target_words = config.target_duration_minutes * config.words_per_minute

        for i, (ch, analysis) in enumerate(zip(chapters, analyses)):
            chapter_num = ch.get("chapter_number", i + 1)
            word_count = ch.get("word_count", len(ch.get("content", "")))
            current_words += word_count

            # 判断是否应该在这里断开
            should_break = False

            # 条件1: 字数达到目标
            if current_words >= target_words:
                should_break = True

            # 条件2: 是好的断点且字数超过最小值
            min_words = config.min_duration_minutes * config.words_per_minute
            if analysis.is_good_break_point and current_words >= min_words:
                should_break = True

            # 条件3: 是高潮章节，适合作为一集的结尾
            if analysis.emotional_arc == "climax" and current_words >= min_words:
                should_break = True

            # 条件4: 字数超过最大值，强制断开
            max_words = config.max_duration_minutes * config.words_per_minute
            if current_words >= max_words:
                should_break = True

            if should_break or chapter_num == len(chapters):
                # 创建一集
                episode_num = len(episodes) + 1
                episodes.append(EpisodeSuggestion(
                    episode_number=episode_num,
                    title=f"第{episode_num}集",
                    start_chapter=current_episode_start,
                    end_chapter=chapter_num,
                    synopsis=f"第{current_episode_start}章到第{chapter_num}章的内容",
                    estimated_duration_minutes=current_words / config.words_per_minute,
                    key_events=analysis.key_events[:3] if analysis.key_events else []
                ))

                # 重置
                current_episode_start = chapter_num + 1
                current_words = 0

        total_duration = sum(ep.estimated_duration_minutes for ep in episodes)

        return EpisodePlan(
            episodes=episodes,
            total_episodes=len(episodes),
            total_estimated_duration=total_duration,
            reasoning="基于字数和断点规则自动划分"
        )

    def adjust_plan(
        self,
        plan: EpisodePlan,
        adjustments: List[dict]
    ) -> EpisodePlan:
        """
        根据用户调整修改集规划。

        Args:
            plan: 原始规划
            adjustments: 调整列表，每个元素包含 episode_number 和要修改的字段

        Returns:
            EpisodePlan: 调整后的规划
        """
        episodes = list(plan.episodes)

        for adj in adjustments:
            ep_num = adj.get("episode_number")
            if ep_num is None:
                continue

            for ep in episodes:
                if ep.episode_number == ep_num:
                    if "title" in adj:
                        ep.title = adj["title"]
                    if "start_chapter" in adj:
                        ep.start_chapter = adj["start_chapter"]
                    if "end_chapter" in adj:
                        ep.end_chapter = adj["end_chapter"]
                    if "synopsis" in adj:
                        ep.synopsis = adj["synopsis"]
                    break

        return EpisodePlan(
            episodes=episodes,
            total_episodes=len(episodes),
            total_estimated_duration=sum(ep.estimated_duration_minutes for ep in episodes),
            reasoning=plan.reasoning + " (用户已调整)"
        )


# 单例
episode_planner = EpisodePlanner()
