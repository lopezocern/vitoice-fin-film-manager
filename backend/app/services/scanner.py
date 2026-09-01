"""File scanner — scans a library directory and creates/updates Media records.

Security:
- root_path is validated and resolved (no path traversal)
- Symbolic links are skipped (prevent symlink attacks)
- os.walk uses followlinks=False explicitly

Performance:
- Delayed metadata extraction (scan first, extract metadata in background task)
- 64KB file hash (not full file hash) for deduplication
- scan_directory runs in asyncio.to_thread (non-blocking)
- Batch updates for existing media (no N+1 queries)
"""
import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("vitoice.scanner")

from app.database import async_session
from app.models.library import MediaLibrary
from app.models.media import Media, MediaUrl
from app.models.enums import MediaType, ScrapeMode, UrlRole

# Supported video extensions
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv", ".3gp",
}


def compute_file_hash(file_path: str, chunk_size: int = 65536) -> str:
    """Compute a 64KB-prefix hash for deduplication (fast, not full-file).

    Reads only the first 64KB of the file — sufficient for uniqueness
    while being fast even for multi-GB files.
    Uses blake2b (non-crypto, collision-resistant, faster than MD5).
    """
    hasher = hashlib.blake2b(digest_size=16)
    try:
        with open(file_path, "rb") as f:
            hasher.update(f.read(chunk_size))
    except (OSError, PermissionError):
        return ""
    return hasher.hexdigest()


def validate_root_path(root_path: str) -> Path:
    """Validate and resolve a library root path.

    Security checks:
    - Must be a non-empty absolute path
    - Resolved (no .. traversal)
    - Must exist and be a directory
    - Must not be a system root (C:\\, /, etc.)

    Returns the resolved Path.
    Raises ValueError if invalid.
    """
    if not root_path or not root_path.strip():
        raise ValueError("root_path cannot be empty")

    raw = Path(root_path)
    if not raw.is_absolute():
        raise ValueError("root_path must be an absolute path")

    resolved = raw.resolve()

    # Block system roots
    if resolved == Path(resolved.root) or str(resolved) in ("C:\\", "C:/", "/", "\\"):
        raise ValueError("Cannot scan system root directory")

    if not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {resolved}")

    return resolved


def scan_directory(root_path: str) -> list[dict]:
    """Walk a directory and return video file info (fast, no metadata).

    Security: skips symbolic links to prevent symlink attacks.
    Returns list of {file_path, file_name, file_size, file_modified_at}.
    """
    results: list[dict] = []
    root = Path(root_path).resolve()

    if not root.exists() or not root.is_dir():
        return results

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Skip hidden directories and symbolic link directories
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and not os.path.islink(os.path.join(dirpath, d))
        ]

        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue

            full_path = os.path.join(dirpath, filename)

            # Skip symbolic link files (security: prevent symlink attacks)
            if os.path.islink(full_path):
                continue

            try:
                stat = os.stat(full_path)  # follows links, but we skipped links above
                results.append({
                    "file_path": os.path.normpath(full_path),
                    "file_name": filename,
                    "file_size": stat.st_size,
                    "file_modified_at": datetime.fromtimestamp(stat.st_mtime),
                })
            except (OSError, PermissionError):
                continue

    return results


