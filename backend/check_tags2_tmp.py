import asyncio, sys
sys.path.insert(0, '.')
from sqlalchemy import select, func, case
from app.database import async_session
from app.models.media import Media, VideoTag
from app.models.tag import Tag

async def main():
    async with async_session() as s:
        res = await s.execute(
            select(
                func.count(VideoTag.id),
                func.sum(case((Media.series_id.isnot(None), 1), else_=0)),
                func.sum(case((Media.series_id.is_(None), 1), else_=0)),
            )
            .select_from(VideoTag)
            .join(Media, Media.id == VideoTag.media_id)
        )
        row = res.one()
        print(f"video_tags total={row[0]} on_episodes={row[1]} on_non_episodes={row[2]}")

        res = await s.execute(
            select(func.count(func.distinct(Media.id)))
            .join(VideoTag, VideoTag.media_id == Media.id)
            .where(Media.series_id.isnot(None))
        )
        print("episodes with >=1 tag:", res.scalar())

asyncio.run(main())
