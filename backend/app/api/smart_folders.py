"""Smart folder routes — virtual folders defined by rules."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.media import Media
from app.models.smart_folder import SmartFolder
from app.services.restricted import get_restricted_library_ids
from app.rules.engine import evaluate_rule
from app.schemas.media import MediaResponse
from app.schemas.smart_folder import (
    SmartFolderCreate,
    SmartFolderResponse,
    SmartFolderUpdate,
)

logger = logging.getLogger("vitoice.smart_folders")

router = APIRouter(prefix="/smart-folders", tags=["smart-folders"])

# ---------------------------------------------------------------------------
# System preset folders — seeded idempotently on first list. They use the same
# rule-tree JSON format as user folders (the engine treats an empty group as
# "match all"), so the frontend renders them identically; is_system only hides
# delete/edit affordances.
# ---------------------------------------------------------------------------
_PRESET_FOLDERS: list[dict] = [
    {
        "name": "全部媒体",
        "sort_order": -10,
        "rule_json": {"type": "group", "logic": "and", "children": []},
    },
    {
        "name": "继续观看",
        "sort_order": -9,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "playback", "operator": "gt", "value": 0}
            ],
        },
    },
    {
        "name": "未看",
        "sort_order": -8,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "watched", "operator": "eq", "value": False}
            ],
        },
    },
    {
        "name": "本地缺失",
        "sort_order": -7,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "missing", "operator": "eq", "value": True}
            ],
        },
    },
    {
        "name": "网络媒体",
        "sort_order": -6,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "media_type", "operator": "eq", "value": "network"}
            ],
        },
    },
    {
        "name": "最近添加",
        "sort_order": -5,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "recent", "operator": "lte", "value": 7}
            ],
        },
    },
    {
        "name": "未分类",
        "sort_order": -4,
        "rule_json": {
            "type": "group",
            "logic": "and",
            "children": [
                {"type": "condition", "dimension": "no_tag", "operator": "eq", "value": True}
            ],
        },
    },
]

# Colors for presets (soft, distinct)
_PRESET_COLORS = [
    "#6b6b76",  # 全部 — gray
    "#7b73ff",  # 继续观看 — indigo
    "#3b82f6",  # 未看 — blue
    "#f87171",  # 本地缺失 — red
    "#34d399",  # 网络媒体 — green
    "#f5a623",  # 最近添加 — amber
    "#a855f7",  # 未分类 — purple
]


async def init_system_folders(db: AsyncSession) -> None:
    """Idempotently seed system preset folders (by name) on first list."""
    result = await db.execute(
        select(SmartFolder.name).where(SmartFolder.is_system == True)  # noqa: E712
    )
    existing = {row[0] for row in result.fetchall()}

    new_folders: list[SmartFolder] = []
    for i, preset in enumerate(_PRESET_FOLDERS):
        if preset["name"] in existing:
            continue
        folder = SmartFolder(
            name=preset["name"],
            rule_json=preset["rule_json"],
            sort_order=preset["sort_order"],
            color=_PRESET_COLORS[i % len(_PRESET_COLORS)],
            is_system=True,
        )
        db.add(folder)
        new_folders.append(folder)
    if new_folders:
        await db.flush()
        for folder in new_folders:
            await db.refresh(folder)


async def _get_folder_or_404(db: AsyncSession, folder_id: int) -> SmartFolder:
    folder = await db.get(SmartFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Smart folder not found")
    return folder


@router.get("", response_model=list[SmartFolderResponse])
async def list_smart_folders(db: AsyncSession = Depends(get_db)):
    """List all smart folders, ordered by sort_order. Seeds presets on first call.

    Recomputes each preview_count on read so the sidebar count obeys the
    restricted-content switch instead of relying on a possibly stale cache.
    """
    await init_system_folders(db)
    await db.flush()
    result = await db.execute(
        select(SmartFolder).order_by(SmartFolder.sort_order, SmartFolder.id)
    )
    folders = list(result.scalars().all())

    restricted_ids = await get_restricted_library_ids(db)
    for folder in folders:
        query = evaluate_rule(folder.rule_json)
        query = query.where(Media.is_deleted == False)  # noqa: E712
        if restricted_ids:
            query = query.where(~Media.library_id.in_(restricted_ids))
        count_query = query.with_only_columns(func.count())
        folder.preview_count = int((await db.execute(count_query)).scalar_one())
    for folder in folders:
        await db.refresh(folder, attribute_names=['updated_at'])

    return folders


@router.post("", response_model=SmartFolderResponse, status_code=201)
async def create_smart_folder(
    payload: SmartFolderCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new smart folder."""
    folder = SmartFolder(**payload.model_dump())
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.put("/{folder_id}", response_model=SmartFolderResponse)
async def update_smart_folder(
    folder_id: int,
    payload: SmartFolderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a smart folder's name, rules, or appearance."""
    folder = await _get_folder_or_404(db, folder_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(folder, field, value)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
async def delete_smart_folder(folder_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a smart folder (does not affect any media files)."""
    folder = await _get_folder_or_404(db, folder_id)
    await db.delete(folder)
    await db.flush()


@router.get("/{folder_id}/preview", response_model=list[MediaResponse])
async def preview_smart_folder(
    folder_id: int, db: AsyncSession = Depends(get_db)
):
    """Preview media that matches the smart folder's rules.

    Evaluates rule_json against the Media table using the rule engine
    (app/rules/engine.py) and returns the matching items. The cached
    preview_count is refreshed so the sidebar stays in sync.
    """
    folder = await _get_folder_or_404(db, folder_id)

    from app.rules.engine import evaluate_rule

    query = evaluate_rule(folder.rule_json)
    query = query.where(Media.is_deleted == False)  # noqa: E712
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(query)
    media_list = result.scalars().all()

    # Refresh cached hit count
    folder.preview_count = len(media_list)
    await db.flush()

    return [MediaResponse.model_validate(m) for m in media_list]