async def scan_library(library_id: int, task_id: int | None = None) -> int:
    """Scan a library and create/update Media records.

    Returns the number of new media files found.
    Called by TaskManager as a task worker.

    CRITICAL: This function must NOT hold a DB session open while calling
    task_manager.update_progress(). SQLite pool_size=1 means a second
    session request while one is held will deadlock. The scan is split into
    phases with separate short sessions.
    """
    from app.tasks.manager import task_manager

    new_count = 0
    relink_count = 0

    # --- Phase 1: Load library info (short session) ---
    async with async_session() as session:
        lib = await session.get(MediaLibrary, library_id)
        if not lib:
            raise ValueError(f"Library {library_id} not found")
        try:
            validate_root_path(lib.root_path)
        except ValueError:
            raise ValueError(f"Invalid library root_path: {lib.root_path}")
        # Capture scalar values before session closes (avoid DetachedInstanceError)
        lib_name = lib.name
        lib_root_path = lib.root_path
        lib_scrape_mode = lib.scrape_mode

    # --- Phase 2: Scan directory (no DB session held) ---
    files = await asyncio.to_thread(scan_directory, lib_root_path)
    total = len(files)

    # --- Phase 3: Load existing media records (short session) ---
    async with async_session() as session:
        result = await session.execute(
            select(
                Media.id, Media.file_path, Media.file_modified_at,
                Media.file_size, Media.file_missing, Media.media_type,
                Media.is_deleted,
            ).where(Media.library_id == library_id)
        )
        existing: dict[str, dict] = {}
        # Missing (not soft-deleted) records keyed by filename — used to
        # relink files that were moved/renamed while the app was offline
        # (no watcher event fired, so only a full scan can reconcile them).
        missing_by_name: dict[str, list[dict]] = {}
        for row in result.fetchall():
            # Normalize path for consistent comparison (fixes path separator
            # differences between DB-stored paths and os.walk output)
            norm_path = os.path.normpath(row[1]) if row[1] else row[1]
            existing[norm_path] = {
                "id": row[0],
                "file_modified_at": row[2],
                "file_size": row[3],
                "file_missing": row[4],
                "media_type": row[5],
                "is_deleted": row[6],
                "orig_path": row[1],  # Keep original for potential migration
            }
            if row[4] and not row[6] and row[1]:
                missing_by_name.setdefault(os.path.basename(row[1]), []).append(
                    existing[norm_path]
                )

    # --- Phase 4: Process files + progress updates (no DB session held) ---
    to_update: list[tuple[int, datetime, int]] = []
    to_create: list[Media] = []
    # media_id → new file_path — records whose file moved while offline
    to_relink: dict[int, dict] = {}
    seen_paths: set[str] = set()

    for i, file_info in enumerate(files):
        fp = file_info["file_path"]
        if fp in existing or fp in seen_paths:
            info = existing.get(fp)
            if info and info["file_modified_at"] != file_info["file_modified_at"]:
                to_update.append((
                    info["id"],
                    file_info["file_modified_at"],
                    file_info["file_size"],
                ))
        else:
            # Relink pass: if a missing record in this library has the same
            # filename, the file was most likely moved/renamed offline —
            # reuse the record instead of creating a shadow duplicate.
            candidates = missing_by_name.get(file_info["file_name"])
            if candidates:
                size_matches = [
                    c for c in candidates if c["file_size"] == file_info["file_size"]
                ]
                chosen = (size_matches or candidates)[0]
                to_relink[chosen["id"]] = {
                    "file_path": fp,
                    "file_size": file_info["file_size"],
                    "file_modified_at": file_info["file_modified_at"],
                }
                candidates.remove(chosen)  # one file relinks one record
                seen_paths.add(fp)
                relink_count += 1
                continue

            media = Media(
                library_id=library_id,
                title=Path(file_info["file_name"]).stem,
                file_path=file_info["file_path"],
                file_name=file_info["file_name"],
                media_type=MediaType.LOCAL,
                file_size=file_info["file_size"],
                file_modified_at=file_info["file_modified_at"],
            )
            to_create.append(media)
            seen_paths.add(fp)
            new_count += 1

        # Throttle progress updates: every 5 items or last item
        # (reduces DB write contention during bulk imports)
        if task_id and ((i + 1) % 5 == 0 or i + 1 == total):
            await task_manager.update_progress(
                task_id, current=i + 1, total=total,
                subtitle=file_info["file_name"],
            )

    # --- Phase 5: Detect missing/restored files (pure logic, no DB) ---
    scanned_paths = {f["file_path"] for f in files}
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

    missing_ids: list[int] = []
    restored_ids: list[int] = []
    for fp, info in existing.items():
        if fp is None or info["is_deleted"]:
            continue
        if info["id"] in to_relink:
            continue  # handled by the relink pass — old path is expected gone
        if fp not in scanned_paths:
            if not info["file_missing"]:
                missing_ids.append(info["id"])
        else:
            if info["file_missing"]:
                restored_ids.append(info["id"])

    # --- Phase 6: Batch write — missing/restored/modified/insert (short session) ---
    async with async_session() as session:
        # Migrate non-normalized file_paths to normalized form (one-time fix)
        path_migrations: list[tuple[int, str]] = []
        for norm_fp, info in existing.items():
            orig = info.get("orig_path")
            if orig and orig != norm_fp:
                path_migrations.append((info["id"], norm_fp))
        if path_migrations:
            for mid, nfp in path_migrations:
                await session.execute(
                    update(Media)
                    .where(Media.id == mid)
                    .values(file_path=nfp)
                )
            logger.info(
                "Normalized %d file path(s) in library %s",
                len(path_migrations), library_id,
            )

        # Single-scan relink: a file moved offline produces BOTH a missing old
        # record and a would-be-new record in the same scan pass. Match them
        # by filename and relink instead of missing + shadow duplicate.
        if missing_ids and to_create:
            name_map: dict[str, list[int]] = {}
            mrows = (await session.execute(
                select(Media.id, Media.file_name).where(Media.id.in_(missing_ids))
            )).fetchall()
            for mid, fname in mrows:
                name_map.setdefault(fname, []).append(mid)
            kept: list[Media] = []
            for media in to_create:
                cand = name_map.get(media.file_name)
                if cand:
                    rid = cand.pop(0)
                    missing_ids.remove(rid)
                    to_relink[rid] = {
                        "file_path": media.file_path,
                        "file_size": media.file_size,
                        "file_modified_at": media.file_modified_at,
                    }
                    new_count -= 1
                    relink_count += 1
                else:
                    kept.append(media)
            if len(kept) != len(to_create):
                logger.info(
                    "Relinked %d offline-moved file(s) in library %s",
                    len(to_create) - len(kept), library_id,
                )
                to_create = kept

        # Shadow-duplicate guard: a file copied to a new location, scanned
        # (fresh record created), then original deleted offline leaves BOTH a
        # missing old record and an identical live new record. Merge instead
        # of marking missing (prevents recurring shadow duplicates).
        shadow_merged = 0
        if missing_ids:
            from app.services.missing_reconcile import reconcile_pair

            mrows = (await session.execute(
                select(Media.id, Media.file_name, Media.file_size).where(
                    Media.id.in_(missing_ids)
                )
            )).fetchall()
            merged_ids: list[int] = []
            for mid, fname, fsize in mrows:
                dup = (await session.execute(
                    select(Media.id)
                    .where(
                        Media.library_id == library_id,
                        Media.file_name == fname,
                        Media.id != mid,
                        Media.is_deleted.is_(False),
                        Media.file_missing.is_(False),
                    )
                    .limit(2)
                )).scalars().all()
                live_id = None
                if fsize is not None:
                    exact = (await session.execute(
                        select(Media.id)
                        .where(Media.id.in_(dup), Media.file_size == fsize)
                        .limit(1)
                    )).scalar_one_or_none()
                    live_id = exact or (dup[0] if dup else None)
                else:
                    live_id = dup[0] if dup else None
                if live_id is not None:
                    try:
                        await reconcile_pair(session, mid, live_id, pending_missing=True)
                        merged_ids.append(mid)
                    except ValueError as exc:
                        logger.warning(
                            "Shadow-duplicate merge failed for media %s: %s", mid, exc
                        )
            if merged_ids:
                for mid in merged_ids:
                    missing_ids.remove(mid)
                shadow_merged = len(merged_ids)
                logger.info(
                    "Merged %d shadow-duplicate pair(s) in library %s",
                    shadow_merged, library_id,
                )

        # Mark missing files
        if missing_ids:
            for mid in missing_ids:
                await session.execute(
                    update(Media)
                    .where(Media.id == mid)
                    .values(
                        file_missing=True,
                        missing_detected_at=now_naive,
                        media_type=MediaType.OFFLINE,
                    )
                )
            logger.info(
                "Detected %d missing file(s) in library %s", len(missing_ids), library_id
            )

        # Restore previously missing files that reappeared
        if restored_ids:
            net_result = await session.execute(
                select(MediaUrl.media_id)
                .where(
                    MediaUrl.media_id.in_(restored_ids),
                    MediaUrl.url_role == UrlRole.SOURCE,
                )
                .distinct()
            )
            has_network_ids = {row[0] for row in net_result.fetchall()}

            for rid in restored_ids:
                restored_type = MediaType.BOTH if rid in has_network_ids else MediaType.LOCAL
                await session.execute(
                    update(Media)
                    .where(Media.id == rid)
                    .values(
                        file_missing=False,
                        missing_detected_at=None,
                        media_type=restored_type,
                    )
                )
            logger.info(
                "Restored %d previously missing file(s) in library %s",
                len(restored_ids), library_id,
            )

        # Relink records whose files moved while the app was offline
        if to_relink:
            net_result = await session.execute(
                select(MediaUrl.media_id)
                .where(
                    MediaUrl.media_id.in_(list(to_relink)),
                    MediaUrl.url_role == UrlRole.SOURCE,
                )
                .distinct()
            )
            has_network_ids = {row[0] for row in net_result.fetchall()}
            for rid, vals in to_relink.items():
                relinked_type = (
                    MediaType.BOTH if rid in has_network_ids else MediaType.LOCAL
                )
                await session.execute(
                    update(Media)
                    .where(Media.id == rid)
                    .values(
                        file_path=vals["file_path"],
                        file_size=vals["file_size"],
                        file_modified_at=vals["file_modified_at"],
                        file_missing=False,
                        missing_detected_at=None,
                        media_type=relinked_type,
                    )
                )
            logger.info(
                "Relinked %d moved file(s) in library %s", len(to_relink), library_id
            )

        # Batch update modified files (no N+1)
        for media_id, mod_time, file_size in to_update:
            await session.execute(
                update(Media)
                .where(Media.id == media_id)
                .values(file_modified_at=mod_time, file_size=file_size)
            )

        if (missing_ids or shadow_merged or restored_ids or to_update
                or path_migrations or to_relink):
            await session.commit()

        # Guard against concurrent scans: re-check file_paths right before insert
        if to_create:
            new_paths = [m.file_path for m in to_create]
            recheck = await session.execute(
                select(Media.file_path)
                .where(
                    Media.library_id == library_id,
                    Media.file_path.in_(new_paths),
                )
            )
            race_paths = {row[0] for row in recheck.fetchall()}
            if race_paths:
                to_create = [m for m in to_create if m.file_path not in race_paths]
                new_count -= len(race_paths)
                logger.info(
                    "Skipped %d duplicate(s) from concurrent scan (library %s)",
                    len(race_paths), library_id,
                )

        if to_create:
            session.add_all(to_create)
            try:
                await session.commit()
            except IntegrityError:
                # A watcher event can slip a same-path row in between the
                # recheck above and this commit (uq_media_library_file).
                # Fall back to per-row inserts so one collision doesn't fail
                # the whole scan task.
                await session.rollback()
                logger.warning(
                    "Bulk insert hit unique constraint (library %s); retrying per-row",
                    library_id,
                )
                for media in to_create:
                    try:
                        session.add(media)
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        logger.info(
                            "Skipped duplicate %s (library %s)",
                            media.file_path, library_id,
                        )

    # --- Phase 7: Series aggregation + task enqueueing ---
    if new_count > 0 and lib_scrape_mode == ScrapeMode.TV:
        from app.services.series_aggregator import aggregate_series
        try:
            await aggregate_series(library_id)
        except Exception:
            logger.warning("Series aggregation failed for library %s", library_id, exc_info=True)

    if new_count > 0:
        from app.models.task import Task
        from app.models.enums import TaskStatus

        async with async_session() as s:
            existing_types: set[str] = set()
            result = await s.execute(
                select(Task.type).where(
                    Task.library_id == library_id,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
            )
            for row in result.fetchall():
                existing_types.add(row[0])

        if "metadata" not in existing_types:
            await task_manager.enqueue(
                task_type="metadata",
                title=f"提取元数据 ({lib_name})",
                library_id=library_id,
                priority="medium",
            )
        if "thumbnail" not in existing_types:
            await task_manager.enqueue(
                task_type="thumbnail",
                title=f"生成缩略图 ({lib_name})",
                library_id=library_id,
                priority="low",
            )
        if lib_scrape_mode != ScrapeMode.NONE and "scrape" not in existing_types:
            await task_manager.enqueue(
                task_type="scrape",
                title=f"刮削元数据 ({lib_name})",
                library_id=library_id,
                priority="low",
            )

    return new_count
