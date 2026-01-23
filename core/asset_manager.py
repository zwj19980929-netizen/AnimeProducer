"""
Asset Manager - "Bible Manager" for character consistency.

Manages character extraction, reference image generation, and versioned asset storage.
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlmodel import Session, select

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
        """Convert character traits to a prompt string."""
        parts = []
        if self.hair_color:
            parts.append(f"{self.hair_color} hair")
        if self.eye_color:
            parts.append(f"{self.eye_color} eyes")
        if self.physical_features:
            parts.append(self.physical_features)
        if self.clothing:
            parts.append(self.clothing)
        if self.age_range:
            parts.append(f"{self.age_range} age")
        return ", ".join(parts) if parts else "detailed character portrait"


@dataclass
class Candidate:
    """A candidate reference image."""
    path: str
    seed: int
    prompt: str
    generation_params: Dict
    score: float = 0.0
    version: int = 1


class CharacterListResponse(BaseModel):
    """Pydantic model for LLM structured output."""
    characters: List[dict]


class AssetManager:
    """
    Bible Manager for character consistency.
    
    Handles:
    - Character extraction from novel text
    - Reference image generation with versioning
    - Asset storage organized by project
    """
    
    def __init__(self, base_assets_dir: Optional[str] = None):
        self.base_assets_dir = Path(base_assets_dir or settings.ASSETS_DIR)
        logger.info(f"AssetManager initialized with base_assets_dir: {self.base_assets_dir}")
    
    def _get_project_dir(self, project_id: str) -> Path:
        """Get the project directory path."""
        return self.base_assets_dir / "projects" / project_id
    
    def _get_character_dir(self, project_id: str, character_id: str) -> Path:
        """Get the character directory path within a project."""
        return self._get_project_dir(project_id) / "characters" / character_id
    
    def _ensure_dir(self, path: Path) -> None:
        """Ensure directory exists."""
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {path}")
    
    def _get_next_version(self, character_dir: Path) -> int:
        """Get the next version number for reference images."""
        if not character_dir.exists():
            return 1
        
        existing_versions = []
        for f in character_dir.glob("v*_ref*.png"):
            match = re.match(r"v(\d+)_", f.name)
            if match:
                existing_versions.append(int(match.group(1)))
        
        return max(existing_versions, default=0) + 1
    
    def extract_characters(self, novel_text: str) -> List[CharacterDraft]:
        """
        Extract characters from novel text using LLM.
        
        Args:
            novel_text: The novel text to analyze
            
        Returns:
            List of CharacterDraft objects
        """
        logger.info("Extracting characters from novel text")
        
        prompt = f"""Analyze the following novel text and extract all main characters with their visual traits.

For each character, provide:
- name: The character's name
- hair_color: Hair color description
- eye_color: Eye color description
- clothing: Typical clothing/outfit description
- personality_keywords: List of personality trait keywords
- physical_features: Other notable physical features
- age_range: Approximate age range (e.g., "young adult", "teenager", "middle-aged")

Novel text:
---
{novel_text}
---

