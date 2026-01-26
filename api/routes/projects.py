"""Project management API routes."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status, Body
from sqlmodel import func, select

from api.deps import DBSession, DirectorDep
from api.schemas import (
    ErrorResponse,
    PipelineStartRequest,
    PipelineStartResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectStatusUpdate,
    ProjectUpdate,
    ShotListResponse,
    ShotResponse,
)
from core.errors import ProjectNotFoundError
from core.models import Project, ProjectStatus, Shot, Job

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}},
)
def create_project(
    project_in: ProjectCreate,
    session: DBSession,
) -> Project:
    """Create a new project."""
    logger.info(f"Creating project: {project_in.name}")

    project = Project(
        name=project_in.name,
        description=project_in.description,
        script_content=project_in.script_content,
        style_preset=project_in.style_preset,
        project_metadata=project_in.project_metadata,
    )

    session.add(project)
    session.commit()
    session.refresh(project)

    logger.info(f"Created project: {project.id}")
    return project


@router.get(
    "",
    response_model=ProjectListResponse,
)
def list_projects(
    session: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
) -> ProjectListResponse:
    """List all projects with pagination."""
    logger.debug(f"Listing projects: page={page}, page_size={page_size}")

    query = select(Project)
    count_query = select(func.count()).select_from(Project)

    if status_filter:
        query = query.where(Project.status == status_filter)
        count_query = count_query.where(Project.status == status_filter)

    query = query.order_by(Project.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    projects = session.exec(query).all()
    total = session.exec(count_query).one()

    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_project(
    project_id: str,
    session: DBSession,
) -> Project:
    """Get a project by ID."""
    logger.debug(f"Getting project: {project_id}")

    project = session.get(Project, project_id)
    if not project:
        logger.warning(f"Project not found: {project_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    session: DBSession,
) -> Project:
    """Update a project (includes ingest novel via script_content)."""
    logger.info(f"Updating project: {project_id}")

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )

    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.utcnow()

    session.add(project)
    session.commit()
    session.refresh(project)

    logger.info(f"Updated project: {project_id}")
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
def delete_project(
    project_id: str,
    session: DBSession,
) -> None:
    """Delete a project."""
    logger.info(f"Deleting project: {project_id}")

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )

    session.delete(project)
    session.commit()

    logger.info(f"Deleted project: {project_id}")


@router.put(
    "/{project_id}/status",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_project_status(
    project_id: str,
    status_update: ProjectStatusUpdate,
    session: DBSession,
) -> Project:
    """Update project status."""
    logger.info(f"Updating project status: {project_id} -> {status_update.status}")

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )

    project.status = status_update.status
    if status_update.error_message:
        project.error_message = status_update.error_message
    project.updated_at = datetime.utcnow()

    session.add(project)
    session.commit()
    session.refresh(project)

    return project


@router.get(
    "/{project_id}/shots",
    response_model=ShotListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_project_shots(
    project_id: str,
    session: DBSession,
) -> ShotListResponse:
    """List all shots for a project."""
    logger.debug(f"Listing shots for project: {project_id}")

    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {project_id}",
        )

    query = (
        select(Shot)
        .where(Shot.project_id == project_id)
        .order_by(Shot.sequence_order)
    )
    shots = session.exec(query).all()

    return ShotListResponse(
        items=[ShotResponse.model_validate(s) for s in shots],
        total=len(shots),
    )


# ============================================================================
# Action Routes (Triggers) - Added for Pipeline Execution
# ============================================================================

@router.post(
    "/{project_id}/assets/build",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def build_project_assets(
    project_id: str,
    session: DBSession,
    director: DirectorDep,
) -> Project:
    """
    Trigger: Extract characters and generate reference images from script content.
    """
    logger.info(f"Triggering asset build for project: {project_id}")
    try:
        updated_project = director.director.build_assets(project_id)
        return updated_project
    except Exception as e:
        logger.error(f"Asset build failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{project_id}/storyboard/generate",
    response_model=ShotListResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def generate_project_storyboard(
    project_id: str,
    session: DBSession,
    director: DirectorDep,
) -> ShotListResponse:
    """
    Trigger: Generate storyboard (shots) from script content using LLM.
    """
    logger.info(f"Triggering storyboard generation for project: {project_id}")
    try:
        shots = director.director.generate_storyboard(project_id)
        return ShotListResponse(
            items=[ShotResponse.model_validate(s) for s in shots],
            total=len(shots),
        )
    except Exception as e:
        logger.error(f"Storyboard generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/{project_id}/pipeline/start",
    response_model=PipelineStartResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def start_pipeline(
    project_id: str,  # Path parameter
    request: PipelineStartRequest,
    session: DBSession,
    director: DirectorDep,
) -> PipelineStartResponse:
    """
    Trigger: Start the full production pipeline (Rendering).
    """
    logger.info(f"Starting pipeline for project: {project_id}")
    actual_project_id = project_id

    try:
        job = director.director.start_render_job(actual_project_id)

        return PipelineStartResponse(
            job_id=job.id,
            project_id=project_id,
            message="Pipeline started successfully via Celery",
        )
    except Exception as e:
        logger.error(f"Pipeline start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )