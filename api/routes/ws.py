"""WebSocket routes for real-time updates."""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from api.auth import decode_token
from api.websocket import manager
from config import settings
from core.database import engine
from core.models import Job, Project

logger = logging.getLogger(__name__)
router = APIRouter()


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> bool:
    """Authenticate WebSocket connection. Returns True if allowed."""
    if getattr(settings, 'AUTH_DISABLED', True):
        return True
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return False
    token_data = decode_token(token)
    if token_data is None:
        await websocket.close(code=4001, reason="Invalid token")
        return False
    return True


@router.websocket("/projects/{project_id}")
async def websocket_project(websocket: WebSocket, project_id: str, token: str | None = Query(default=None)):
    """WebSocket endpoint for real-time project updates.

    Clients receive updates when:
    - Project status changes
    - Job status changes for this project
    - Shot render progress updates
    """
    if not await _authenticate_ws(websocket, token):
        return

    # Verify project exists
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            await websocket.close(code=4004, reason="Project not found")
            return

    await manager.connect_project(websocket, project_id)

    try:
        # Send initial project state
        with Session(engine) as session:
            project = session.get(Project, project_id)
            if project:
                await manager.send_personal_message(websocket, {
                    "type": "initial_state",
                    "project": {
                        "id": project.id,
                        "status": project.status.value if hasattr(project.status, 'value') else project.status,
                        "output_video_path": project.output_video_path,
                        "output_video_url": project.output_video_url,
                        "error_message": project.error_message,
                    }
                })

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong for connection keep-alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_project(websocket, project_id)
        logger.debug(f"WebSocket disconnected for project: {project_id}")
    except Exception as e:
        logger.error(f"WebSocket error for project {project_id}: {e}")
        manager.disconnect_project(websocket, project_id)


@router.websocket("/jobs/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str, token: str | None = Query(default=None)):
    """WebSocket endpoint for real-time job updates.

    Clients receive updates when:
    - Job status changes
    - Job progress updates
    - Shot render updates for this job
    """
    if not await _authenticate_ws(websocket, token):
        return

    # Verify job exists
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            await websocket.close(code=4004, reason="Job not found")
            return
        project_id = job.project_id

    await manager.connect_job(websocket, job_id)

    try:
        # Send initial job state
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                await manager.send_personal_message(websocket, {
                    "type": "initial_state",
                    "job": {
                        "id": job.id,
                        "project_id": job.project_id,
                        "job_type": job.job_type.value if hasattr(job.job_type, 'value') else job.job_type,
                        "status": job.status.value if hasattr(job.status, 'value') else job.status,
                        "progress": job.progress,
                        "error_message": job.error_message,
                    }
                })

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect_job(websocket, job_id)
        logger.debug(f"WebSocket disconnected for job: {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
        manager.disconnect_job(websocket, job_id)
