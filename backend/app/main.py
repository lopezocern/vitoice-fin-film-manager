"""FastAPI application entry point.

Binds to 127.0.0.1 by default (local desktop app).
Set VITOICE_HOST=0.0.0.0 only if you need network access.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Import rules to register handlers
    from app.rules import handlers  # noqa: F401

    # Startup: create tables if they don't exist (Alembic handles migrations)
    await init_db()

    # Start the task manager
    from app.tasks.manager import task_manager
    await task_manager.start()

    # Start file watchers for libraries with watch_enabled
    from app.services.file_watcher import file_watcher
    await file_watcher.start()

    yield

    # Shutdown
    await file_watcher.stop()
    await task_manager.stop()


app = FastAPI(
    title="vitoice",
    version="0.1.0",
    description="Desktop media asset management — 播放即整理",
    lifespan=lifespan,
)

# CORS — restricted origins and methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# Register routers
from app.api.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
