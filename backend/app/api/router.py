"""Main API router — aggregates all sub-routers.

All routes are exposed under the /api prefix, which is applied by main.py:
    app.include_router(api_router, prefix="/api")

So a route defined as @router.get("/libraries") here is accessible at
GET /api/libraries.
"""
from fastapi import APIRouter

from app.api import (
    batch,
    duplicates,
    libraries,
    media,
    media_ai,
    media_import,
    media_urls,
    network_sources,
    recycle_bin,
    search,
    segments,
    series,
    settings,
    smart_folders,
    stats,
    subtitles,
    tags,
    tasks,
    tools,
)

api_router = APIRouter()

api_router.include_router(libraries.router)
api_router.include_router(media.router)
api_router.include_router(media_urls.router)
api_router.include_router(network_sources.router)
api_router.include_router(media_ai.router)
api_router.include_router(media_import.router)
api_router.include_router(batch.router)
api_router.include_router(series.router)
api_router.include_router(tags.router)
api_router.include_router(segments.router)
api_router.include_router(subtitles.router)
api_router.include_router(smart_folders.router)
api_router.include_router(tasks.router)
api_router.include_router(settings.router)
api_router.include_router(search.router)
api_router.include_router(tools.router)
api_router.include_router(recycle_bin.router)
api_router.include_router(duplicates.router)
api_router.include_router(stats.router)
