"""FastAPI application entry point.

Binds to 127.0.0.1 by default (local desktop app).
Set VITOICE_HOST=0.0.0.0 only if you need network access.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db

logger = logging.getLogger("vitoice")


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

    # Daily database backup — one snapshot per calendar day, checked lazily
    # every 6 hours (long-running sessions still get their daily backup).
    import asyncio

    from app.services.backup import has_backup_today, run_backup_now

    async def _backup_loop() -> None:
        while True:
            try:
                if not has_backup_today():
                    await asyncio.to_thread(run_backup_now, "scheduled")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — backup must never kill the app
                # Swallowing this silently meant a broken backup was
                # indistinguishable from a working one; log it so the failure
                # is at least visible in the backend log.
                logger.exception(
                    "Scheduled backup failed; will retry in 6h. "
                    "Data safety depends on this — check the data root is writable."
                )
            await asyncio.sleep(6 * 3600)

    backup_task = asyncio.create_task(_backup_loop())

    yield

    # Shutdown
    backup_task.cancel()
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
