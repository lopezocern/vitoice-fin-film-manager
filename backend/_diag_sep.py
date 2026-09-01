# -*- coding: utf-8 -*-
"""Diagnose per-library file_path separator consistency vs dir prefix matching."""
import os
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "data" / "vitoice_dev.db"
conn = sqlite3.connect(str(DB))

for lid, name, root in conn.execute(
    "SELECT id, name, root_path FROM media_libraries"
).fetchall():
    rows = conn.execute(
        "SELECT file_path FROM media WHERE library_id=? AND is_deleted=0", (lid,)
    ).fetchall()
    seps = {}
    inroot = 0
    norm_root = root.rstrip("\\/").replace("\\", "/").lower()
    for (fp,) in rows:
        if fp is None:
            s = "NULL"
        elif "\\" in fp and "/" in fp:
            s = "mixed"
        elif "\\" in fp:
            s = "backslash"
        elif "/" in fp:
            s = "slash"
        else:
            s = "none"
        seps[s] = seps.get(s, 0) + 1
        if fp:
            norm_fp = fp.replace("\\", "/").lower()
            if norm_fp.startswith(norm_root + "/") or norm_fp == norm_root:
                inroot += 1
    subs = 0
    sub_files = 0
    if os.path.isdir(root):
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if os.path.isdir(p):
                subs += 1
                for _, _, files in os.walk(p):
                    sub_files += sum(1 for f in files if f.lower().endswith((".mp4", ".mkv", ".avi", ".wmv", ".ts", ".mov", ".flv", ".rmvb")))
    print(f"lib {lid} {name}: {len(rows)} rows | seps {seps} | in-root {inroot} | disk subdirs {subs} | disk sub videos {sub_files}")

conn.close()
