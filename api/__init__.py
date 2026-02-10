"""API layer for AnimeMatrix."""

from fastapi import APIRouter

from api.routes import api_test, assets, books, chapters, episodes, jobs, projects

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(chapters.router, prefix="/projects/{project_id}/chapters", tags=["chapters"])
api_router.include_router(episodes.router, prefix="/projects/{project_id}/episodes", tags=["episodes"])
api_router.include_router(books.router, prefix="/projects/{project_id}/book", tags=["books"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(api_test.router, prefix="/api-test", tags=["api-test"])
