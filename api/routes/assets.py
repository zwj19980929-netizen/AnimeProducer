"""Character assets API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import func, select

from api.deps import AssetDep, DBSession
from api.schemas import (
    CharacterCreate,
    CharacterListResponse,
    CharacterResponse,
    CharacterUpdate,
    ErrorResponse,
)
from core.models import Character, Project

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/characters",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_character(
    character_in: CharacterCreate,
    session: DBSession,
    project_id: str | None = Query(default=None),
) -> Character:
    """Create a new character."""
    logger.info(f"Creating character: {character_in.name}")
    
    if project_id:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}",
            )
    
    existing = session.get(Character, character_in.character_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Character already exists: {character_in.character_id}",
        )
    
    character = Character(
        character_id=character_in.character_id,
        project_id=project_id,
        name=character_in.name,
        prompt_base=character_in.prompt_base,
        reference_image_path=character_in.reference_image_path,
        voice_id=character_in.voice_id,
        metadata=character_in.metadata,
    )
    
    session.add(character)
    session.commit()
    session.refresh(character)
    
    logger.info(f"Created character: {character.character_id}")
    return character


@router.get(
    "/characters",
    response_model=CharacterListResponse,
)
def list_characters(
    session: DBSession,
    project_id: str | None = Query(default=None),
) -> CharacterListResponse:
    """List all characters, optionally filtered by project."""
    logger.debug(f"Listing characters: project_id={project_id}")
    
    query = select(Character)
    count_query = select(func.count()).select_from(Character)
    
    if project_id:
        query = query.where(Character.project_id == project_id)
        count_query = count_query.where(Character.project_id == project_id)
    
    query = query.order_by(Character.created_at.desc())
    
    characters = session.exec(query).all()
    total = session.exec(count_query).one()
    
    return CharacterListResponse(
        items=[CharacterResponse.model_validate(c) for c in characters],
        total=total,
    )


@router.get(
    "/characters/{character_id}",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_character(
    character_id: str,
    session: DBSession,
) -> Character:
    """Get a character by ID."""
    logger.debug(f"Getting character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    return character


@router.patch(
    "/characters/{character_id}",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_character(
    character_id: str,
    character_in: CharacterUpdate,
    session: DBSession,
) -> Character:
    """Update a character."""
    logger.info(f"Updating character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    update_data = character_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    session.add(character)
    session.commit()
    session.refresh(character)
    
    logger.info(f"Updated character: {character_id}")
    return character


@router.delete(
    "/characters/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_character(
    character_id: str,
    session: DBSession,
) -> None:
    """Delete a character."""
    logger.info(f"Deleting character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    session.delete(character)
    session.commit()
    
    logger.info(f"Deleted character: {character_id}")


@router.post(
    "/characters/{character_id}/generate-reference",
    response_model=CharacterResponse,
    responses={404: {"model": ErrorResponse}},
)
def generate_character_reference(
    character_id: str,
    session: DBSession,
    asset_service: AssetDep,
) -> Character:
    """Generate reference image for a character using AI.
    
    This endpoint triggers the asset generation pipeline for the character.
    """
    logger.info(f"Generating reference for character: {character_id}")
    
    character = session.get(Character, character_id)
    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character not found: {character_id}",
        )
    
    # TODO: Implement actual generation via AssetManager
    # asset_service.manager.generate_character_reference(character)
    
    session.refresh(character)
    return character
