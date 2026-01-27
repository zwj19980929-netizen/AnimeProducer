"""Job status and management API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import func, select

from api.deps import DBSession
from api.schemas import (
    ErrorResponse,
    JobCreate,
    JobListResponse,
    JobProgressUpdate,
    JobResponse,
    JobStatusUpdate,
    ShotRenderListResponse,
    ShotRenderResponse,
)
from core.models import Job, JobStatus, JobType, Project, ShotRender

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_job(
    job_in: JobCreate,
    session: DBSession,
) -> Job:
    """Create a new job record."""
    logger.info(f"Creating job: type={job_in.job_type}, project={job_in.project_id}")
    
    project = session.get(Project, job_in.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found: {job_in.project_id}",
        )
    
    job = Job(
        project_id=job_in.project_id,
        job_type=job_in.job_type,
    )
    
    session.add(job)
    session.commit()
    session.refresh(job)
    
    logger.info(f"Created job: {job.id}")
    return job


@router.get(
    "",
    response_model=JobListResponse,
)
def list_jobs(
    session: DBSession,
    project_id: str | None = Query(default=None),
    job_type: JobType | None = Query(default=None),
    job_status: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> JobListResponse:
    """List jobs with optional filters."""
    logger.debug(f"Listing jobs: project={project_id}, type={job_type}, status={job_status}")
    
    query = select(Job)
    count_query = select(func.count()).select_from(Job)
    
    if project_id:
        query = query.where(Job.project_id == project_id)
        count_query = count_query.where(Job.project_id == project_id)
    
    if job_type:
        query = query.where(Job.job_type == job_type)
        count_query = count_query.where(Job.job_type == job_type)
    
    if job_status:
        query = query.where(Job.status == job_status)
        count_query = count_query.where(Job.status == job_status)
    
    query = query.order_by(Job.created_at.desc()).limit(limit)
    
    jobs = session.exec(query).all()
    total = session.exec(count_query).one()
    
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_job(
    job_id: str,
    session: DBSession,
) -> Job:
    """Get a job by ID."""
    logger.debug(f"Getting job: {job_id}")
    
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    return job


@router.put(
    "/{job_id}/progress",
    response_model=JobResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_job_progress(
    job_id: str,
    progress_update: JobProgressUpdate,
    session: DBSession,
) -> Job:
    """Update job progress."""
    logger.debug(f"Updating job progress: {job_id} -> {progress_update.progress}")
    
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    job.progress = progress_update.progress
    if progress_update.status:
        job.status = progress_update.status
        if progress_update.status == JobStatus.STARTED and not job.started_at:
            job.started_at = datetime.utcnow()
    
    session.add(job)
    session.commit()
    session.refresh(job)
    
    return job


@router.put(
    "/{job_id}/status",
    response_model=JobResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_job_status(
    job_id: str,
    status_update: JobStatusUpdate,
    session: DBSession,
) -> Job:
    """Update job status."""
    logger.info(f"Updating job status: {job_id} -> {status_update.status}")
    
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    job.status = status_update.status
    
    if status_update.status == JobStatus.STARTED:
        job.started_at = datetime.utcnow()
    elif status_update.status in (JobStatus.SUCCESS, JobStatus.FAILURE, JobStatus.REVOKED):
        job.completed_at = datetime.utcnow()
        if status_update.status == JobStatus.SUCCESS:
            job.progress = 1.0
    
    if status_update.error_message:
        job.error_message = status_update.error_message
    if status_update.error_traceback:
        job.error_traceback = status_update.error_traceback
    if status_update.result:
        job.result = status_update.result
    
    session.add(job)
    session.commit()
    session.refresh(job)
    
    return job


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
def cancel_job(
    job_id: str,
    session: DBSession,
) -> Job:
    """Cancel a running job."""
    logger.info(f"Cancelling job: {job_id}")
    
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    if job.status not in (JobStatus.PENDING, JobStatus.STARTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in status: {job.status}",
        )
    
    # TODO: Actually revoke Celery task
    # if job.celery_task_id:
    #     celery_app.control.revoke(job.celery_task_id, terminate=True)
    
    job.status = JobStatus.REVOKED
    job.completed_at = datetime.utcnow()
    
    session.add(job)
    session.commit()
    session.refresh(job)
    
    logger.info(f"Cancelled job: {job_id}")
    return job


@router.get(
    "/{job_id}/shot-renders",
    response_model=ShotRenderListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_job_shot_renders(
    job_id: str,
    session: DBSession,
) -> ShotRenderListResponse:
    """List all shot renders for a job."""
    logger.debug(f"Listing shot renders for job: {job_id}")
    
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    
    query = (
        select(ShotRender)
        .where(ShotRender.job_id == job_id)
        .order_by(ShotRender.shot_id)
    )
    renders = session.exec(query).all()
    
    return ShotRenderListResponse(
        items=[ShotRenderResponse.model_validate(r) for r in renders],
        total=len(renders),
    )


@router.get(
    "/shot-renders/{render_id}",
    response_model=ShotRenderResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_shot_render(
    render_id: str,
    session: DBSession,
) -> ShotRender:
    """Get a shot render by ID."""
    logger.debug(f"Getting shot render: {render_id}")
    
    render = session.get(ShotRender, render_id)
    if not render:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shot render not found: {render_id}",
        )
    
    return render
