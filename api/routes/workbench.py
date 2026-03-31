"""Aggregated routes for the redesigned stage-based workbench."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from api.auth import get_current_active_user
from api.deps import DBSession, get_project_or_404
from api.schemas import ShotResponse
from api.workbench_schemas import DashboardResponse, ProjectCardListResponse, ShotUpdateRequest, WorkspaceResponse
from core.models import Shot
from core.workbench import build_dashboard, build_workspace, list_project_cards

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_active_user)])


@router.get("/projects", response_model=ProjectCardListResponse)
def list_workbench_projects(session: DBSession) -> ProjectCardListResponse:
    """List project cards with stage and progress summaries."""

    return list_project_cards(session)


@router.get("/projects/{project_id}/dashboard", response_model=DashboardResponse)
def get_project_dashboard(project_id: str, session: DBSession) -> DashboardResponse:
    """Get the dashboard payload for a single project."""

    get_project_or_404(session, project_id)
    return build_dashboard(session, project_id)


@router.get("/projects/{project_id}/workspace", response_model=WorkspaceResponse)
def get_project_workspace(project_id: str, session: DBSession) -> WorkspaceResponse:
    """Get the full workbench payload for a single project."""

    get_project_or_404(session, project_id)
    return build_workspace(session, project_id)


@router.patch(
    "/projects/{project_id}/shots/{shot_id}",
    response_model=ShotResponse,
    responses={404: {"description": "Shot not found"}},
)
def update_shot_from_workbench(
    project_id: str,
    shot_id: int,
    shot_in: ShotUpdateRequest,
    session: DBSession,
) -> Shot:
    """Update editable storyboard fields from the workbench editor."""

    get_project_or_404(session, project_id)
    shot = session.exec(
        select(Shot).where(Shot.project_id == project_id, Shot.shot_id == shot_id)
    ).first()
    if shot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot not found: {shot_id}",
        )

    update_data = shot_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(shot, field, value)

    if hasattr(shot, "updated_at"):
        shot.updated_at = datetime.utcnow()  # pragma: no cover - compatibility if field exists later

    session.add(shot)
    session.commit()
    session.refresh(shot)
    logger.info("Updated shot %s for project %s", shot_id, project_id)
    return shot
