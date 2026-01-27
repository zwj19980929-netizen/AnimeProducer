"""API layer for AnimeMatrix."""

from fastapi import APIRouter

from api.routes import assets, jobs, projects

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
