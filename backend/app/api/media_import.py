"""Network media import route — create media records from network URLs."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import MediaType, UrlRole
from app.models.library import MediaLibrary
from app.models.media import Media, MediaUrl, VideoTag
from app.schemas.media import MediaResponse
from app.schemas.tag import TagResponse

router = APIRouter(prefix="/media", tags=["media-import"])


class NetworkMediaImport(BaseModel):
    """Schema for importing a network-only media item."""
    library_id: int
    url: str = Field(..., max_length=2000)
    title: str = Field(..., max_length=500)
    url_role: UrlRole = UrlRole.SOURCE
    platform: str | None = Field(None, max_length=100)
    description: str | None = None


@router.post("/import-network", response_model=MediaResponse, status_code=201)
async def import_network_media(
    payload: NetworkMediaImport,
    db: AsyncSession = Depends(get_db),
):
    """Create a network-only media record with a source URL."""
    lib = await db.get(MediaLibrary, payload.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")

    url_path = payload.url.split("?")[0].split("#")[0]
    file_name = url_path.rsplit("/", 1)[-1] if "/" in url_path else payload.title
    if not file_name or len(file_name) > 500:
        file_name = payload.title

    platform = payload.platform
    if not platform:
        lower_url = payload.url.lower()
        if "youtube.com" in lower_url or "youtu.be" in lower_url:
            platform = "youtube"
        elif "bilibili.com" in lower_url or "b23.tv" in lower_url:
            platform = "bilibili"
        elif "vimeo.com" in lower_url:
            platform = "vimeo"

    media = Media(
        library_id=payload.library_id,
        title=payload.title,
        file_path=None,
        file_name=file_name,
        media_type=MediaType.NETWORK,
        file_missing=False,
        description=payload.description,
    )
    db.add(media)
    await db.flush()

    url_record = MediaUrl(
        media_id=media.id,
        url=payload.url,
        url_role=payload.url_role,
        title=payload.title if payload.url_role == UrlRole.SOURCE else None,
        platform=platform,
    )
    db.add(url_record)
    await db.flush()

    query = (
        select(Media)
        .where(Media.id == media.id)
        .options(
            selectinload(Media.urls),
            selectinload(Media.segments),
            selectinload(Media.video_tags).selectinload(VideoTag.tag),
            selectinload(Media.subtitles),
        )
    )
    result = await db.execute(query)
    media = result.scalar_one_or_none()

    resp = MediaResponse.model_validate(media)
    resp.tags = [TagResponse.model_validate(vt.tag) for vt in media.video_tags]
    return resp
