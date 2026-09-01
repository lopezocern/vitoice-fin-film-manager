# -*- coding: utf-8 -*-
"""T3 verification: offline move → scan relinks instead of creating shadows."""
import os
import shutil
import tempfile
from pathlib import Path

os.environ["VITOICE_ENV"] = "dev"

import asyncio


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="vitoice_t3_"))
    # fake video file (scanner only checks extension, no ffprobe at scan time)
    src = tmp / "IPZZ-827.mp4"
    src.write_bytes(b"x" * 1024)

    from app.database import async_session
    from app.models.library import MediaLibrary
    from app.models.media import Media
    from app.services.scanner import scan_library

    async with async_session() as s:
        lib = MediaLibrary(name="_t3_test", root_path=str(tmp), type="video",
                           scrape_mode="none")
        s.add(lib)
        await s.commit()
        await s.refresh(lib)
        lib_id = lib.id

    try:
        # 1. first scan → 1 new record
        n1 = await scan_library(lib_id)
        # 2. offline move into a subdir (app "closed")
        sub = tmp / "S" / "三澄寧"
        sub.mkdir(parents=True)
        moved = sub / "IPZZ-827.mp4"
        shutil.move(str(src), str(moved))
        # 3. rescan → should relink, not create
        n2 = await scan_library(lib_id)

        from sqlalchemy import select
        async with async_session() as s:
            rows = (await s.execute(
                select(Media.id, Media.file_path, Media.file_missing,
                       Media.media_type).where(Media.library_id == lib_id)
            )).fetchall()
        assert n1 == 1, f"first scan should add 1, got {n1}"
        assert n2 == 0, f"rescan should add 0 (relink), got {n2}"
        assert len(rows) == 1, f"expected 1 record total, got {len(rows)}"
        rid, rpath, rmissing, rtype = rows[0]
        assert rpath == str(moved), f"relinked path wrong: {rpath}"
        assert not rmissing, "record should not be missing after relink"
        print(f"RELINK OK: id={rid} path={rpath} missing={rmissing} type={rtype}")
        print("T3 TEST PASSED")
    finally:
        async with async_session() as s:
            from sqlalchemy import delete
            await s.execute(delete(Media).where(Media.library_id == lib_id))
            await s.execute(delete(MediaLibrary).where(MediaLibrary.id == lib_id))
            await s.commit()
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(main())
