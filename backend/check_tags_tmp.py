import asyncio, sys
sys.path.insert(0, '.')
from sqlalchemy import select, func
from app.database import async_session
from app.models.series import Series
from app.models.media import Media, VideoTag

async def main():
    async with async_session() as s:
        res = await s.execute(select(Series.id, Series.title).limit(5))
        print("series:", res.all())
        res = await s.execute(select(func.count(Media.id)).where(Media.series_id.isnot(None)))
        print("media with series_id:", res.scalar())
        res = await s.execute(select(func.count(VideoTag.id)))
        print("total video_tags:", res.scalar())
        res = await s.execute(
            select(Media.series_id, func.count(func.distinct(VideoTag.tag_id)))
            .join(VideoTag, VideoTag.media_id == Media.id)
            .where(Media.series_id.isnot(None))
            .group_by(Media.series_id)
            .limit(5)
        )
        print("series with tagged episodes:", res.all())

asyncio.run(main())
