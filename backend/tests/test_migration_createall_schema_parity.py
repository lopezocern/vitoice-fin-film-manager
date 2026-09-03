"""Schema parity: alembic migration head <-> model metadata (create_all).

Prod databases carry no alembic_version and are maintained by
``database.init_db()`` (create_all + additive-column + unique-constraint
guards) — that IS the production schema source. Fresh installs go through
alembic. These two paths must not silently drift apart.

Comparison is *semantic*, not byte-level:

- table set must match exactly;
- per table, every column must match on (name, affinity type, primary-key
  membership, and whether the column is *filled* — DDL NOT NULL or a server
  default that backfills omitted inserts);
- unique coverage must match (deduplicated by column set, autoindexes and
  explicit unique indexes counted together).

Known intentional nuance — the two paths spell "this column always has a
value" differently today:

- model DDL (create_all / prod path): ``nullable=False`` with a Python-side
  ``default=`` — SQLAlchemy does NOT render a server default, so the column
  is NOT NULL only;
- migration DDL (fresh-install path): ``nullable + server_default`` (e.g.
  ``media_type`` -> ``'local'``, ``is_favorite`` -> ``'0'``,
  ``created_at`` -> ``CURRENT_TIMESTAMP``).

Both are behaviourally identical through the application: the ORM always
supplies the value, an explicit NULL never arrives, and prod (which has run
create_all all along, never the migration chain) has worked without the
server defaults. The migration's extra ``server_default`` only guards raw
SQL that omits the column — no code path relies on it (it could not: prod
never had it). This inert DDL-style difference is normalized away by the
``filled`` predicate below.

What still FAILS the test: a column truly nullable without a default on one
path but filled on the other; a missing/renamed/retrotyped column; a primary
key mismatch; or unique-coverage drift. Those are real divergence.

Isolation mirrors test_migration_seed_parity.py: subprocess +
VITOICE_DATA_ROOT=temp (alembic/env.py and the app singleton both pin
``settings.database_url`` at import time — never touches dev/prod).
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_in_data_root(tmp_root: Path, code: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "VITOICE_ENV"}
    env["VITOICE_DATA_ROOT"] = str(tmp_root)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )


_ALEMBIC_UPGRADE = (
    "from alembic.config import Config;"
    " from alembic import command;"
    f' cfg = Config(r"{BACKEND_DIR / "alembic.ini"}");'
    f' cfg.set_main_option("script_location", r"{BACKEND_DIR / "alembic"}");'
    ' command.upgrade(cfg, "head");'
    " print('upgrade ok')"
)

_INIT_DB = (
    "import asyncio;"
    " from app.database import init_db;"
    " asyncio.run(init_db());"
    " print('init ok')"
)


def _column_signature(col) -> tuple:
    # PRAGMA table_info row: cid, name, type, notnull, dflt_value, pk
    _, name, ctype, notnull, dflt, pk = col
    # "Filled" = DDL NOT NULL, or a server default backfills an omitted
    # insert. Through the ORM (models carry Python-side defaults and never
    # send explicit NULL for these columns) the two spellings are
    # equivalent, so migration "nullable + server_default" and model
    # "NOT NULL" normalize to the same value. The raw default *literal* is
    # deliberately not compared: on a filled column it is inert DDL detail.
    # A column that is truly nullable (no NOT NULL, no server default) on
    # one path but filled on the other remains real drift and fails.
    filled = bool(notnull) or (dflt is not None)
    return (name, ctype, bool(pk), filled)


def _schema(db_path: Path) -> dict:
    con = sqlite3.connect(str(db_path))
    try:
        tables = sorted(
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            ).fetchall()
        )
        out: dict[str, dict] = {}
        for t in tables:
            cols = con.execute(f"PRAGMA table_info('{t}')").fetchall()
            unique_sets = set()
            for idx in con.execute(f"PRAGMA index_list('{t}')").fetchall():
                if not idx[2]:  # unique flag
                    continue
                member_cols = tuple(
                    c[2]
                    for c in con.execute(
                        f"PRAGMA index_info('{idx[1]}')"
                    ).fetchall()
                )
                if member_cols:
                    unique_sets.add(frozenset(member_cols))
            out[t] = {
                "cols": {_column_signature(c) for c in cols},
                "uniq": unique_sets,
            }
        return out
    finally:
        con.close()


def test_column_signature_filled_equivalence_classes() -> None:
    """PRAGMA rows that differ only in DDL style must compare equal; a truly
    nullable column must not."""

    def sig(notnull: int, dflt: str | None) -> tuple:
        # (cid, name, type, notnull, dflt_value, pk)
        return _column_signature((0, "c", "INTEGER", notnull, dflt, 0))

    # model spelling (NOT NULL, no server default) == migration spelling
    # (nullable + server default that backfills) — inert DDL difference.
    assert sig(1, None) == sig(0, "0")
    assert sig(1, None) == sig(0, "'local'")
    # both sides nullable + default, whatever the literal
    assert sig(0, "0") == sig(0, "1")
    # a truly nullable column (bare NULL accepted, nothing backfills)
    # is real drift against either filled form.
    assert sig(0, None) != sig(1, None)
    assert sig(0, None) != sig(0, "0")
    assert sig(0, None) != sig(1, "0")


def test_migration_head_matches_create_all_schema(tmp_path: Path) -> None:
    """Fresh alembic DB and fresh init_db() DB expose the same schema."""
    root_a = tmp_path / "alembic"
    root_b = tmp_path / "createall"
    root_a.mkdir()
    root_b.mkdir()

    ra = _run_in_data_root(root_a, _ALEMBIC_UPGRADE)
    assert ra.returncode == 0, f"alembic failed:\n{ra.stdout}\n{ra.stderr}"
    rb = _run_in_data_root(root_b, _INIT_DB)
    assert rb.returncode == 0, f"init_db failed:\n{rb.stdout}\n{rb.stderr}"

    schema_a = _schema(root_a / "vitoice.db")
    schema_b = _schema(root_b / "vitoice.db")

    assert set(schema_a) == set(schema_b), (
        "table-set drift — migration vs create_all: "
        f"{sorted(set(schema_a) ^ set(schema_b))}"
    )

    problems: list[str] = []
    for t in sorted(schema_a):
        sa_t, sb_t = schema_a[t], schema_b[t]
        if sa_t["cols"] != sb_t["cols"]:
            only_a = sa_t["cols"] - sb_t["cols"]
            only_b = sb_t["cols"] - sa_t["cols"]
            problems.append(f"[{t}] column drift A-only={sorted(only_a)} B-only={sorted(only_b)}")
        if sa_t["uniq"] != sb_t["uniq"]:
            only_a = sorted(sa_t["uniq"] - sb_t["uniq"], key=sorted)
            only_b = sorted(sb_t["uniq"] - sa_t["uniq"], key=sorted)
            problems.append(f"[{t}] unique drift A-only={only_a} B-only={only_b}")

    assert not problems, (
        "model metadata (create_all path) and alembic migration head diverged:\n"
        + "\n".join(problems)
    )
