"""临时诊断：库 root_path 与 file_path 分隔符对比 + dir 前缀匹配数。"""
import os
import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/vitoice_dev.db")
rows = conn.execute("SELECT id, name, root_path FROM media_libraries").fetchall()
for i, n, r in rows:
    print(f"lib {i}: {n} | root_path = {r!r}")

print()
for i, n, r in rows:
    files = conn.execute(
        "SELECT file_path FROM media WHERE library_id=? AND is_deleted=0 LIMIT 2", (i,)
    ).fetchall()
    for (fp,) in files:
        print(f"lib {i} sample: {fp!r}")

    sub = None
    if r and os.path.isdir(r):
        for d in sorted(os.listdir(r)):
            if os.path.isdir(os.path.join(r, d)):
                sub = d
                break
    if sub:
        prefix = str(Path(r) / sub).rstrip("/\\") + os.sep
        cnt = conn.execute(
            "SELECT COUNT(*) FROM media WHERE library_id=? AND file_path LIKE ?",
            (i, prefix + "%"),
        ).fetchone()[0]
        fwd = prefix.replace(os.sep, "/")
        cnt2 = conn.execute(
            "SELECT COUNT(*) FROM media WHERE library_id=? AND file_path LIKE ?",
            (i, fwd + "%"),
        ).fetchone()[0]
        print(f"  subdir {sub!r}: prefix={prefix!r}")
        print(f"    反斜杠前缀匹配 {cnt} 条 | 正斜杠前缀匹配 {cnt2} 条")
    print()
conn.close()
