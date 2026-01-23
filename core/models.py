from typing import List, Optional
from sqlmodel import Field, SQLModel, JSON

class Character(SQLModel, table=True):
    character_id: str = Field(primary_key=True)
    name: str
    prompt_base: str
    reference_image_path: str
    voice_id: Optional[str] = None

class Shot(SQLModel, table=True):
    shot_id: int = Field(primary_key=True)
    duration: float
    scene_description: str
    visual_prompt: str
    camera_movement: str
    # Store list of strings as JSON
    characters_in_shot: List[str] = Field(default=[], sa_type=JSON)
    dialogue: Optional[str] = None
    action_type: Optional[str] = None
