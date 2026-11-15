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


class NetworkUrlItem(BaseModel):
    """一条线路/一集。line_name + episode_name 让播放器能显示可读的源名。"""
    url: str = Field(..., max_length=2000)
    line_name: str | None = Field(None, max_length=100)
    episode_name: str | None = Field(None, max_length=200)
    episode_index: int | None = None


class NetworkMediaImport(BaseModel):
    """Schema for importing a network-only media item."""
    library_id: int
    url: str = Field(..., max_length=2000)
    title: str = Field(..., max_length=500)
    url_role: UrlRole = UrlRole.SOURCE
    platform: str | None = Field(None, max_length=100)
    description: str | None = None
    # 在线源信息：source_name 用于显示，source_id 便于日后回源刷新
    source_name: str | None = Field(None, max_length=100)
    source_id: str | None = Field(None, max_length=100)
    # 完整线路/剧集列表。不传则只入库 url 一条，保持旧行为。
    urls: list[NetworkUrlItem] = Field(default_factory=list)


def _detect_platform(url: str) -> str | None:
    """按域名推断平台；仅覆盖明确已知的几家，其余留空。"""
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "bilibili.com" in lower or "b23.tv" in lower:
        return "bilibili"
    if "vimeo.com" in lower:
        return "vimeo"
    return None


def _ordered_entries(payload: NetworkMediaImport) -> list[NetworkUrlItem]:
    """去重后按「当前播放的那条排第一」排序。

    在线源里 `url` 是用户点开播放的那一条，其余是同一部片的其它线路/集数。
    把它排第一，播放器默认选中的就是用户刚才在看的那条。
    """
    ordered: list[NetworkUrlItem] = []
    seen: set[str] = set()
    for entry in payload.urls:
        if not entry.url or entry.url in seen:
            continue
        seen.add(entry.url)
        ordered.append(entry)

    primary = next((e for e in ordered if e.url == payload.url), None)
    if primary is None:
        ordered.insert(0, NetworkUrlItem(url=payload.url))
    elif ordered[0] is not primary:
        ordered.remove(primary)
        ordered.insert(0, primary)
    return ordered


@router.post("/import-network", response_model=MediaResponse, status_code=201)
async def import_network_media(
    payload: NetworkMediaImport,
    db: AsyncSession = Depends(get_db),
):
    """Create a network-only media record with one or more source URLs."""
    lib = await db.get(MediaLibrary, payload.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")

    url_path = payload.url.split("?")[0].split("#")[0]
    file_name = url_path.rsplit("/", 1)[-1] if "/" in url_path else payload.title
    if not file_name or len(file_name) > 500:
        file_name = payload.title

    entries = _ordered_entries(payload)
    platform = payload.platform or _detect_platform(payload.url)

    media = Media(
        library_id=payload.library_id,
        title=payload.title,
        file_path=None,
        file_name=file_name,
        media_type=MediaType.NETWORK,
        file_missing=False,
        description=payload.description,
        # 多集/多线路说明这是剧集，先落 series_title 便于后续聚合
        series_title=payload.title if len(entries) > 1 else None,
    )
    db.add(media)
    await db.flush()

    for entry in entries:
        db.add(
            MediaUrl(
                media_id=media.id,
                url=entry.url,
                url_role=payload.url_role,
                title=(
                    entry.episode_name or payload.title
                    if payload.url_role == UrlRole.SOURCE
                    else None
                ),
                platform=payload.platform or _detect_platform(entry.url) or platform,
                source_name=payload.source_name,
                source_id=payload.source_id,
                line_name=entry.line_name,
                episode_name=entry.episode_name,
                episode_index=entry.episode_index,
            )
        )
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
