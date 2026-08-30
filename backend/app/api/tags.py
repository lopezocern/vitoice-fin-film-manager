"""Tag and TagType routes — includes media tagging endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger("vitoice.api.tags")
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.media import Media
from app.models.tag import Tag, TagType, VideoTag
from app.schemas.tag import (
    TagCreate,
    TagResponse,
    TagTypeCreate,
    TagTypeResponse,
    TagTypeUpdate,
    TagUpdate,
    VideoTagCreate,
    VideoTagResponse,
)
from app.services.restricted import get_restricted_library_ids, should_hide_restricted

router = APIRouter(tags=["tags"])


# ---------------------------------------------------------------------------
# Tag Types
# ---------------------------------------------------------------------------

@router.get("/tag-types", response_model=list[TagTypeResponse])
async def list_tag_types(db: AsyncSession = Depends(get_db)):
    """List all tag types, ordered by sort_order.

    When ``show_restricted`` is off, AV tag types (name starting with ``av_``)
    are excluded so they don't appear in any UI surface.
    """
    query = select(TagType).order_by(TagType.sort_order, TagType.id)

    hide_restricted = await should_hide_restricted(db)
    if hide_restricted:
        query = query.where(~TagType.name.like("av_%"))

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/tag-types", response_model=TagTypeResponse, status_code=201)
async def create_tag_type(
    payload: TagTypeCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new tag type (category)."""
    tag_type = TagType(**payload.model_dump())
    db.add(tag_type)
    await db.flush()
    await db.refresh(tag_type)
    return tag_type


