"""Global search route."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.media import Media
from app.services.restricted import get_restricted_library_ids
from app.schemas.media import MediaResponse

router = APIRouter(prefix="/search", tags=["search"])


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user search text is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=list[MediaResponse])
async def search_media(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """Global search across media title and file name.

    Case-insensitive substring match. Returns up to `limit` results,
    ordered by most recently updated. Excludes soft-deleted and restricted
    content (unless the user has enabled showing restricted content).
    """
    pattern = f"%{_escape_like(q)}%"
    query = (
        select(Media)
        .where(
            Media.is_deleted == False,  # noqa: E712
            or_(
                Media.title.ilike(pattern, escape="\\"),
                Media.file_name.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Media.updated_at.desc())
        .limit(limit)
    )

    # Content restriction filter
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))

    result = await db.execute(query)
    return result.scalars().all()
