"""Segment routes — timeline markers for media."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.segment import Segment
from app.schemas.segment import SegmentCreate, SegmentResponse, SegmentUpdate
from app.services.media_access import get_accessible_media

router = APIRouter(tags=["segments"])


@router.get("/media/{media_id}/segments", response_model=list[SegmentResponse])
async def list_segments(media_id: int, db: AsyncSession = Depends(get_db)):
    """List all segments for a media item, ordered by start_time."""
    # Gate: soft-deleted rows and restricted libraries must not be reachable.
    await get_accessible_media(db, media_id)
    result = await db.execute(
        select(Segment)
        .where(Segment.media_id == media_id)
        .order_by(Segment.start_time)
    )
    return result.scalars().all()


@router.post("/media/{media_id}/segments", response_model=SegmentResponse, status_code=201)
async def create_segment(
    media_id: int,
    payload: SegmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new segment (time-point marker) for a media item."""
    await get_accessible_media(db, media_id)
    data = payload.model_dump()
    data["media_id"] = media_id
    segment = Segment(**data)
    db.add(segment)
    await db.flush()
    await db.refresh(segment)
    return segment


@router.put("/segments/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: int,
    payload: SegmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a segment."""
    segment = await db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(segment, field, value)
    await db.flush()
    await db.refresh(segment)
    return segment


@router.delete("/segments/{segment_id}", status_code=204)
async def delete_segment(segment_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a segment."""
    segment = await db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    await db.delete(segment)
    await db.flush()