@router.put("/tag-types/{tag_type_id}", response_model=TagTypeResponse)
async def update_tag_type(
    tag_type_id: int, payload: TagTypeUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a tag type (name, color, sort_order). Builtin types cannot be renamed."""
    tag_type = await db.get(TagType, tag_type_id)
    if not tag_type:
        raise HTTPException(status_code=404, detail="Tag type not found")
    update_data = payload.model_dump(exclude_unset=True)
    # Protect builtin type names from being changed
    if tag_type.is_builtin and "name" in update_data:
        del update_data["name"]
    for field, value in update_data.items():
        setattr(tag_type, field, value)
    await db.flush()
    await db.refresh(tag_type)
    return tag_type


@router.delete("/tag-types/{tag_type_id}", status_code=204)
async def delete_tag_type(
    tag_type_id: int, db: AsyncSession = Depends(get_db)
):
    """Delete a tag type. Builtin types cannot be deleted.

    Cascades to all tags under this type (and their VideoTag associations).
    """
    tag_type = await db.get(TagType, tag_type_id)
    if not tag_type:
        raise HTTPException(status_code=404, detail="Tag type not found")
    if tag_type.is_builtin:
        raise HTTPException(status_code=400, detail="Builtin tag types cannot be deleted")
    await db.delete(tag_type)
    await db.flush()


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    tag_type_id: int | None = Query(None, description="Filter by tag type"),
    library_id: int | None = Query(None, description="Only tags attached to media in this library"),
    exclude_av: bool = Query(False, description="Exclude AV tag types (names starting with av_)"),
    av_only: bool = Query(False, description="Only AV tag types (names starting with av_)"),
    db: AsyncSession = Depends(get_db),
):
    """List tags as a tree, optionally filtered by tag_type_id / library_id / AV scope.

    Tags are loaded flat and assembled into a tree in Python to avoid
    recursive lazy-loading issues in async SQLAlchemy.

    Filtering:
    - ``tag_type_id``: restrict to a single tag type.
    - ``library_id``: only return tags that have at least one VideoTag
      association with media in the given library.
    - ``exclude_av``: drop tags whose TagType name starts with ``av_``.
    - ``av_only``: keep only tags whose TagType name starts with ``av_``.
    """
    query = select(Tag)
    if tag_type_id is not None:
        query = query.where(Tag.tag_type_id == tag_type_id)

    # --- Content restriction: hide AV tag types when show_restricted is off ---
    hide_restricted = await should_hide_restricted(db)
    restricted_ids: set[int] | None = None
    if hide_restricted:
        exclude_av = True
        # 同时排除"只与受限库媒体关联"的标签（含其计数）：否则侧边栏标签树
        # 仍会显示受限内容的标签，点击后内容又被隐藏，体验割裂。
        restricted_ids = await get_restricted_library_ids(db)
        if restricted_ids:
            query = query.where(
                Tag.id.in_(
                    select(VideoTag.tag_id)
                    .join(Media, Media.id == VideoTag.media_id)
                    .where(Media.library_id.notin_(restricted_ids))
                )
            )

    # --- AV scope filtering by tag type name prefix ---
    if exclude_av or av_only:
        # Load AV type IDs
        av_types_result = await db.execute(
            select(TagType.id).where(TagType.name.like("av_%"))
        )
        av_type_ids = {row[0] for row in av_types_result.fetchall()}
        if av_only:
            if not av_type_ids:
                return []  # No AV types exist yet
            query = query.where(Tag.tag_type_id.in_(av_type_ids))
        elif exclude_av:
            if av_type_ids:
                query = query.where(Tag.tag_type_id.notin_(av_type_ids))

    # --- Library filtering: restrict to tags used by media in this library ---
    if library_id is not None:
        query = query.where(
            Tag.id.in_(
                select(VideoTag.tag_id)
                .join(Media, Media.id == VideoTag.media_id)
                .where(Media.library_id == library_id)
            )
        )

    query = query.order_by(Tag.sort_order, Tag.id)

    result = await db.execute(query)
    tags = result.scalars().all()

    # Build children map
    children_map: dict[int, list[Tag]] = {}
    tag_ids = {t.id for t in tags}
    for t in tags:
        if t.parent_id is not None and t.parent_id in tag_ids:
            children_map.setdefault(t.parent_id, []).append(t)

    # Count non-deleted media per tag in a single query
    count_map: dict[int, int] = {}
    if tag_ids:
        count_query = (
            select(
                VideoTag.tag_id,
                func.count(func.distinct(VideoTag.media_id)).label("cnt"),
            )
            .join(Media, Media.id == VideoTag.media_id)
            .where(Media.is_deleted == False)  # noqa: E712
            .where(VideoTag.tag_id.in_(tag_ids))
        )
        # 计数同样排除受限库媒体（与标签列表过滤保持一致）
        if hide_restricted and restricted_ids:
            count_query = count_query.where(Media.library_id.notin_(restricted_ids))
        count_query = count_query.group_by(VideoTag.tag_id)
        count_result = await db.execute(count_query)
        count_map = {row.tag_id: row.cnt for row in count_result}

    # Recursively build response tree
    def _build(tag: Tag) -> TagResponse:
        resp = TagResponse.model_validate(tag)
        resp.children = [_build(c) for c in children_map.get(tag.id, [])]
        resp.media_count = count_map.get(tag.id, 0)
        return resp

    roots = [t for t in tags if t.parent_id is None or t.parent_id not in tag_ids]
    return [_build(t) for t in roots]


@router.post("/tags", response_model=TagResponse, status_code=201)
async def create_tag(payload: TagCreate, db: AsyncSession = Depends(get_db)):
    """Create a new tag.

    ``tag_type_id`` is optional. When omitted, the tag is attached to a
    "custom" tag type, which is created on first use. This keeps the API
    compatible with clients (e.g. the frontend tag editor) that only send a
    name.
    """
    data = payload.model_dump()
    tag_type_id = data.get("tag_type_id")
    if tag_type_id is None:
        result = await db.execute(select(TagType).where(TagType.name == "custom"))
        tag_type = result.scalar_one_or_none()
        if tag_type is None:
            tag_type = TagType(name="custom", sort_order=0)
            db.add(tag_type)
            await db.flush()
        data["tag_type_id"] = tag_type.id

    tag = Tag(**data)
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return tag


@router.get("/tags/suggest")
async def suggest_tags(
    media_id: int = Query(..., description="Media id to suggest tags for"),
    db: AsyncSession = Depends(get_db),
):
    """Suggest tag names for a media item (AI, without persisting).

    Returns a list of tag-name strings. Empty when no AI key is configured or
    the provider returns nothing. Never raises on provider errors so the
    frontend can degrade gracefully.
    """
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    from app.services.ai_tagger import suggest_tags_for_media

    try:
        names = await suggest_tags_for_media(media_id)
    except Exception:  # noqa: BLE001
        logger.warning("Tag suggestion failed for media %s", media_id, exc_info=True)
        names = []
    return names


@router.put("/tags/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int, payload: TagUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a tag."""
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    await db.flush()
    await db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a tag. Cascades to VideoTag associations."""
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.flush()


# ---------------------------------------------------------------------------
# Media Tagging (VideoTag)
# ---------------------------------------------------------------------------

@router.post("/media/{media_id}/tags", response_model=VideoTagResponse, status_code=201)
async def tag_media(
    media_id: int,
    payload: VideoTagCreate,
    db: AsyncSession = Depends(get_db),
):
    """Attach a tag to a media item."""
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    tag = await db.get(Tag, payload.tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Check for duplicate
    existing = await db.execute(
        select(VideoTag).where(
            VideoTag.media_id == media_id, VideoTag.tag_id == payload.tag_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Tag already attached to this media"
        )

    # media_id comes from the path, not the body
    data = payload.model_dump()
    data["media_id"] = media_id
    video_tag = VideoTag(**data)
    db.add(video_tag)
    await db.flush()
    await db.refresh(video_tag)
    return video_tag


@router.delete("/media/{media_id}/tags/{tag_id}", status_code=204)
async def untag_media(
    media_id: int, tag_id: int, db: AsyncSession = Depends(get_db)
):
    """Remove a tag from a media item."""
    result = await db.execute(
        select(VideoTag).where(
            VideoTag.media_id == media_id, VideoTag.tag_id == tag_id
        )
    )
    video_tag = result.scalar_one_or_none()
    if not video_tag:
        raise HTTPException(status_code=404, detail="Tag association not found")
    await db.delete(video_tag)
    await db.flush()
