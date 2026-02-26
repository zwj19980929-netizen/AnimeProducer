"""Dependency injection for API routes."""

import logging
import re
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from core.database import engine
from core.models import Project

logger = logging.getLogger(__name__)

# Path segment validation pattern: only allow safe characters
_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def sanitize_path_segment(value: str) -> str:
    """Validate that a path segment contains only safe characters.

    Raises ValueError if the value contains path traversal or unsafe characters.
    """
    if not value or not _SAFE_SEGMENT_RE.match(value):
        raise ValueError(f"Invalid path segment: {value!r}")
    return value


def get_project_or_404(session: Session, project_id: str) -> Project:
    """Get a project by ID or raise 404."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )
    return project


def get_db() -> Generator[Session, None, None]:
    """Yield a database session.
    
    Automatically closes session after request.
    """
    with Session(engine) as session:
        logger.debug("Database session opened")
        try:
            yield session
        finally:
            logger.debug("Database session closed")


DBSession = Annotated[Session, Depends(get_db)]


class DirectorService:
    """Service wrapper for Director functionality.
    
    Provides access to the pipeline director for orchestrating
    video generation workflows.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._director: object | None = None

    @property
    def director(self) -> object:
        """Lazy-load the Director instance."""
        if self._director is None:
            from core.director import Director
            self._director = Director(session=self.session)
        return self._director


def get_director_service(session: DBSession) -> DirectorService:
    """Get DirectorService instance with DB session."""
    return DirectorService(session=session)


DirectorDep = Annotated[DirectorService, Depends(get_director_service)]


class AssetService:
    """Service wrapper for AssetManager functionality."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._manager: object | None = None

    @property
    def manager(self) -> object:
        """Lazy-load the AssetManager instance."""
        if self._manager is None:
            from core.asset_manager import AssetManager
            self._manager = AssetManager(session=self.session)
        return self._manager


def get_asset_service(session: DBSession) -> AssetService:
    """Get AssetService instance with DB session."""
    return AssetService(session=session)


AssetDep = Annotated[AssetService, Depends(get_asset_service)]
