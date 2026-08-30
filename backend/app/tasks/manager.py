"""TaskManager — async task dispatch with DB-persisted state.

Key features:
- Tasks persisted in DB (survive restart)
- On restart, running tasks marked as failed
- Concurrency limit with proper asyncio.Task references
- Cancel actually interrupts running workers via asyncio.Task.cancel()
- Traceback logged server-side only; error_msg stores sanitized message
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from app.config import settings
from app.database import async_session
from app.models.enums import TaskPriority, TaskStatus, TaskType
from app.models.task import Task

logger = logging.getLogger("vitoice.tasks")


class TaskManager:
    """Async task manager with DB-persisted state and worker dispatch."""

    def __init__(self):
        self._workers: dict[TaskType, Callable[[Task], Awaitable[dict | None]]] = {}
        self._queue: asyncio.Queue[int] | None = None
        self._running: set[int] = set()
        self._worker_tasks: dict[int, asyncio.Task] = {}  # task_id -> asyncio.Task
        self._task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore | None = None

    def register_worker(
        self, task_type: TaskType, worker: Callable[[Task], Awaitable[dict | None]]
    ) -> None:
        """Register a worker function for a task type."""
        self._workers[task_type] = worker

    async def start(self) -> None:
        """Start the task manager: recover from crash, start dispatch loop."""
        self._queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_tasks)

        # On startup: mark any "running" tasks as "failed" (crash recovery)
        async with async_session() as session:
            await session.execute(
                update(Task)
                .where(Task.status == TaskStatus.RUNNING)
                .values(
                    status=TaskStatus.FAILED,
                    error_msg="Task interrupted by restart",
                    completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await session.commit()

            # Re-enqueue pending tasks
            result = await session.execute(
                select(Task.id)
                .where(Task.status == TaskStatus.PENDING)
                .order_by(Task.created_at)
            )
            for row in result.fetchall():
                await self._queue.put(row[0])

        # Register built-in workers BEFORE starting dispatch (C2 fix)
        self._register_builtin_workers()

        # Start dispatch loop
        self._task = asyncio.create_task(self._dispatch_loop())

        # Start cleanup loop (hourly)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the task manager and all running workers."""
        # Cancel dispatch and cleanup loops
        for bg_task in (self._task, self._cleanup_task):
            if bg_task:
                bg_task.cancel()
                try:
                    await bg_task
                except asyncio.CancelledError:
                    pass

        # Cancel all running workers
        for task_id, worker_task in list(self._worker_tasks.items()):
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        self._worker_tasks.clear()
        self._running.clear()

    def _register_builtin_workers(self) -> None:
        """Register all built-in task workers."""
        from app.services.scanner import scan_library
        from app.services.metadata import extract_metadata_batch, extract_subtitles
        from app.services.thumbnail import generate_thumbnail_batch
        from app.services.ai_tagger import tag_media_batch_with_ai
        from app.services.scraper import scrape_media_batch

        async def scan_worker(task: Task):
            if not task.library_id:
                raise ValueError("Scan task requires library_id")
            count = await scan_library(task.library_id, task.id)
            return {"new_count": count}

        async def metadata_worker(task: Task):
            if not task.library_id:
                raise ValueError("Metadata task requires library_id")
            count = await extract_metadata_batch(task.library_id, task.id)
            return {"processed_count": count}

        async def thumbnail_worker(task: Task):
            if not task.library_id:
                raise ValueError("Thumbnail task requires library_id")
            count = await generate_thumbnail_batch(task.library_id, task.id)
            return {"generated_count": count}

        async def ai_tag_worker(task: Task):
            re_tag = False
            if task.result:
                try:
                    meta = json.loads(task.result) if isinstance(task.result, str) else task.result
                    re_tag = meta.get("re_tag", False)
                except (json.JSONDecodeError, TypeError):
                    pass
            count = await tag_media_batch_with_ai(task.library_id, task.id, unverified_only=not re_tag)
            return {"tagged_count": count}

        async def subtitle_worker(task: Task):
            if not task.media_id:
                raise ValueError("Subtitle task requires media_id")
            count = await extract_subtitles(task.media_id)
            return {"subtitle_count": count}

        async def hash_worker(task: Task):
            from app.services.perceptual_hash import find_duplicates
            dups = await find_duplicates(task.library_id)
            return {"duplicate_pairs": len(dups)}

        async def scrape_worker(task: Task):
            re_scrape = False
            if task.result:
                try:
                    meta = json.loads(task.result) if isinstance(task.result, str) else task.result
                    re_scrape = meta.get("re_scrape", False)
                except (json.JSONDecodeError, TypeError):
                    pass
            count = await scrape_media_batch(task.library_id, task.id, re_scrape=re_scrape)
            return {"matched_count": count}

        self.register_worker(TaskType.SCAN, scan_worker)
        self.register_worker(TaskType.METADATA, metadata_worker)
        self.register_worker(TaskType.THUMBNAIL, thumbnail_worker)
        self.register_worker(TaskType.AI_TAG, ai_tag_worker)
        self.register_worker(TaskType.SUBTITLE, subtitle_worker)
        self.register_worker(TaskType.HASH, hash_worker)
        self.register_worker(TaskType.SCRAPE, scrape_worker)

    async def enqueue(
        self,
        task_type: str | TaskType,
        title: str,
        subtitle: str | None = None,
        priority: str | TaskPriority = TaskPriority.MEDIUM,
        library_id: int | None = None,
        media_id: int | None = None,
        result: str | None = None,
    ) -> int:
        """Create a new task and enqueue it. Returns task ID.

        ``result`` is an optional JSON string that is atomically stored on the
        Task record at creation time, so workers can read it immediately when
        they pick up the task (avoids the race condition where the caller sets
        ``result`` after enqueue but before the worker runs).
        """
        task_type = TaskType(task_type) if isinstance(task_type, str) else task_type
        priority = TaskPriority(priority) if isinstance(priority, str) else priority

        async with async_session() as session:
            task = Task(
                type=task_type,
                status=TaskStatus.PENDING,
                priority=priority,
                title=title,
                subtitle=subtitle,
                library_id=library_id,
                media_id=media_id,
                result=result,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            task_id = task.id

        if self._queue:
            await self._queue.put(task_id)
        return task_id

    async def cancel(self, task_id: int) -> bool:
        """Cancel a pending or running task.

        For running tasks, cancels the asyncio.Task to interrupt the worker.
        Checks current status before overwriting to avoid race conditions.
        """
        # Cancel the running asyncio.Task if exists
        worker_task = self._worker_tasks.get(task_id)
        if worker_task and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        # Update DB status (only if not already in terminal state)
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()

        self._running.discard(task_id)
        self._worker_tasks.pop(task_id, None)
        return True

    async def update_progress(
        self,
        task_id: int,
        current: int | None = None,
        total: int | None = None,
        progress: int | None = None,
        subtitle: str | None = None,
    ) -> None:
        """Update task progress (called by workers).

        ``subtitle`` is an optional human-readable line describing what the
        worker is doing *right now* (e.g. the file being scanned). It is
        surfaced to the UI as the task's live activity message.
        """
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if not task:
                return

            if current is not None:
                task.current = current
            if total is not None:
                task.total = total
            if progress is not None:
                task.progress = progress
            elif current is not None and total is not None and total > 0:
                task.progress = int(current / total * 100)
            if subtitle is not None:
                task.subtitle = subtitle[:200]

            await session.commit()

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop: pick tasks from queue, run with concurrency limit."""
        while True:
            assert self._queue is not None
            task_id = await self._queue.get()

            # Check if task is still pending (not cancelled)
            async with async_session() as session:
                task = await session.get(Task, task_id)
                if not task or task.status != TaskStatus.PENDING:
                    continue

            # Use semaphore for concurrency control (no busy-wait)
            assert self._semaphore is not None
            await self._semaphore.acquire()
            self._running.add(task_id)

            # Create worker task and save reference (prevent GC)
            worker_task = asyncio.create_task(self._run_worker(task_id))
            self._worker_tasks[task_id] = worker_task

    async def _run_worker(self, task_id: int) -> None:
        """Run a single task worker."""
        assert self._semaphore is not None
        try:
            # Extract task data in a session, then close it (avoid DetachedInstanceError)
            async with async_session() as session:
                task = await session.get(Task, task_id)
                if not task:
                    self._running.discard(task_id)
                    return

                # S5 race fix: the dispatch loop checked PENDING *before*
                # acquiring the semaphore; cancel() may have set CANCELLED in
                # that window. Re-check here so we never resurrect a cancelled
                # task. The finally block releases the semaphore.
                if task.status != TaskStatus.PENDING:
                    logger.info(
                        "Task %s skipped at start (status=%s)",
                        task_id, task.status.value,
                    )
                    return

                # Mark as running
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()

                # Extract plain attributes (don't pass ORM object to worker)
                task_type = task.type
                task_library_id = task.library_id
                task_media_id = task.media_id
                task_title = task.title
                task_result = task.result  # JSON string or None

            # Build a lightweight data object for the worker
            class TaskData:
                pass

            task_data = TaskData()
            task_data.id = task_id
            task_data.type = task_type
            task_data.library_id = task_library_id
            task_data.media_id = task_media_id
            task_data.title = task_title
            task_data.result = task_result

            # Get worker
            worker = self._workers.get(task_type)
            if not worker:
                await self._fail_task(task_id, f"No worker registered for {task_type}")
                return

            # Run worker with timeout
            timeout_seconds = settings.task_timeout_minutes * 60
            try:
                result = await asyncio.wait_for(
                    worker(task_data), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Task %s timed out after %d minutes",
                    task_id, settings.task_timeout_minutes,
                )
                await self._fail_task(
                    task_id,
                    f"任务超时（{settings.task_timeout_minutes} 分钟）",
                )
                return

            # Mark as completed — but check if task was cancelled during execution
            async with async_session() as session:
                task = await session.get(Task, task_id)
                if task:
                    # Don't overwrite CANCELLED status (race condition guard)
                    if task.status == TaskStatus.CANCELLED:
                        return
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100
                    task.result = json.dumps(result) if result else None
                    task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await session.commit()

        except asyncio.CancelledError:
            # Task was cancelled via cancel() — status already set
            logger.info("Task %s was cancelled", task_id)
            raise

        except Exception as e:
            # Log full traceback server-side; store only sanitized message in DB
            logger.exception("Worker failed for task %s", task_id)
            safe_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            await self._fail_task(task_id, safe_msg)

        finally:
            self._running.discard(task_id)
            self._worker_tasks.pop(task_id, None)
            self._semaphore.release()

    async def _fail_task(self, task_id: int, error_msg: str) -> None:
        """Mark a task as failed."""
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error_msg = error_msg
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()

    async def _cleanup_loop(self) -> None:
        """Hourly cleanup: delete completed/failed/cancelled tasks older than retention."""
        while True:
            await asyncio.sleep(3600)  # 1 hour
            try:
                cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=settings.task_retention_hours)
                async with async_session() as session:
                    # Bulk delete (no loading into memory)
                    result = await session.execute(
                        delete(Task).where(
                            Task.status.in_([
                                TaskStatus.COMPLETED,
                                TaskStatus.FAILED,
                                TaskStatus.CANCELLED,
                            ]),
                            Task.completed_at < cutoff,
                        )
                    )
                    await session.commit()
                    if result.rowcount > 0:
                        logger.info("Cleaned up %d old tasks", result.rowcount)
            except Exception:
                logger.warning("Task cleanup loop error", exc_info=True)


# Global singleton
task_manager = TaskManager()
