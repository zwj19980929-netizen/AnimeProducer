"""
Asset Manager - "Bible Manager" for character consistency.
"""

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from core.database import engine
from core.models import Character, CharacterState
from integrations.provider_factory import ProviderFactory
from integrations.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class CharacterDraft:
    """Draft character extracted from novel text."""
    name: str
    aliases: List[str] = field(default_factory=list)  # 别名列表
    hair_color: str = ""
    eye_color: str = ""
    clothing: str = ""
    personality_keywords: List[str] = field(default_factory=list)
    physical_features: str = ""
    age_range: str = ""
    first_appearance_chapter: int = 0
    evolution_type: str = ""  # "new", "evolution", or empty
    suspected_same_as: str = ""  # 可疑关联：可能与某个已有角色是同一人

    def to_prompt_base(self) -> str:
        parts = []
        if self.hair_color:
            hair = self.hair_color if isinstance(self.hair_color, str) else ", ".join(self.hair_color)
            parts.append(f"{hair} hair")
        if self.eye_color:
            eyes = self.eye_color if isinstance(self.eye_color, str) else ", ".join(self.eye_color)
            parts.append(f"{eyes} eyes")
        if self.physical_features:
            features = self.physical_features if isinstance(self.physical_features, str) else ", ".join(self.physical_features)
            parts.append(features)
        if self.clothing:
            clothes = self.clothing if isinstance(self.clothing, str) else ", ".join(self.clothing)
            parts.append(clothes)
        if self.age_range:
            age = self.age_range if isinstance(self.age_range, str) else ", ".join(self.age_range)
            parts.append(f"{age} age")
        return ", ".join(parts) if parts else "detailed character portrait"


@dataclass
class Candidate:
    path: str  # Primary path (could be local or OSS URL)
    seed: int
    prompt: str
    generation_params: Dict
    score: float = 0.0
    version: int = 1

    @property
    def is_oss_url(self) -> bool:
        """Check if path is an OSS URL."""
        return self.path.startswith("http://") or self.path.startswith("https://")

    @property
    def local_path(self) -> Optional[str]:
        """Get local path if available."""
        return None if self.is_oss_url else self.path

    @property
    def oss_url(self) -> Optional[str]:
        """Get OSS URL if available."""
        return self.path if self.is_oss_url else None


class CharacterListResponse(BaseModel):
    characters: List[dict]


class CharacterEvolutionResponse(BaseModel):
    """Response model for incremental character extraction."""
    new_characters: List[dict]  # New characters discovered
    character_evolutions: List[dict]  # {character_name, evolution_type, new_traits}


class BatchCharacterExtractionResponse(BaseModel):
    """Response model for batch character extraction with alias detection."""
    new_characters: List[dict]  # 新发现的角色
    character_evolutions: List[dict]  # 角色形象变化
    alias_detections: List[dict]  # 检测到的别名 {character_name, new_alias, confidence}
    suspected_identities: List[dict]  # 可疑身份关联 {new_character, existing_character, reason, confidence}


