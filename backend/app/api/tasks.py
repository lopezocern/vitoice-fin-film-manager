"""Task API endpoints."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.enums import TaskStatus
from app.models.task import Task
from app.schemas.task import TaskResponse

logger = logging.getLogger("vitoice.api.tasks")
router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_response(task: Task) -> TaskResponse:
    """Convert ORM to response (sanitized)."""
    resp = TaskResponse.model_validate(task)
    # error_msg is already sanitized in manager.py (no traceback)
    return resp


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List tasks with optional filters."""
    query = select(Task).order_by(Task.created_at.desc()).limit(min(limit, 200))
    if type:
        query = query.where(Task.type == type)
    if status:
        query = query.where(Task.status == status)
    result = await db.execute(query)
    return [_to_response(t) for t in result.scalars().all()]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_response(task)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a task via the task manager (interrupts running workers)."""
    from app.tasks.manager import task_manager

    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return {"status": task.status.value, "task_id": task_id, "message": "Task already finished"}

    success = await task_manager.cancel(task_id)
    if success:
        return {"status": "cancelled", "task_id": task_id}
    return {"status": task.status.value, "task_id": task_id, "message": "Could not cancel"}


@router.delete("/completed")
async def cleanup_completed_tasks(db: AsyncSession = Depends(get_db)):
    """Delete completed/failed/cancelled tasks older than retention period."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=settings.task_retention_hours)
    result = await db.execute(
        delete(Task).where(
            Task.status.in_([
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ]),
            Task.completed_at < cutoff,
        )
    )
    await db.commit()
    count = result.rowcount or 0
    logger.info("Cleaned up %d completed tasks", count)
    return {"deleted": count}