Return a JSON object with a "characters" array containing objects with the above fields.
If a trait is not mentioned in the text, leave it as an empty string or empty list."""

        try:
            result = llm_client.generate_structured_output(prompt, CharacterListResponse)
            
            if result is None:
                logger.warning("LLM returned None, returning empty character list")
                return []
            
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
                logger.debug(f"Extracted character: {draft.name}")
            
            logger.info(f"Extracted {len(characters)} characters from novel text")
            return characters
            
        except Exception as e:
            logger.error(f"Error extracting characters: {e}")
            return []
    
    def create_or_update_character(
        self, 
        project_id: str, 
        draft: CharacterDraft
    ) -> Character:
        """
        Create or update a character in the database.
        
        Args:
            project_id: The project identifier
            draft: Character draft with extracted traits
            
        Returns:
            The created or updated Character object
        """
        logger.info(f"Creating/updating character '{draft.name}' for project '{project_id}'")
        
        character_id = f"{project_id}_{draft.name.lower().replace(' ', '_')}"
        prompt_base = draft.to_prompt_base()
        
        character_dir = self._get_character_dir(project_id, character_id)
        self._ensure_dir(character_dir)
        
        reference_image_path = str(character_dir / "current_ref.png")
        
        with Session(engine) as session:
            existing = session.get(Character, character_id)
            
            if existing:
                existing.prompt_base = prompt_base
                existing.reference_image_path = reference_image_path
                session.add(existing)
                session.commit()
                session.refresh(existing)
                logger.info(f"Updated existing character: {character_id}")
                return existing
            else:
                character = Character(
                    character_id=character_id,
                    name=draft.name,
                    prompt_base=prompt_base,
                    reference_image_path=reference_image_path
                )
                session.add(character)
                session.commit()
                session.refresh(character)
                logger.info(f"Created new character: {character_id}")
                return character
    
    def generate_reference_images(
        self,
        character: Character,
        style_spec: str,
        n: int = 4,
        project_id: Optional[str] = None
    ) -> List[Candidate]:
        """
        Generate candidate reference images for a character.
        
        Args:
            character: The Character object
            style_spec: Style specification (e.g., "anime style", "realistic")
            n: Number of candidates to generate
            project_id: Optional project ID (extracted from character_id if not provided)
            
        Returns:
            List of Candidate objects with generated images
        """
        if project_id is None:
            project_id = character.character_id.split("_")[0]
        
        logger.info(f"Generating {n} reference images for character '{character.name}'")
        
        character_dir = self._get_character_dir(project_id, character.character_id)
        self._ensure_dir(character_dir)
        
        version = self._get_next_version(character_dir)
        
        full_prompt = f"{character.prompt_base}, {style_spec}, character reference sheet, high quality, detailed"
        
        candidates = []
        for i in range(n):
            seed = int(datetime.now().timestamp() * 1000) + i
            
            generation_params = {
                "prompt": full_prompt,
                "seed": seed,
                "style_spec": style_spec,
                "width": 1024,
                "height": 1024,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                image_bytes = gen_client.generate_image(full_prompt)
                
                if image_bytes:
                    image_path = character_dir / f"v{version}_ref_{i+1}_seed{seed}.png"
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    
                    params_path = character_dir / f"v{version}_ref_{i+1}_seed{seed}.json"
                    with open(params_path, "w") as f:
                        json.dump(generation_params, f, indent=2)
                    
                    candidate = Candidate(
                        path=str(image_path),
                        seed=seed,
                        prompt=full_prompt,
                        generation_params=generation_params,
                        version=version
                    )
                    candidates.append(candidate)
                    logger.debug(f"Generated candidate {i+1}/{n}: {image_path}")
                else:
                    logger.warning(f"Failed to generate candidate {i+1}/{n}")
                    
            except Exception as e:
                logger.error(f"Error generating candidate {i+1}: {e}")
        
        logger.info(f"Generated {len(candidates)} candidates for character '{character.name}'")
        return candidates
    
    def select_best_reference(
        self, 
        candidates: List[Candidate],
        character: Optional[Character] = None
    ) -> Optional[str]:
        """
        Select the best reference image from candidates.
        
        Currently uses simple heuristics. Can be extended to use VLM scoring.
        
        Args:
            candidates: List of candidate images
            character: Optional character for VLM-based scoring
            
        Returns:
            Path to the best reference image, or None if no candidates
        """
        if not candidates:
            logger.warning("No candidates provided for selection")
            return None
        
        logger.info(f"Selecting best reference from {len(candidates)} candidates")
        
        best = max(candidates, key=lambda c: (c.score, -c.seed))
        
        if character and Path(best.path).exists():
            character_dir = Path(best.path).parent
            current_ref_path = character_dir / "current_ref.png"
            
            import shutil
            shutil.copy2(best.path, current_ref_path)
            
            with Session(engine) as session:
                db_character = session.get(Character, character.character_id)
                if db_character:
                    db_character.reference_image_path = str(current_ref_path)
                    session.add(db_character)
                    session.commit()
            
            logger.info(f"Selected and saved best reference: {current_ref_path}")
            return str(current_ref_path)
        
        logger.info(f"Selected best reference: {best.path}")
        return best.path
    
    def get_reference_images(self, character_ids: List[str]) -> Dict[str, Optional[str]]:
        """
        Get reference image paths for multiple characters.
        
        Args:
            character_ids: List of character IDs
            
        Returns:
            Dictionary mapping character_id to reference image path (or None)
        """
        logger.info(f"Getting reference images for {len(character_ids)} characters")
        
        result: Dict[str, Optional[str]] = {}
        
        with Session(engine) as session:
            for char_id in character_ids:
                character = session.get(Character, char_id)
                if character and character.reference_image_path:
                    ref_path = character.reference_image_path
                    if Path(ref_path).exists():
                        result[char_id] = ref_path
                        logger.debug(f"Found reference for {char_id}: {ref_path}")
                    else:
                        result[char_id] = None
                        logger.warning(f"Reference path exists in DB but file not found: {ref_path}")
                else:
                    result[char_id] = None
                    logger.debug(f"No reference found for character: {char_id}")
        
        return result
    
    def get_all_versions(self, project_id: str, character_id: str) -> List[Dict]:
        """
        Get all reference image versions for a character.
        
        Args:
            project_id: The project identifier
            character_id: The character identifier
            
        Returns:
            List of version metadata dictionaries
        """
        character_dir = self._get_character_dir(project_id, character_id)
        
        if not character_dir.exists():
            return []
        
        versions = []
        for json_file in sorted(character_dir.glob("v*_ref_*.json")):
            try:
                with open(json_file, "r") as f:
                    params = json.load(f)
                image_path = json_file.with_suffix(".png")
                if image_path.exists():
                    versions.append({
                        "params_path": str(json_file),
                        "image_path": str(image_path),
                        **params
                    })
            except Exception as e:
                logger.error(f"Error reading version file {json_file}: {e}")
        
        return versions


asset_manager = AssetManager()
