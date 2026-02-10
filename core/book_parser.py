"""书籍解析服务 - 解析整本书文件为章节。"""

import logging
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ParsedChapter(BaseModel):
    """解析出的章节。"""
    chapter_number: int
    title: str
    content: str
    word_count: int


class BookParseResult(BaseModel):
    """书籍解析结果。"""
    chapters: List[ParsedChapter]
    total_chapters: int
    total_words: int
    detected_title: Optional[str] = None
    detected_author: Optional[str] = None


class BookParser:
    """书籍解析器 - 支持多种格式和章节识别模式。"""

    # 常见的章节标题模式
    CHAPTER_PATTERNS = [
        # 中文数字章节: 第一章、第二章...
        r'^第[一二三四五六七八九十百千万零〇]+章[\s:：]*(.*?)$',
        # 阿拉伯数字章节: 第1章、第2章...
        r'^第(\d+)章[\s:：]*(.*?)$',
        # 简单数字: 1、2、3... 或 1. 2. 3...
        r'^(\d+)[\.、\s]+(.*?)$',
        # Chapter 1, Chapter 2...
        r'^[Cc]hapter\s*(\d+)[\s:：]*(.*?)$',
        # 卷/篇 + 章节
        r'^[第卷篇][一二三四五六七八九十百千万零〇\d]+[卷篇章节回]\s*(.*?)$',
    ]

    # 中文数字映射
    CN_NUM_MAP = {
        '零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '百': 100, '千': 1000, '万': 10000
    }

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.MULTILINE) for p in self.CHAPTER_PATTERNS]

    def parse_txt(self, content: str, encoding: str = 'utf-8') -> BookParseResult:
        """
        解析 TXT 格式的小说。

        Args:
            content: 文件内容
            encoding: 编码（已解码的内容忽略此参数）

        Returns:
            BookParseResult: 解析结果
        """
        # 清理内容
        content = self._clean_content(content)

        # 尝试提取书名和作者
        detected_title, detected_author = self._extract_metadata(content)

        # 检测章节模式
        pattern, matches = self._detect_chapter_pattern(content)

        if not matches:
            # 没有检测到章节，整个内容作为一章
            logger.warning("No chapter pattern detected, treating entire content as one chapter")
            chapters = [ParsedChapter(
                chapter_number=1,
                title="全文",
                content=content.strip(),
                word_count=len(content.strip())
            )]
        else:
            # 按检测到的模式分割章节
            chapters = self._split_chapters(content, pattern, matches)

        total_words = sum(ch.word_count for ch in chapters)

        logger.info(f"Parsed {len(chapters)} chapters, {total_words} words")
        return BookParseResult(
            chapters=chapters,
            total_chapters=len(chapters),
            total_words=total_words,
            detected_title=detected_title,
            detected_author=detected_author
        )

    def _clean_content(self, content: str) -> str:
        """清理内容：统一换行符、去除多余空白。"""
        # 统一换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        # 去除连续多个空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def _extract_metadata(self, content: str) -> Tuple[Optional[str], Optional[str]]:
        """尝试从内容开头提取书名和作者。"""
        lines = content.split('\n')[:20]  # 只看前20行

        title = None
        author = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测书名（通常是第一个非空行，且不是章节标题）
            if title is None and not self._is_chapter_title(line):
                if len(line) < 50:  # 书名通常不会太长
                    title = line

            # 检测作者
            author_match = re.match(r'^[作著]者[：:]\s*(.+)$', line)
            if author_match:
                author = author_match.group(1).strip()

            if title and author:
                break

        return title, author

    def _is_chapter_title(self, line: str) -> bool:
        """判断一行是否是章节标题。"""
        for pattern in self.compiled_patterns:
            if pattern.match(line):
                return True
        return False

    def _detect_chapter_pattern(self, content: str) -> Tuple[Optional[re.Pattern], List[re.Match]]:
        """检测内容中使用的章节模式。"""
        best_pattern = None
        best_matches = []

        for pattern in self.compiled_patterns:
            matches = list(pattern.finditer(content))
            if len(matches) > len(best_matches):
                best_pattern = pattern
                best_matches = matches

        return best_pattern, best_matches

    def _split_chapters(
        self,
        content: str,
        pattern: re.Pattern,
        matches: List[re.Match]
    ) -> List[ParsedChapter]:
        """根据匹配结果分割章节。"""
        chapters = []

        for i, match in enumerate(matches):
            # 章节标题
            full_match = match.group(0)
            title = self._extract_title_from_match(match)

            # 章节内容：从当前匹配到下一个匹配（或文件结尾）
            start = match.end()
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)

            chapter_content = content[start:end].strip()

            # 如果内容太短，可能是误匹配，跳过
            if len(chapter_content) < 50:
                continue

            chapters.append(ParsedChapter(
                chapter_number=i + 1,
                title=title or f"第{i + 1}章",
                content=chapter_content,
                word_count=len(chapter_content)
            ))

        return chapters

    def _extract_title_from_match(self, match: re.Match) -> str:
        """从匹配结果中提取章节标题。"""
        groups = match.groups()
        if groups:
            # 取最后一个非空组作为标题
            for g in reversed(groups):
                if g and g.strip():
                    return g.strip()
        # 如果没有捕获组，使用整个匹配
        return match.group(0).strip()

    def _cn_to_num(self, cn_str: str) -> int:
        """将中文数字转换为阿拉伯数字。"""
        if not cn_str:
            return 0

        result = 0
        temp = 0
        for char in cn_str:
            if char in self.CN_NUM_MAP:
                num = self.CN_NUM_MAP[char]
                if num >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * num
                    temp = 0
                else:
                    temp = temp * 10 + num if temp else num
        result += temp
        return result if result else 1

    def parse_with_ai(self, content: str) -> BookParseResult:
        """
        使用 AI 智能分章（当规则匹配失败时的备选方案）。

        Args:
            content: 文件内容

        Returns:
            BookParseResult: 解析结果
        """
        from integrations.llm_client import llm_client

        # 如果内容太长，先截取前面部分让 AI 分析章节模式
        sample = content[:10000] if len(content) > 10000 else content

        prompt = f"""分析以下小说文本的章节结构，识别章节分割模式。

文本样本:
{sample}

请返回:
1. 章节标题的正则表达式模式
2. 检测到的书名（如果有）
3. 检测到的作者（如果有）
"""

        # 这里简化处理，实际可以让 AI 返回结构化数据
        # 目前先用规则解析，AI 解析作为 TODO
        logger.info("AI-based parsing not fully implemented, falling back to rule-based")
        return self.parse_txt(content)


# 单例
book_parser = BookParser()
