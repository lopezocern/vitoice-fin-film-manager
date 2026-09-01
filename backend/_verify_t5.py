# -*- coding: utf-8 -*-
"""T5 verification: stale asset paths before/after rewrite + endpoint smoke."""
import os

os.environ["VITOICE_ENV"] = "dev"

import sqlite3
from pathlib import Path

DB = Path("data/vitoice_dev.db")


def count_stale():
    conn = sqlite3.connect(str(DB))
    present = {r[1] for r in conn.execute("PRAGMA table_info(media)")}
    cols = [c for c in ("thumbnail_path", "poster_path", "backdrop_path") if c in present]
    stale = {c: 0 for c in cols}
    total = {c: 0 for c in cols}
    for col in cols:
        rows = conn.execute(
            f"SELECT {col} FROM media WHERE {col} IS NOT NULL"
        ).fetchall()
        for (v,) in rows:
            if not isinstance(v, str):
                continue
            total[col] += 1
            if not Path(v).is_file():
                stale[col] += 1
    conn.close()
    return stale, total


before, total = count_stale()
print("BEFORE  stale:", before, "| total set:", total)

# Trigger the import-time rewrite (idempotent) and the endpoint fallback
from app import config  # noqa: E402  (import runs migration + rewrite)

config._rewrite_legacy_asset_paths(DB, config._DATA_ROOT)

after, _ = count_stale()
print("AFTER   stale:", after)

# Endpoint smoke via TestClient: collect a few media ids and fetch thumbnails
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app) as c:
    ids = [r[0] for r in sqlite3.connect(str(DB)).execute(
        "SELECT id FROM media WHERE is_deleted=0 AND thumbnail_path IS NOT NULL LIMIT 8"
    ).fetchall()]
    ok404 = 0
    for mid in ids:
        r = c.get(f"/api/media/{mid}/thumbnail")
        if r.status_code == 200:
            ok404 += 1
    print(f"thumbnail endpoint: {ok404}/{len(ids)} returned 200")
print("T5 SMOKE DONE")
