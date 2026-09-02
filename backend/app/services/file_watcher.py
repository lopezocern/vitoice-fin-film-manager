"""File watcher — cross-platform real-time directory monitoring.

Windows: ReadDirectoryChangesW (via watchdog)
macOS: FSEvents (via watchdog)
Linux: inotify (via watchdog)

Monitors library directories for changes and triggers scan tasks.
- On file deletion: immediately marks the media record as file_missing
- On file creation/move-in: immediately creates/restores Media records
- On file modification: progressively updates file_size (like Pixcall)
- When file is stable (no modifications for N seconds): extracts metadata
"""
import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from app.models.enums import TaskPriority, MediaType

logger = logging.getLogger("vitoice.file_watcher")

# Max seconds to wait for an observer thread to exit. Bounded so shutdown or
# watch removal can never hang on a stuck event handler.
_JOIN_TIMEOUT = 5.0

# Debounce: batch rapid changes before triggering full scan
DEBOUNCE_SECONDS = 2.0
# Wait time after last modification before considering file "stable" (copy complete)
STABLE_SECONDS = 5.0
# Throttle interval for file_size updates during copy
SIZE_UPDATE_INTERVAL = 2.0


class LibraryEventHandler(FileSystemEventHandler):
    """Handle file system events for a library.

    Implements real-time file detection similar to Pixcall:
    - Files are registered immediately on creation (on_created)
    - File size is updated progressively during copy (on_modified)
    - Metadata extraction triggers when file is stable (no writes for STABLE_SECONDS)
    - Moved files: old path marked missing, new path registered immediately
    - Deleted files: marked missing immediately
    """

    def __init__(self, library_id: int, library_name: str, loop: asyncio.AbstractEventLoop):
        self.library_id = library_id
        self.library_name = library_name
        self.loop = loop
        self._lock = threading.Lock()
        # Debounce for full scan scheduling
        self._debounce_task: Any | None = None
        self._debounce_gen: int = 0

        # Track files being copied/watched for progressive updates
        # path -> media_id (populated by _on_file_appeared, cleaned up by _stable_check/on_deleted)
        self._pending_files: dict[str, int] = {}
        # Stable check generation counters: path -> gen
        self._stable_gens: dict[str, int] = {}
        # Last file_size update timestamp: path -> monotonic seconds
        self._last_size_update: dict[str, float] = {}

    def _is_video(self, path: str) -> bool:
        ext = Path(path).suffix.lower()
        return ext in {
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
            ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv", ".3gp",
        }

    # ------------------------------------------------------------------
    # Event handlers (called from Watchdog thread)
    # ------------------------------------------------------------------

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_video(event.src_path):
            return
        # Immediately register the file — don't wait for full scan
        asyncio.run_coroutine_threadsafe(
            self._on_file_appeared(event.src_path), self.loop
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_video(event.src_path):
            return
        normalized = os.path.normpath(event.src_path)

        # Progressive file_size update (throttled)
        self._try_update_file_size(normalized)

        # Reset stable-file timer if we're tracking this file
        with self._lock:
            gen = self._stable_gens.get(normalized)
            if gen is not None:
                self._stable_gens[normalized] = gen + 1
                media_id = self._pending_files.get(normalized)
                if media_id is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._stable_check(normalized, media_id, self._stable_gens[normalized]),
                        self.loop,
                    )

    def on_deleted(self, event: FileSystemEvent) -> None:
        normalized = os.path.normpath(event.src_path)
        # Clean up tracking dicts
        with self._lock:
            self._pending_files.pop(normalized, None)
            self._stable_gens.pop(normalized, None)
            self._last_size_update.pop(normalized, None)

        if event.is_directory:
            asyncio.run_coroutine_threadsafe(
                self._mark_dir_missing(event.src_path), self.loop
            )
            self._schedule_scan()
            return
        if not self._is_video(event.src_path):
            return
        asyncio.run_coroutine_threadsafe(
            self._mark_file_missing(event.src_path), self.loop
        )
        self._schedule_scan()

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            asyncio.run_coroutine_threadsafe(
                self._update_dir_paths(event.src_path, event.dest_path), self.loop
            )
            self._schedule_scan()
            return
        if not self._is_video(event.src_path):
            return
        # Old path is gone — mark as missing immediately
        asyncio.run_coroutine_threadsafe(
            self._mark_file_missing(event.src_path), self.loop
        )
        # New path — register the file immediately (restores or creates)
        if self._is_video(event.dest_path):
            asyncio.run_coroutine_threadsafe(
                self._on_file_appeared(event.dest_path), self.loop
            )
        self._schedule_scan()

    # ------------------------------------------------------------------
    # File appearance (created or moved in)
    # ------------------------------------------------------------------

    async def _on_file_appeared(self, file_path: str) -> None:
        """Handle a file appearing (created or moved in).

        - If existing record with file_missing=True -> restore immediately
        - If existing record with is_deleted=True -> undelete and restore
        - If no existing record -> create new Media record
        - Schedule stable-file check for metadata extraction
        - Schedule full scan for cleanup (series aggregation, etc.)
        """
        try:
            normalized = os.path.normpath(file_path)

            # Get file stat (file might not be fully copied yet — that's OK)
            try:
                stat = os.stat(file_path)
            except (OSError, PermissionError):
                return

            from app.database import async_session
            from app.models.media import Media, MediaUrl
            from app.models.enums import MediaType, UrlRole
            from sqlalchemy import select, update

            media_id: int | None = None
            needs_metadata = False

            async with async_session() as session:
                # Find existing record by file_path (try normalized, then original)
                result = await session.execute(
                    select(
                        Media.id, Media.file_missing, Media.is_deleted,
                        Media.duration, Media.thumbnail_path,
                    ).where(Media.file_path == normalized)
                )
                row = result.fetchone()

                if not row:
                    # Try with original path (might differ in separators)
                    result = await session.execute(
                        select(
                            Media.id, Media.file_missing, Media.is_deleted,
                            Media.duration, Media.thumbnail_path,
                        ).where(Media.file_path == file_path)
                    )
                    row = result.fetchone()

                if row:
                    mid, file_missing, is_deleted, duration, _thumbnail = row

                    if is_deleted:
                        # Undelete and restore — mirror the file_missing
                        # branch: check network sources to decide BOTH/LOCAL
                        # and clear deleted_at so no stale soft-delete data.
                        net_result = await session.execute(
                            select(MediaUrl.media_id).where(
                                MediaUrl.media_id == mid,
                                MediaUrl.url_role == UrlRole.SOURCE,
                            )
                        )
                        has_network = net_result.fetchone() is not None
                        restored_type = MediaType.BOTH if has_network else MediaType.LOCAL
                        await session.execute(
                            update(Media)
                            .where(Media.id == mid)
                            .values(
                                is_deleted=False,
                                deleted_at=None,
                                file_missing=False,
                                missing_detected_at=None,
                                media_type=restored_type,
                                file_size=stat.st_size,
                                file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                            )
                        )
                        await session.commit()
                        media_id = mid
                        needs_metadata = duration is None
                        logger.info(
                            "Restored deleted media %d (file reappeared: %s)",
                            mid, file_path,
                        )

                    elif file_missing:
                        # Restore missing file — check for network sources
                        net_result = await session.execute(
                            select(MediaUrl.media_id).where(
                                MediaUrl.media_id == mid,
                                MediaUrl.url_role == UrlRole.SOURCE,
                            )
                        )
                        has_network = net_result.fetchone() is not None
                        restored_type = MediaType.BOTH if has_network else MediaType.LOCAL

                        await session.execute(
                            update(Media)
                            .where(Media.id == mid)
                            .values(
                                file_missing=False,
                                missing_detected_at=None,
                                media_type=restored_type,
                                file_size=stat.st_size,
                                file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                            )
                        )
                        await session.commit()
                        media_id = mid
                        needs_metadata = duration is None
                        logger.info(
                            "Restored missing media %d (file reappeared: %s)",
                            mid, file_path,
                        )

                    else:
                        # File exists and not missing — update size/mtime
                        await session.execute(
                            update(Media)
                            .where(Media.id == mid)
                            .values(
                                file_size=stat.st_size,
                                file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                            )
                        )
                        await session.commit()
                        media_id = mid
                        needs_metadata = duration is None

                else:
                    # 精确路径未匹配 → 先尝试回收同库同名记录。
                    # 覆盖场景：文件移动/重命名/事件路径与 DB 路径有分隔符或大小写
                    # 差异时，appeared 事件按路径找不到旧记录，若不回收会新建一条
                    # "影子记录"（同一文件两条记录：旧的被标 missing、新的 local）。
                    # 同库同文件名基本即同一文件（AV 库按番号分目录，文件名唯一），
                    # 复用旧记录并更新路径，避免重复。
                    result = await session.execute(
                        select(
                            Media.id, Media.file_missing, Media.is_deleted,
                            Media.duration,
                        )
                        .where(
                            Media.library_id == self.library_id,
                            Media.file_name == Path(file_path).name,
                            Media.is_deleted == False,  # noqa: E712
                        )
                        .limit(1)
                    )
                    same_name_row = result.fetchone()
                    if same_name_row:
                        mid, _fm, _del, dur = same_name_row
                        net_result = await session.execute(
                            select(MediaUrl.media_id).where(
                                MediaUrl.media_id == mid,
                                MediaUrl.url_role == UrlRole.SOURCE,
                            )
                        )
                        has_net = net_result.fetchone() is not None
                        await session.execute(
                            update(Media)
                            .where(Media.id == mid)
                            .values(
                                file_path=normalized,
                                file_name=Path(file_path).name,
                                file_missing=False,
                                missing_detected_at=None,
                                media_type=(
                                    MediaType.BOTH if has_net else MediaType.LOCAL
                                ),
                                file_size=stat.st_size,
                                file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                            )
                        )
                        await session.commit()
                        media_id = mid
                        needs_metadata = dur is None
                        logger.info(
                            "Reclaimed same-name media %d for %s (path updated)",
                            mid, file_path,
                        )
                    else:
                        # 真正的新文件 — create Media record immediately
                        media = Media(
                            library_id=self.library_id,
                            title=Path(file_path).stem,
                            file_path=normalized,
                            file_name=Path(file_path).name,
                            media_type=MediaType.LOCAL,
                            file_size=stat.st_size,
                            file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                        )
                        session.add(media)
                        await session.flush()  # Get the ID without committing
                        media_id = media.id
                        await session.commit()
                        needs_metadata = True
                        logger.info(
                            "Created new media %d (file appeared: %s, size: %d)",
                            media_id, file_path, stat.st_size,
                        )

            # Track for progressive updates and stable-file check
            if media_id is not None:
                with self._lock:
                    self._pending_files[normalized] = media_id
                    self._last_size_update[normalized] = time.monotonic()

                if needs_metadata:
                    self._schedule_stable_check(normalized, media_id)

            # Schedule full scan for cleanup (series, directory structure, etc.)
            self._schedule_scan()

        except Exception:
            logger.warning(
                "Failed to handle file appearance: %s", file_path, exc_info=True
            )

    # ------------------------------------------------------------------
    # Progressive file_size updates (during copy)
    # ------------------------------------------------------------------

    def _try_update_file_size(self, normalized_path: str) -> None:
        """Throttled file_size update for a file being modified."""
        with self._lock:
            media_id = self._pending_files.get(normalized_path)
            if media_id is None:
                return  # Not tracking this file

            now = time.monotonic()
            last = self._last_size_update.get(normalized_path, 0)
            if now - last < SIZE_UPDATE_INTERVAL:
                return  # Too soon since last update

            self._last_size_update[normalized_path] = now
        asyncio.run_coroutine_threadsafe(
            self._do_size_update(normalized_path, media_id), self.loop
        )

    async def _do_size_update(self, file_path: str, media_id: int) -> None:
        """Update file_size in the database."""
        try:
            try:
                stat = os.stat(file_path)
            except (OSError, PermissionError):
                return

            from app.database import async_session
            from app.models.media import Media
            from sqlalchemy import update

            async with async_session() as session:
                await session.execute(
                    update(Media)
                    .where(Media.id == media_id)
                    .values(
                        file_size=stat.st_size,
                        file_modified_at=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
                await session.commit()
        except Exception:
            logger.debug(
                "Size update failed for media %d: %s", media_id, file_path,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Stable-file detection (copy complete → metadata extraction)
    # ------------------------------------------------------------------

    def _schedule_stable_check(self, file_path: str, media_id: int) -> None:
        """Schedule a stable-file check for metadata extraction.

        Uses a generation counter so rapid modifications only trigger
        one metadata extraction (after the file stops changing).
        """
        with self._lock:
            self._stable_gens[file_path] = self._stable_gens.get(file_path, 0) + 1
            gen = self._stable_gens[file_path]

        asyncio.run_coroutine_threadsafe(
            self._stable_check(file_path, media_id, gen), self.loop
        )

    async def _stable_check(self, file_path: str, media_id: int, gen: int) -> None:
        """Check if file is stable and extract metadata if so.

        A file is "stable" when no modification events have occurred for
        STABLE_SECONDS. This indicates a copy/transfer is complete.
        """
        await asyncio.sleep(STABLE_SECONDS)

        with self._lock:
            current_gen = self._stable_gens.get(file_path, 0)
        if gen != current_gen:
            return  # Newer modification occurred — file not stable yet

        try:
            # Verify file still exists and is accessible
            if not os.path.exists(file_path):
                self._cleanup_tracking(file_path)
                return

            from app.database import async_session
            from app.models.media import Media
            from app.services.metadata import extract_metadata
            from app.services.thumbnail import generate_thumbnail
            from app.config import settings

            # Check if metadata is still needed
            async with async_session() as session:
                media = await session.get(Media, media_id)
                if not media or media.duration is not None:
                    # Already has metadata or record gone
                    self._cleanup_tracking(file_path)
                    return

            # Extract metadata (ffprobe — needs complete file)
            success = await extract_metadata(media_id)

            if success:
                # Generate thumbnail
                output_path = str(settings.thumbnail_dir / f"{media_id}.jpg")
                # Smart-frame selection uses the probed duration when available
                media_duration: float | None = None
                try:
                    async with async_session() as session:
                        m = await session.get(Media, media_id)
                        media_duration = m.duration if m else None
                except Exception:
                    media_duration = None
                thumb_success = await generate_thumbnail(
                    file_path, output_path, duration=media_duration
                )

                if thumb_success:
                    async with async_session() as session:
                        media = await session.get(Media, media_id)
                        if media:
                            media.thumbnail_path = output_path
                            await session.commit()

                logger.info(
                    "Metadata + thumbnail extracted for media %d (file stable: %s)",
                    media_id, file_path,
                )
            else:
                logger.warning(
                    "Metadata extraction failed for media %d (file: %s) — file may be incomplete",
                    media_id, file_path,
                )

        except Exception:
            logger.warning(
                "Stable check failed for media %d: %s", media_id, file_path,
                exc_info=True,
            )
        finally:
            self._cleanup_tracking(file_path)

    def _cleanup_tracking(self, file_path: str) -> None:
        """Remove file from all tracking dicts."""
        with self._lock:
            self._pending_files.pop(file_path, None)
            self._stable_gens.pop(file_path, None)
            self._last_size_update.pop(file_path, None)

    # ------------------------------------------------------------------
    # Missing file detection (existing functionality)
    # ------------------------------------------------------------------

    async def _mark_file_missing(self, file_path: str) -> None:
        """Mark a media record as file_missing based on its file_path.

        Runs in the asyncio event loop (called via run_coroutine_threadsafe).
        Only marks non-deleted records. The debounced scan will handle
        full detection and media_type transitions.
        """
        try:
            from app.database import async_session
            from app.models.media import Media
            from sqlalchemy import update, select

            normalized = os.path.normpath(file_path)

            async with async_session() as session:
                # Find the media record by file_path (try normalized first)
                result = await session.execute(
                    select(Media.id, Media.file_missing, Media.is_deleted)
                    .where(Media.file_path == normalized)
                )
                row = result.fetchone()
                if not row:
                    # Try with original path (might differ in separators)
                    result = await session.execute(
                        select(Media.id, Media.file_missing, Media.is_deleted)
                        .where(Media.file_path == file_path)
                    )
                    row = result.fetchone()

                if not row or row[2]:  # not found or already deleted
                    return

                media_id = row[0]
                already_missing = row[1]
                if already_missing:
                    return  # Already marked

                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.execute(
                    update(Media)
                    .where(Media.id == media_id)
                    .values(
                        file_missing=True,
                        missing_detected_at=now_naive,
                        media_type=MediaType.OFFLINE,
                    )
                )
                await session.commit()
                logger.info(
                    "Marked media %d as file_missing (file deleted: %s)",
                    media_id, file_path,
                )
        except Exception:
            logger.warning(
                "Failed to mark file_missing for %s", file_path, exc_info=True
            )

    async def _mark_dir_missing(self, dir_path: str) -> None:
        """Mark all media records under a deleted directory as file_missing.

        Uses prefix matching (LIKE 'dir_path%') to find all affected records.
        """
        try:
            from app.database import async_session
            from app.models.media import Media
            from sqlalchemy import update, select

            normalized = os.path.normpath(dir_path)

            async with async_session() as session:
                result = await session.execute(
                    select(Media.id, Media.file_path).where(
                        Media.file_path.like(f"{normalized}%"),
                        Media.is_deleted == False,  # noqa: E712
                        Media.file_missing == False,  # noqa: E712
                    )
                )
                # S4 fix: LIKE "%" prefix would match sibling dirs (e.g.
                # "Show2" when "Show" is deleted) — require separator boundary.
                affected_ids = [
                    mid
                    for mid, fp in result.fetchall()
                    if fp == normalized
                    or fp.startswith(normalized + os.sep)
                    or fp.startswith(normalized + "/")
                ]
                if not affected_ids:
                    return

                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.execute(
                    update(Media)
                    .where(Media.id.in_(affected_ids))
                    .values(
                        file_missing=True,
                        missing_detected_at=now_naive,
                        media_type=MediaType.OFFLINE,
                    )
                )
                await session.commit()
                logger.info(
                    "Marked %d media as file_missing (dir deleted: %s)",
                    len(affected_ids), dir_path,
                )
        except Exception:
            logger.warning(
                "Failed to mark dir_missing for %s", dir_path, exc_info=True
            )

    async def _update_dir_paths(self, old_path: str, new_path: str) -> None:
        """Update file_path for all media records under a moved/renamed directory.

        Performs prefix replacement: old_path -> new_path on every matching
        Media.file_path.
        """
        try:
            from app.database import async_session
            from app.models.media import Media
            from sqlalchemy import update, select

            old_normalized = os.path.normpath(old_path)
            new_normalized = os.path.normpath(new_path)

            async with async_session() as session:
                result = await session.execute(
                    select(Media.id, Media.file_path).where(
                        Media.file_path.like(f"{old_normalized}%"),
                        Media.is_deleted == False,  # noqa: E712
                    )
                )
                # S4 fix: LIKE "%" prefix would match sibling dirs — require
                # the path to equal the dir or start with a separator.
                affected = [
                    (mid, fp)
                    for mid, fp in result.fetchall()
                    if fp == old_normalized
                    or fp.startswith(old_normalized + os.sep)
                    or fp.startswith(old_normalized + "/")
                ]
                if not affected:
                    return

                updated = 0
                for media_id, file_path in affected:
                    new_fp = new_normalized + file_path[len(old_normalized):]
                    # uq_media_library_file: another row (incl. soft-deleted)
                    # may already occupy the target path — skip that row
                    # instead of letting the unique constraint abort the
                    # whole rename and leave disk/DB inconsistent.
                    dup = await session.execute(
                        select(Media.id).where(
                            Media.file_path == new_fp,
                            Media.id != media_id,
                        )
                    )
                    if dup.scalar_one_or_none() is not None:
                        logger.warning(
                            "Skip path update for media %d: target already taken (%s)",
                            media_id, new_fp,
                        )
                        continue
                    await session.execute(
                        update(Media)
                        .where(Media.id == media_id)
                        .values(file_path=new_fp)
                    )
                    updated += 1
                await session.commit()
                logger.info(
                    "Updated %d media paths (dir moved: %s -> %s)",
                    updated, old_path, new_path,
                )
        except Exception:
            logger.warning(
                "Failed to update dir paths %s -> %s", old_path, new_path, exc_info=True
            )

    # ------------------------------------------------------------------
    # Debounced full scan scheduling
    # ------------------------------------------------------------------

    def _schedule_scan(self) -> None:
        """Debounce: wait for more changes before triggering scan.

        Uses a generation counter so that only the most recently scheduled
        scan actually fires — previous coroutines see a stale generation
        after sleeping and bail out.
        """
        self._debounce_gen += 1

        self._debounce_task = asyncio.run_coroutine_threadsafe(
            self._debounced_scan(self._debounce_gen), self.loop
        )

    async def _debounced_scan(self, gen: int) -> None:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        if gen != self._debounce_gen:
            return  # A newer scan has been scheduled — bail out

        from app.tasks.manager import task_manager

        await task_manager.enqueue(
            task_type="scan",
            title=f"监控触发扫描 ({self.library_name})",
            library_id=self.library_id,
            priority="medium",
        )


class FileWatcherService:
    """Manages file watchers for all libraries with watch_enabled=True."""

    def __init__(self):
        self._observers: dict[int, Observer] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start watching all libraries with watch_enabled."""
        self._loop = asyncio.get_running_loop()

        from app.database import async_session
        from app.models.library import MediaLibrary
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(
                select(MediaLibrary).where(MediaLibrary.watch_enabled.is_(True))
            )
            libraries = result.scalars().all()

        for lib in libraries:
            await self.add_watch(lib.id, lib.name, lib.root_path)

    async def stop(self) -> None:
        """Stop all watchers."""
        observers = list(self._observers.values())
        for observer in observers:
            observer.stop()
        # join() blocks. Offload it and bound it: a handler stuck on slow I/O
        # (e.g. an ffprobe of a network path) would otherwise freeze the whole
        # event loop — including /health — during shutdown. Observer threads
        # are daemons, so one that outlives the timeout dies with the process.
        await asyncio.gather(
            *(asyncio.to_thread(o.join, _JOIN_TIMEOUT) for o in observers)
        )
        self._observers.clear()

    async def add_watch(self, library_id: int, name: str, root_path: str) -> None:
        """Add a watch for a library."""
        if library_id in self._observers:
            return  # Already watching

        if not os.path.isdir(root_path):
            return

        if not self._loop:
            self._loop = asyncio.get_running_loop()

        handler = LibraryEventHandler(library_id, name, self._loop)
        observer = Observer()
        observer.schedule(handler, root_path, recursive=True)
        observer.start()
        self._observers[library_id] = observer

    async def remove_watch(self, library_id: int) -> None:
        """Remove a watch."""
        if library_id in self._observers:
            observer = self._observers.pop(library_id)
            observer.stop()
            # Same reasoning as stop(): never block the event loop on join().
            await asyncio.to_thread(observer.join, _JOIN_TIMEOUT)


# Global instance
file_watcher = FileWatcherService()