class AssetManager:
    """Bible Manager for character consistency."""

    def __init__(self, session: Optional[Session] = None, base_assets_dir: Optional[str] = None):
        """
        :param session: Optional injected DB session
        :param base_assets_dir: Base directory for assets
        """
        self.session = session
        self.base_assets_dir = Path(base_assets_dir or settings.ASSETS_DIR)
        logger.info(f"AssetManager initialized with base_assets_dir: {self.base_assets_dir}")

    def _get_project_dir(self, project_id: str) -> Path:
        from api.deps import sanitize_path_segment
        sanitize_path_segment(project_id)
        return self.base_assets_dir / "projects" / project_id

    def _get_character_dir(self, project_id: str, character_id: str) -> Path:
        from api.deps import sanitize_path_segment
        sanitize_path_segment(character_id)
        return self._get_project_dir(project_id) / "characters" / character_id

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def _get_next_version(self, character_dir: Path) -> int:
        if not character_dir.exists(): return 1
        existing_versions = []
        for f in character_dir.glob("v*_ref*.png"):
            match = re.match(r"v(\d+)_", f.name)
            if match: existing_versions.append(int(match.group(1)))
        return max(existing_versions, default=0) + 1

    def extract_characters(self, novel_text: str, chapter_number: int = 0) -> List[CharacterDraft]:
        """
        Extract characters from novel text.
        
        :param novel_text: The novel text to analyze
        :param chapter_number: Chapter number for first_appearance_chapter field
        :return: List of CharacterDraft objects
        """
        logger.info("Extracting characters from novel text")
        prompt = f"""You are an expert character designer and novel analyst.
Your task is to analyze the provided novel text and extract detailed profiles for all MAIN characters.
Focus specifically on visual traits that can be used to generate character reference images.

Instructions:
1. Identify all MAIN characters.
2. For each character, infer their visual appearance.
3. Be consistent.
4. Extract personality keywords.

Fields: name, hair_color, eye_color, clothing, personality_keywords, physical_features, age_range.

Novel text:
---
{novel_text[:10000]} 
---
Return ONLY the valid JSON object matching the requested schema."""

        try:
            result = llm_client.generate_structured_output(prompt, CharacterListResponse, temperature=0.1)
            if result is None: return []

            def ensure_str(val) -> str:
                """确保值是字符串，如果是列表则拼接。"""
                if val is None:
                    return ""
                if isinstance(val, list):
                    return ", ".join(str(v) for v in val)
                return str(val)

            def ensure_list(val) -> list:
                """确保值是列表。"""
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                return [val]

            characters = []
            for char_data in result.characters:
                draft = CharacterDraft(
                    name=ensure_str(char_data.get("name")) or "Unknown",
                    hair_color=ensure_str(char_data.get("hair_color")),
                    eye_color=ensure_str(char_data.get("eye_color")),
                    clothing=ensure_str(char_data.get("clothing")),
                    personality_keywords=ensure_list(char_data.get("personality_keywords")),
                    physical_features=ensure_str(char_data.get("physical_features")),
                    age_range=ensure_str(char_data.get("age_range")),
                    first_appearance_chapter=chapter_number,
                    evolution_type="new"
                )
                characters.append(draft)
            return characters
        except Exception as e:
            logger.error(f"Error extracting characters: {e}")
            return []

    def extract_characters_from_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
        existing_characters: List[str]
    ) -> List[CharacterDraft]:
        """
        从单个章节提取新角色，排除已知角色。
        同时检测已有角色的形象变化。
        
        :param chapter_content: Chapter text content
        :param chapter_number: Chapter number (1-indexed)
        :param existing_characters: List of known character names to exclude
        :return: List of CharacterDraft (new characters and evolutions)
        """
        logger.info(f"Extracting characters from chapter {chapter_number}, "
                    f"existing characters: {existing_characters}")

        existing_chars_str = ", ".join(existing_characters) if existing_characters else "None"

        prompt = f"""You are an expert character designer and novel analyst.
Your task is to analyze the provided chapter text and:
1. Extract profiles for NEW characters that do NOT appear in the existing characters list.
2. Detect any significant visual/appearance changes (evolution) for existing characters.

EXISTING CHARACTERS (do NOT extract these as new):
{existing_chars_str}

Instructions for NEW characters:
- Only extract characters NOT in the existing list above
- Focus on visual traits for character reference images
- Fields: name, hair_color, eye_color, clothing, personality_keywords, physical_features, age_range

Instructions for CHARACTER EVOLUTIONS:
- Look for significant visual changes in existing characters such as:
  * 换装 (costume change)
  * 变身 (transformation)
  * 黑化 (becoming dark/evil)
  * 升级 (power-up with new appearance)
  * 受伤 (injuries affecting appearance)
  * 成长 (aging/maturing)
- For evolutions, include: character_name, evolution_type, and new visual traits

Chapter text:
---
{chapter_content[:15000]}
---

Return a JSON object with two arrays:
1. "new_characters": array of new character profiles (name, hair_color, eye_color, clothing, personality_keywords, physical_features, age_range)
2. "character_evolutions": array of evolution events (character_name, evolution_type, new_traits dict with hair_color, eye_color, clothing, physical_features)

Return ONLY the valid JSON object."""

        try:
            result = llm_client.generate_structured_output(
                prompt, CharacterEvolutionResponse, temperature=0.1
            )
            if result is None:
                return []

            def ensure_str(val) -> str:
                """确保值是字符串，如果是列表则拼接。"""
                if val is None:
                    return ""
                if isinstance(val, list):
                    return ", ".join(str(v) for v in val)
                return str(val)

            def ensure_list(val) -> list:
                """确保值是列表。"""
                if val is None:
                    return []
                if isinstance(val, list):
                    return val
                return [val]

            characters = []

            # Process new characters
            for char_data in result.new_characters:
                draft = CharacterDraft(
                    name=ensure_str(char_data.get("name")) or "Unknown",
                    hair_color=ensure_str(char_data.get("hair_color")),
                    eye_color=ensure_str(char_data.get("eye_color")),
                    clothing=ensure_str(char_data.get("clothing")),
                    personality_keywords=ensure_list(char_data.get("personality_keywords")),
                    physical_features=ensure_str(char_data.get("physical_features")),
                    age_range=ensure_str(char_data.get("age_range")),
                    first_appearance_chapter=chapter_number,
                    evolution_type="new"
                )
                characters.append(draft)

            # Process character evolutions as special drafts
            for evo_data in result.character_evolutions:
                new_traits = evo_data.get("new_traits", {})
                draft = CharacterDraft(
                    name=ensure_str(evo_data.get("character_name")) or "Unknown",
                    hair_color=ensure_str(new_traits.get("hair_color")),
                    eye_color=ensure_str(new_traits.get("eye_color")),
                    clothing=ensure_str(new_traits.get("clothing")),
                    personality_keywords=[],
                    physical_features=ensure_str(new_traits.get("physical_features")),
                    age_range="",
                    first_appearance_chapter=chapter_number,
                    evolution_type=ensure_str(evo_data.get("evolution_type")) or "evolution"
                )
                characters.append(draft)

            logger.info(f"Found {len(result.new_characters)} new characters and "
                        f"{len(result.character_evolutions)} evolutions in chapter {chapter_number}")
            return characters

        except Exception as e:
            logger.error(f"Error extracting characters from chapter {chapter_number}: {e}")
            return []

    def batch_extract_characters_from_chapters(
        self,
        chapters_content: List[Dict[str, Any]],
        existing_characters: List[Dict[str, Any]],
        project_context: str = ""
    ) -> Dict[str, Any]:
        """
        批量从多个章节提取角色，支持别名识别和可疑身份关联检测。

        :param chapters_content: 章节列表 [{chapter_number, title, content}, ...]
        :param existing_characters: 已有角色完整信息 [{name, aliases, appearance_prompt, bio, first_appearance_chapter}, ...]
        :param project_context: 项目背景信息（如小说类型、世界观等）
        :return: 包含新角色、别名、可疑关联的结果
        """
        if not chapters_content:
            return {"new_characters": [], "character_evolutions": [], "alias_detections": [], "suspected_identities": []}

        chapter_range = f"{chapters_content[0]['chapter_number']}-{chapters_content[-1]['chapter_number']}"
        logger.info(f"Batch extracting characters from chapters {chapter_range}, "
                    f"existing characters: {len(existing_characters)}")

        # 构建已有角色的详细描述
        existing_chars_desc = []
        for char in existing_characters:
            aliases_str = f"（别名：{', '.join(char.get('aliases', []))}）" if char.get('aliases') else ""
            desc = f"- {char['name']}{aliases_str}: {char.get('appearance_prompt', '无外貌描述')}"
            if char.get('bio'):
                desc += f" | 简介: {char['bio'][:100]}"
            if char.get('first_appearance_chapter'):
                desc += f" | 首次出场: 第{char['first_appearance_chapter']}章"
            existing_chars_desc.append(desc)

        existing_chars_str = "\n".join(existing_chars_desc) if existing_chars_desc else "（暂无已知角色）"

        # 合并章节内容
        chapters_text = ""
        for ch in chapters_content:
            chapters_text += f"\n\n=== 第{ch['chapter_number']}章"
            if ch.get('title'):
                chapters_text += f": {ch['title']}"
            chapters_text += f" ===\n{ch['content']}"

        # 限制总长度
        max_content_length = 25000
        if len(chapters_text) > max_content_length:
            chapters_text = chapters_text[:max_content_length] + "\n...(内容过长已截断)"

        prompt = f"""你是一位专业的小说角色分析师，擅长识别角色身份和别名关系。

## 任务
分析以下章节内容，完成：
1. 提取新出现的重要角色（排除已知角色）
2. 检测已知角色的新别名/称呼
3. 识别可疑的身份关联（某个新角色可能是已知角色的伪装/化身/隐藏身份）
4. 检测角色的外貌变化（换装、变身等）

## 已知角色列表（包含别名和外貌特征）
{existing_chars_str}

## 项目背景
{project_context or "无特殊背景"}

## 章节内容
{chapters_text}

## 分析要点

### 别名识别
小说中同一角色可能有多种称呼：
- 全名/简称（如"李明"和"小明"）
- 职位/身份称呼（如"李总"、"那个医生"）
- 亲昵称呼（如"阿明"、"明哥"）
- 外号/绰号

### 可疑身份关联
注意以下情况可能暗示两个角色是同一人：
- 外貌特征高度相似但名字不同
- 从不同时出现在同一场景
- 有暗示性的描写（如"似曾相识的眼神"）
- 隐藏身份/伪装的剧情暗示
- 神秘人物的特征与已知角色吻合

### 新角色判定
只提取真正的新角色：
- 有名字或明确称呼
- 有一定戏份（不是路人甲）
- 不是已知角色的别名

## 输出格式
返回 JSON 对象：
{{
    "new_characters": [
        {{
            "name": "角色名",
            "aliases": ["可能的别名1", "别名2"],
            "hair_color": "发色",
            "eye_color": "眼睛颜色",
            "clothing": "服装描述",
            "physical_features": "其他外貌特征",
            "age_range": "年龄段",
            "personality_keywords": ["性格关键词"],
            "first_appearance_chapter": 章节号
        }}
    ],
    "character_evolutions": [
        {{
            "character_name": "已知角色名",
            "evolution_type": "变化类型（换装/变身/黑化/受伤等）",
            "trigger_chapter": 章节号,
            "new_traits": {{
                "hair_color": "新发色",
                "clothing": "新服装",
                "physical_features": "新特征"
            }}
        }}
    ],
    "alias_detections": [
        {{
            "character_name": "已知角色名",
            "new_alias": "新发现的别名",
            "context": "出现的上下文",
            "confidence": "high/medium/low"
        }}
    ],
    "suspected_identities": [
        {{
            "new_character": "新角色名或称呼",
            "existing_character": "可能对应的已知角色名",
            "reason": "判断依据",
            "confidence": "high/medium/low",
            "evidence": ["证据1", "证据2"]
        }}
    ]
}}

只返回 JSON，不要其他内容。"""

        try:
            result = llm_client.generate_structured_output(
                prompt, BatchCharacterExtractionResponse, temperature=0.1
            )
            if result is None:
                return {"new_characters": [], "character_evolutions": [], "alias_detections": [], "suspected_identities": []}

            logger.info(f"Batch extraction result: {len(result.new_characters)} new characters, "
                        f"{len(result.alias_detections)} aliases, {len(result.suspected_identities)} suspected identities")

            return {
                "new_characters": result.new_characters,
                "character_evolutions": result.character_evolutions,
                "alias_detections": result.alias_detections,
                "suspected_identities": result.suspected_identities
            }

        except Exception as e:
            logger.error(f"Error in batch character extraction: {e}")
            return {"new_characters": [], "character_evolutions": [], "alias_detections": [], "suspected_identities": []}

    def process_chapter_for_characters(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        处理单个章节的角色发现：
        1. 获取项目已有角色列表
        2. 调用 extract_characters_from_chapter
        3. 创建新角色或更新 CharacterState
        
        :param project_id: Project ID
        :param chapter_number: Chapter number (1-indexed)
        :param chapter_content: Chapter text content
        :param session: Optional database session
        :return: Dict with new_characters and evolutions info
        """
        logger.info(f"Processing chapter {chapter_number} for project {project_id}")

        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            # 1. Get existing characters for this project
            statement = select(Character).where(Character.project_id == project_id)
            existing_chars = db.exec(statement).all()
            existing_char_names = [c.name for c in existing_chars]
            existing_char_map = {c.name: c for c in existing_chars}

            # 2. Extract new characters and evolutions
            drafts = self.extract_characters_from_chapter(
                chapter_content, chapter_number, existing_char_names
            )

            new_characters_created = []
            evolutions_processed = []

            for draft in drafts:
                if draft.evolution_type == "new":
                    # Create new character
                    character = self.create_or_update_character(
                        project_id, draft, session=db
                    )
                    new_characters_created.append({
                        "character_id": character.character_id,
                        "name": character.name,
                        "first_appearance_chapter": chapter_number
                    })
                elif draft.evolution_type and draft.name in existing_char_map:
                    # Handle character evolution - create new CharacterState
                    existing_char = existing_char_map[draft.name]
                    state = CharacterState(
                        character_id=existing_char.character_id,
                        state_name=draft.evolution_type,
                        trigger_chapter=chapter_number,
                        visual_changes={
                            "hair_color": draft.hair_color,
                            "eye_color": draft.eye_color,
                            "clothing": draft.clothing,
                            "physical_features": draft.physical_features
                        },
                        prompt_override=draft.to_prompt_base()
                    )
                    db.add(state)
                    evolutions_processed.append({
                        "character_name": draft.name,
                        "evolution_type": draft.evolution_type,
                        "trigger_chapter": chapter_number,
                        "new_traits": state.visual_changes
                    })

            db.commit()

            result = {
                "project_id": project_id,
                "chapter_number": chapter_number,
                "new_characters": new_characters_created,
                "evolutions": evolutions_processed,
                "total_new": len(new_characters_created),
                "total_evolutions": len(evolutions_processed)
            }

            logger.info(f"Chapter {chapter_number} processed: "
                        f"{len(new_characters_created)} new characters, "
                        f"{len(evolutions_processed)} evolutions")
            return result

        except Exception as e:
            logger.error(f"Error processing chapter {chapter_number}: {e}")
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def process_chapters_batch_for_characters(
        self,
        project_id: str,
        chapter_numbers: List[int],
        session: Optional[Session] = None,
        auto_create: bool = True
    ) -> Dict[str, Any]:
        """
        批量处理多个章节的角色发现（支持别名和可疑身份检测）。

        :param project_id: Project ID
        :param chapter_numbers: 要扫描的章节号列表（最多10章）
        :param session: Optional database session
        :param auto_create: 是否自动创建新角色（False则只返回分析结果）
        :return: 包含新角色、别名、可疑关联的完整结果
        """
        from core.models import Chapter

        if len(chapter_numbers) > 10:
            raise ValueError("一次最多扫描10个章节")

        logger.info(f"Batch processing chapters {chapter_numbers} for project {project_id}")

        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            # 1. 获取章节内容
            chapters_content = []
            for ch_num in sorted(chapter_numbers):
                statement = select(Chapter).where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number == ch_num
                )
                chapter = db.exec(statement).first()
                if chapter:
                    chapters_content.append({
                        "chapter_number": chapter.chapter_number,
                        "title": chapter.title,
                        "content": chapter.content
                    })

            if not chapters_content:
                return {
                    "project_id": project_id,
                    "chapters_scanned": [],
                    "new_characters": [],
                    "character_evolutions": [],
                    "alias_detections": [],
                    "suspected_identities": [],
                    "characters_created": []
                }

            # 2. 获取已有角色的完整信息
            statement = select(Character).where(Character.project_id == project_id)
            existing_chars = db.exec(statement).all()
            existing_characters = []
            for c in existing_chars:
                existing_characters.append({
                    "name": c.name,
                    "aliases": c.aliases or [],
                    "appearance_prompt": c.appearance_prompt,
                    "bio": c.bio,
                    "first_appearance_chapter": c.first_appearance_chapter
                })

            # 3. 调用批量提取
            extraction_result = self.batch_extract_characters_from_chapters(
                chapters_content=chapters_content,
                existing_characters=existing_characters
            )

            characters_created = []

            # 4. 处理别名检测 - 更新已有角色的别名
            for alias_info in extraction_result.get("alias_detections", []):
                char_name = alias_info.get("character_name")
                new_alias = alias_info.get("new_alias")
                if char_name and new_alias:
                    for c in existing_chars:
                        if c.name == char_name:
                            if not c.aliases:
                                c.aliases = []
                            if new_alias not in c.aliases:
                                c.aliases.append(new_alias)
                                db.add(c)
                                logger.info(f"Added alias '{new_alias}' to character '{char_name}'")
                            break

            # 5. 如果 auto_create，创建新角色
            if auto_create:
                for char_data in extraction_result.get("new_characters", []):
                    draft = CharacterDraft(
                        name=char_data.get("name", "Unknown"),
                        aliases=char_data.get("aliases", []),
                        hair_color=char_data.get("hair_color", ""),
                        eye_color=char_data.get("eye_color", ""),
                        clothing=char_data.get("clothing", ""),
                        personality_keywords=char_data.get("personality_keywords", []),
                        physical_features=char_data.get("physical_features", ""),
                        age_range=char_data.get("age_range", ""),
                        first_appearance_chapter=char_data.get("first_appearance_chapter", chapter_numbers[0]),
                        evolution_type="new"
                    )
                    character = self.create_or_update_character(project_id, draft, session=db)
                    # 更新别名
                    if draft.aliases:
                        character.aliases = draft.aliases
                        db.add(character)
                    characters_created.append({
                        "character_id": character.character_id,
                        "name": character.name,
                        "aliases": draft.aliases
                    })

            # 6. 处理角色进化
            existing_char_map = {c.name: c for c in existing_chars}
            for evo_data in extraction_result.get("character_evolutions", []):
                char_name = evo_data.get("character_name")
                if char_name and char_name in existing_char_map:
                    existing_char = existing_char_map[char_name]
                    new_traits = evo_data.get("new_traits", {})
                    state = CharacterState(
                        character_id=existing_char.character_id,
                        state_name=evo_data.get("evolution_type", "evolution"),
                        trigger_chapter=evo_data.get("trigger_chapter", chapter_numbers[0]),
                        visual_changes=new_traits,
                        prompt_override=", ".join(f"{k}: {v}" for k, v in new_traits.items() if v)
                    )
                    db.add(state)

            db.commit()

            result = {
                "project_id": project_id,
                "chapters_scanned": [ch["chapter_number"] for ch in chapters_content],
                "new_characters": extraction_result.get("new_characters", []),
                "character_evolutions": extraction_result.get("character_evolutions", []),
                "alias_detections": extraction_result.get("alias_detections", []),
                "suspected_identities": extraction_result.get("suspected_identities", []),
                "characters_created": characters_created
            }

            logger.info(f"Batch processing complete: {len(characters_created)} characters created, "
                        f"{len(extraction_result.get('alias_detections', []))} aliases detected, "
                        f"{len(extraction_result.get('suspected_identities', []))} suspected identities")

            return result

        except Exception as e:
            logger.error(f"Error in batch processing chapters: {e}")
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def merge_characters(
        self,
        project_id: str,
        primary_character_id: str,
        secondary_character_id: str,
        session: Optional[Session] = None
    ) -> Character:
        """
        合并两个角色（当确认是同一人时）。

        将 secondary 角色的信息合并到 primary 角色，然后删除 secondary。
        - secondary 的名字变成 primary 的别名
        - secondary 的 CharacterState 转移到 primary
        - secondary 的图片转移到 primary

        :param project_id: Project ID
        :param primary_character_id: 保留的主角色 ID
        :param secondary_character_id: 要合并进来的角色 ID
        :return: 合并后的角色
        """
        from core.models import CharacterImage

        logger.info(f"Merging character '{secondary_character_id}' into '{primary_character_id}'")

        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            primary = db.get(Character, primary_character_id)
            secondary = db.get(Character, secondary_character_id)

            if not primary:
                raise ValueError(f"Primary character not found: {primary_character_id}")
            if not secondary:
                raise ValueError(f"Secondary character not found: {secondary_character_id}")

            # 1. 将 secondary 的名字添加为 primary 的别名
            if not primary.aliases:
                primary.aliases = []
            if secondary.name not in primary.aliases:
                primary.aliases.append(secondary.name)
            # 也把 secondary 的别名合并过来
            for alias in (secondary.aliases or []):
                if alias not in primary.aliases and alias != primary.name:
                    primary.aliases.append(alias)

            # 2. 合并 bio（如果 primary 没有的话）
            if not primary.bio and secondary.bio:
                primary.bio = secondary.bio
            elif primary.bio and secondary.bio:
                primary.bio = f"{primary.bio}\n\n[合并自 {secondary.name}]: {secondary.bio}"

            # 3. 转移 CharacterState
            statement = select(CharacterState).where(CharacterState.character_id == secondary_character_id)
            states = db.exec(statement).all()
            for state in states:
                state.character_id = primary_character_id
                db.add(state)

            # 4. 转移 CharacterImage
            statement = select(CharacterImage).where(CharacterImage.character_id == secondary_character_id)
            images = db.exec(statement).all()
            for img in images:
                img.character_id = primary_character_id
                db.add(img)

            # 5. 更新 primary
            primary.updated_at = datetime.utcnow()
            db.add(primary)

            # 6. 删除 secondary
            db.delete(secondary)

            db.commit()
            db.refresh(primary)

            logger.info(f"Merged '{secondary.name}' into '{primary.name}', "
                        f"aliases now: {primary.aliases}")

            return primary

        except Exception as e:
            logger.error(f"Error merging characters: {e}")
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def add_character_alias(
        self,
        character_id: str,
        alias: str,
        session: Optional[Session] = None
    ) -> Character:
        """
        为角色添加别名。

        :param character_id: 角色 ID
        :param alias: 要添加的别名
        :return: 更新后的角色
        """
        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            character = db.get(Character, character_id)
            if not character:
                raise ValueError(f"Character not found: {character_id}")

            if not character.aliases:
                character.aliases = []

            if alias not in character.aliases and alias != character.name:
                character.aliases.append(alias)
                character.updated_at = datetime.utcnow()
                db.add(character)
                db.commit()
                db.refresh(character)
                logger.info(f"Added alias '{alias}' to character '{character.name}'")

            return character

        except Exception as e:
            logger.error(f"Error adding alias: {e}")
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def create_or_update_character(
        self,
        project_id: str,
        draft: CharacterDraft,
        session: Optional[Session] = None
    ) -> Character:
        logger.info(f"Creating/updating character '{draft.name}' for project '{project_id}'")

        character_id = f"{project_id}_{draft.name.lower().replace(' ', '_').replace('/', '_')}"
        prompt_base = draft.to_prompt_base()

        character_dir = self._get_character_dir(project_id, character_id)
        self._ensure_dir(character_dir)
        reference_image_path = str(character_dir / "current_ref.png")

        db = session or self.session
        should_close = False
        if not db:
            db = Session(engine)
            should_close = True

        try:
            existing = db.get(Character, character_id)
            if existing:
                existing.prompt_base = prompt_base
                existing.appearance_prompt = prompt_base
                existing.reference_image_path = reference_image_path
                if not existing.project_id:
                    existing.project_id = project_id
                # 合并别名
                if draft.aliases:
                    if not existing.aliases:
                        existing.aliases = []
                    for alias in draft.aliases:
                        if alias not in existing.aliases:
                            existing.aliases.append(alias)
                existing.updated_at = datetime.utcnow()

                db.add(existing)
                db.commit()
                db.refresh(existing)
                return existing
            else:
                character = Character(
                    character_id=character_id,
                    project_id=project_id,
                    name=draft.name,
                    aliases=draft.aliases or [],
                    appearance_prompt=prompt_base,
                    prompt_base=prompt_base,
                    reference_image_path=reference_image_path,
                    first_appearance_chapter=draft.first_appearance_chapter
                )
                db.add(character)
                db.commit()
                db.refresh(character)
                return character
        except Exception:
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def generate_reference_images(
        self,
        character: Character,
        style_spec: str,
        n: int = 4,
        project_id: Optional[str] = None,
        style_preset: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        prompt_override: Optional[str] = None,
        reference_image: Optional[str] = None,
    ) -> List[Candidate]:
        """
        Generate reference images for a character.

        :param character: Character object to generate images for
        :param style_spec: Style specification string
        :param n: Number of candidate images to generate
        :param project_id: Optional project ID override
        :param style_preset: Optional global style preset to enforce consistent art style
        :param negative_prompt: Optional negative prompt describing what to avoid
        :param seed: Optional random seed for reproducibility (will increment for each candidate)
        :param prompt_override: Optional prompt to use instead of character's prompt_base
        :param reference_image: Optional reference image path/URL for image-to-image generation
        """
        if project_id is None:
            # 如果 character 对象里有 project_id 最好，没有则尝试从 ID 解析
            project_id = character.project_id or character.character_id.split("_")[0]

        logger.info(f"Generating {n} reference images for character '{character.name}'")

        # 检查是否配置了 OSS
        from integrations.oss_service import is_oss_configured, OSSService
        use_oss = is_oss_configured()

        # 本地目录仍然需要用于临时存储或作为备份
        character_dir = self._get_character_dir(project_id, character.character_id)
        self._ensure_dir(character_dir)
        version = self._get_next_version(character_dir)

        # 使用 prompt_override 或默认的 prompt_base
        base_prompt = prompt_override or character.appearance_prompt or character.prompt_base
        full_prompt = f"{base_prompt}, {style_spec}, character reference sheet, best quality"

        candidates = []
        for i in range(n):
            # 如果指定了 seed，每个候选使用递增的 seed
            current_seed = (seed + i) if seed is not None else int(datetime.now().timestamp() * 1000) + i

            generation_params = {
                "prompt": full_prompt,
                "seed": current_seed,
                "style_spec": style_spec,
                "style_preset": style_preset,
                "negative_prompt": negative_prompt,
                "width": 1024,
                "height": 1024,
                "timestamp": datetime.now().isoformat()
            }
            try:
                # 调用绘图接口，传入所有参数（使用 ProviderFactory 获取配置的图像客户端）
                image_client = ProviderFactory.get_image_client()
                image_bytes = image_client.generate_image(
                    full_prompt,
                    reference_image_path=reference_image,
                    style_preset=style_preset,
                    negative_prompt=negative_prompt,
                    seed=current_seed
                )
                if image_bytes:
                    if use_oss:
                        # 直接上传到 OSS
                        oss = OSSService.get_instance()
                        filename = f"char_{character.character_id}_v{version}_ref_{i+1}_seed{current_seed}"
                        image_url = oss.upload_image_bytes(image_bytes, filename=filename)
                        candidates.append(Candidate(
                            path=image_url, seed=current_seed, prompt=full_prompt,
                            generation_params=generation_params, version=version
                        ))
                        logger.info(f"角色参考图已上传到 OSS: {image_url}")
                    else:
                        # 保存到本地
                        image_path = character_dir / f"v{version}_ref_{i+1}_seed{current_seed}.png"
                        with open(image_path, "wb") as f: f.write(image_bytes)

                        params_path = character_dir / f"v{version}_ref_{i+1}_seed{current_seed}.json"
                        with open(params_path, "w") as f: json.dump(generation_params, f, indent=2)

                        candidates.append(Candidate(
                            path=str(image_path), seed=current_seed, prompt=full_prompt,
                            generation_params=generation_params, version=version
                        ))
            except Exception as e:
                logger.error(f"Error generating candidate {i+1}: {e}")
        return candidates

    def select_best_reference(
        self,
        candidates: List[Candidate],
        character: Optional[Character] = None,
        session: Optional[Session] = None
    ) -> Optional[str]:
        if not candidates: return None
        best = max(candidates, key=lambda c: (c.score, -c.seed))

        # 检查 best.path 是否是 OSS URL
        is_oss_url = best.path.startswith("http://") or best.path.startswith("https://")

        if character:
            oss_url = None
            local_path = None

            if is_oss_url:
                # 已经是 OSS URL，直接使用
                oss_url = best.path
                logger.info(f"使用 OSS URL 作为角色参考图: {oss_url}")
            elif Path(best.path).exists():
                # 本地文件，复制并上传到 OSS
                character_dir = Path(best.path).parent
                current_ref_path = character_dir / "current_ref.png"
                shutil.copy2(best.path, current_ref_path)
                local_path = str(current_ref_path)

                # 上传到 OSS
                try:
                    from integrations.oss_service import is_oss_configured, upload_file_to_oss
                    if is_oss_configured():
                        oss_url = upload_file_to_oss(local_path, cleanup=False)
                        logger.info(f"角色参考图已上传到 OSS: {oss_url}")
                except Exception as e:
                    logger.warning(f"上传角色参考图到 OSS 失败: {e}")

            db = session or self.session
            should_close = False
            if not db:
                db = Session(engine)
                should_close = True

            try:
                db_character = db.get(Character, character.character_id)
                if db_character:
                    if local_path:
                        db_character.reference_image_path = local_path
                    if oss_url:
                        db_character.reference_image_url = oss_url
                        # 如果有 OSS URL，也可以用它作为 path（前端优先使用 URL）
                        if not local_path:
                            db_character.reference_image_path = oss_url
                    db.add(db_character)
                    db.commit()
            except Exception:
                if should_close:
                    db.rollback()
                raise
            finally:
                if should_close: db.close()

            return oss_url or local_path or best.path
        return best.path

    def get_reference_images(self, character_ids: List[str]) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {}
        with Session(engine) as session:
            for char_id in character_ids:
                character = session.get(Character, char_id)
                if character and character.reference_image_path and Path(character.reference_image_path).exists():
                    result[char_id] = character.reference_image_path
                else:
                    result[char_id] = None
        return result

    def get_all_versions(self, project_id: str, character_id: str) -> List[Dict]:
        character_dir = self._get_character_dir(project_id, character_id)
        if not character_dir.exists(): return []
        versions = []
        for json_file in sorted(character_dir.glob("v*_ref_*.json")):
            try:
                with open(json_file, "r") as f: params = json.load(f)
                image_path = json_file.with_suffix(".png")
                if image_path.exists():
                    versions.append({"params_path": str(json_file), "image_path": str(image_path), **params})
            except Exception: pass
        return versions

asset_manager = AssetManager()