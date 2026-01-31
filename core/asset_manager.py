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
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session

from config import settings
from core.database import engine
from core.models import Character
from integrations.gen_client import gen_client
from integrations.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class CharacterDraft:
    """Draft character extracted from novel text."""
    name: str
    hair_color: str = ""
    eye_color: str = ""
    clothing: str = ""
    personality_keywords: List[str] = field(default_factory=list)
    physical_features: str = ""
    age_range: str = ""

    def to_prompt_base(self) -> str:
        parts = []
        if self.hair_color: parts.append(f"{self.hair_color} hair")
        if self.eye_color: parts.append(f"{self.eye_color} eyes")
        if self.physical_features: parts.append(self.physical_features)
        if self.clothing: parts.append(self.clothing)
        if self.age_range: parts.append(f"{self.age_range} age")
        return ", ".join(parts) if parts else "detailed character portrait"


@dataclass
class Candidate:
    path: str
    seed: int
    prompt: str
    generation_params: Dict
    score: float = 0.0
    version: int = 1


class CharacterListResponse(BaseModel):
    characters: List[dict]


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
        return self.base_assets_dir / "projects" / project_id

    def _get_character_dir(self, project_id: str, character_id: str) -> Path:
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

    def extract_characters(self, novel_text: str) -> List[CharacterDraft]:
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

            characters = []
            for char_data in result.characters:
                draft = CharacterDraft(
                    name=char_data.get("name", "Unknown"),
                    hair_color=char_data.get("hair_color", ""),
                    eye_color=char_data.get("eye_color", ""),
                    clothing=char_data.get("clothing", ""),
                    personality_keywords=char_data.get("personality_keywords", []),
                    physical_features=char_data.get("physical_features", ""),
                    age_range=char_data.get("age_range", "")
                )
                characters.append(draft)
            return characters
        except Exception as e:
            logger.error(f"Error extracting characters: {e}")
            return []

    def create_or_update_character(
        self,
        project_id: str,
        draft: CharacterDraft,
        session: Optional[Session] = None
    ) -> Character:
        logger.info(f"Creating/updating character '{draft.name}' for project '{project_id}'")

        character_id = f"{project_id}_{draft.name.lower().replace(' ', '_')}"
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
                existing.reference_image_path = reference_image_path
                if not existing.project_id:
                    existing.project_id = project_id

                db.add(existing)
                db.commit()
                db.refresh(existing)
                return existing
            else:
                character = Character(
                    character_id=character_id,
                    project_id=project_id,
                    name=draft.name,
                    prompt_base=prompt_base,
                    reference_image_path=reference_image_path
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
        project_id: Optional[str] = None
    ) -> List[Candidate]:
        if project_id is None:
            # 如果 character 对象里有 project_id 最好，没有则尝试从 ID 解析
            project_id = character.project_id or character.character_id.split("_")[0]

        logger.info(f"Generating {n} reference images for character '{character.name}'")
        character_dir = self._get_character_dir(project_id, character.character_id)
        self._ensure_dir(character_dir)
        version = self._get_next_version(character_dir)
        full_prompt = f"{character.prompt_base}, {style_spec}, character reference sheet, best quality"

        candidates = []
        for i in range(n):
            seed = int(datetime.now().timestamp() * 1000) + i
            generation_params = {
                "prompt": full_prompt, "seed": seed, "style_spec": style_spec,
                "width": 1024, "height": 1024, "timestamp": datetime.now().isoformat()
            }
            try:
                # 调用绘图接口
                image_bytes = gen_client.generate_image(full_prompt)
                if image_bytes:
                    image_path = character_dir / f"v{version}_ref_{i+1}_seed{seed}.png"
                    with open(image_path, "wb") as f: f.write(image_bytes)

                    params_path = character_dir / f"v{version}_ref_{i+1}_seed{seed}.json"
                    with open(params_path, "w") as f: json.dump(generation_params, f, indent=2)

                    candidates.append(Candidate(
                        path=str(image_path), seed=seed, prompt=full_prompt,
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

        if character and Path(best.path).exists():
            character_dir = Path(best.path).parent
            current_ref_path = character_dir / "current_ref.png"
            shutil.copy2(best.path, current_ref_path)

            db = session or self.session
            should_close = False
            if not db:
                db = Session(engine)
                should_close = True

            try:
                db_character = db.get(Character, character.character_id)
                if db_character:
                    db_character.reference_image_path = str(current_ref_path)
                    db.add(db_character)
                    db.commit()
            except Exception:
                if should_close:
                    db.rollback()
                raise
            finally:
                if should_close: db.close()

            return str(current_ref_path)
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