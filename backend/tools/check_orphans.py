"""Scan a vitoice SQLite database for orphaned rows (dangling FK references).

Why this exists
---------------
`PRAGMA foreign_keys` has historically been OFF in this project (see
`app/database.py`). With the pragma off, SQLite never enforces `ON DELETE`
actions, so rows referencing a deleted parent survive as orphans. Before
turning the pragma ON we must know how much dirty data has accumulated —
otherwise deletions will start failing (or cascade unexpectedly) at runtime.

The scan is **read-only**: it opens the DB in immutable mode and never writes.

Usage
-----
    python backend/tools/check_orphans.py                 # default data root
    python backend/tools/check_orphans.py <path-to.db>    # read-only scan
    python backend/tools/check_orphans.py <path-to.db> --fix

`--fix` deletes orphaned child rows (segments, urls, video_tags, tasks, ...)
and nulls out dangling FKs on core rows (`media`). It never deletes `media`.

Exit code 0 = clean, 1 = orphans found.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Tables that SQLite maintains itself; skip them in the scan.
_SKIP_TABLES = {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4", "alembic_version"}


def _default_db_path() -> Path:
    """Resolve the production DB the same way the app does."""
    import os

    override = os.environ.get("VITOICE_DATA_ROOT")
    if override:
        return Path(override) / "vitoice.db"
    pointer = Path.home() / ".vitoice" / "data-root.json"
    if pointer.is_file():
        try:
            import json

            data = json.loads(pointer.read_text(encoding="utf-8"))
            root = data.get("data_root") or data.get("path")
            if root:
                return Path(root) / "vitoice.db"
        except Exception:  # noqa: BLE001 - fall back to the default location
            pass
    return Path.home() / ".vitoice" / "vitoice.db"


def find_orphans(db_path: Path) -> tuple[list[dict], int]:
    """Return (findings, total_orphan_rows). Read-only."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    findings: list[dict] = []
    total = 0
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            if r[0] not in _SKIP_TABLES
        ]
        for table in tables:
            for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
                child_col = fk["from"]
                parent_table = fk["table"]
                parent_col = fk["to"] or "rowid"
                if parent_table in _SKIP_TABLES:
                    continue
                sql = (
                    f"SELECT COUNT(*) AS c FROM {table} AS c "
                    f"WHERE c.{child_col} IS NOT NULL AND NOT EXISTS ("
                    f"  SELECT 1 FROM {parent_table} AS p "
                    f"  WHERE p.{parent_col} = c.{child_col}"
                    f")"
                )
                try:
                    count = conn.execute(sql).fetchone()["c"]
                except sqlite3.Error as exc:  # malformed legacy schema
                    findings.append(
                        {
                            "table": table,
                            "column": child_col,
                            "parent": parent_table,
                            "count": None,
                            "error": str(exc),
                        }
                    )
                    continue
                if count:
                    total += count
                    findings.append(
                        {
                            "table": table,
                            "column": child_col,
                            "parent": parent_table,
                            "count": count,
                            "error": None,
                        }
                    )
    finally:
        conn.close()
    return findings, total


# Tables whose rows are the user's own data — never auto-deleted by --fix.
# An orphan here is repaired by nulling the dangling FK instead.
_PROTECTED_TABLES = {"media"}


def fix_orphans(db_path: Path) -> int:
    """Delete orphaned child rows (and null out dangling FKs on `media`).

    Returns the number of affected rows. Always run the read-only scan first.
    """
    conn = sqlite3.connect(db_path)
    fixed = 0
    try:
        conn.row_factory = sqlite3.Row
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            if r[0] not in _SKIP_TABLES
        ]
        for table in tables:
            for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
                col, parent = fk["from"], fk["table"]
                parent_col = fk["to"] or "rowid"
                if parent in _SKIP_TABLES:
                    continue
                where = (
                    f"{col} IS NOT NULL AND NOT EXISTS ("
                    f"SELECT 1 FROM {parent} AS p WHERE p.{parent_col} = {table}.{col})"
                )
                if table in _PROTECTED_TABLES:
                    cur = conn.execute(f"UPDATE {table} SET {col} = NULL WHERE {where}")
                else:
                    cur = conn.execute(f"DELETE FROM {table} WHERE {where}")
                if cur.rowcount:
                    action = "置 NULL" if table in _PROTECTED_TABLES else "删除"
                    print(f"  {action} {cur.rowcount} 行: {table}.{col} -> {parent}")
                    fixed += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return fixed


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_fix = "--fix" in sys.argv[1:]
    db_path = Path(args[0]) if args else _default_db_path()
    if not db_path.is_file():
        print(f"数据库不存在: {db_path}")
        return 2

    if do_fix:
        print(f"修复(写): {db_path}")
        print("-" * 68)
        n = fix_orphans(db_path)
        print("-" * 68)
        print(f"已处理 {n} 行。")
        # Re-scan to confirm.
        _, remaining = find_orphans(db_path)
        print("复查: " + ("OK 无孤儿行" if remaining == 0 else f"仍剩 {remaining} 行"))
        return 0 if remaining == 0 else 1

    print(f"扫描(只读): {db_path}")
    print("-" * 68)
    findings, total = find_orphans(db_path)

    if not findings:
        print("OK: 未发现孤儿行。可以安全启用 PRAGMA foreign_keys=ON。")
        return 0

    print(f"{'子表':<22}{'外键列':<22}{'父表':<20}{'孤儿行数':>10}")
    print("-" * 68)
    for f in sorted(findings, key=lambda x: -(x["count"] or 0)):
        if f["error"]:
            print(f"{f['table']:<22}{f['column']:<22}{f['parent']:<20}{'ERR':>10}")
            print(f"    -> {f['error']}")
        else:
            print(
                f"{f['table']:<22}{f['column']:<22}{f['parent']:<20}{f['count']:>10}"
            )
    print("-" * 68)
    print(f"孤儿行合计: {total}")
    print("启用 foreign_keys=ON 前需先清理（删除或置 NULL）。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
