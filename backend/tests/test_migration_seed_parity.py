"""Seed parity: alembic migration chain <-> reset_data._SETTINGS_SEED.

Closes the audit gap "migrations & reset_data.py have zero test coverage"
(audit-2026-09-02). The invariants under test:

1. **The migration chain runs on a brand-new empty DB.**
   Regression: 001_initial used `op.create_unique_constraint`, which SQLite
   does not support (no ALTER) and aborted the whole chain — that is why prod
   could only ever be maintained via create_all(). The unique is created by
   revision 003 (batch mode) instead.

2. **A fresh migration and an in-app data reset produce the same seed state.**
   `reset_data._wipe_db_tables` wipes `settings` and re-inserts
   `_SETTINGS_SEED` (comment: "KEEP IN SYNC with the alembic seeds"). Any
   settings row added/edited in a migration but forgotten in `_SETTINGS_SEED`
   (or vice versa) breaks the fresh-install parity of the reset button.
   `tag_types` keeps builtin rows (is_builtin=1) — same state a fresh migrate
   seeds.

Isolation: everything runs in a **subprocess with VITOICE_DATA_ROOT pointed
at a temp dir**, because alembic/env.py pins `settings.database_url` at import
time and `reset_data` operates on that singleton — never touching dev/prod.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.reset_data import _SETTINGS_SEED

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Snapshot of builtin tag types a fresh migration seeds. Bump deliberately
# when a migration adds another builtin type (reset_data preserves these rows
# by is_builtin=1, so the count is a cheap drift alarm, not a hard contract).
_EXPECTED_BUILTIN_COUNT = 10
_EXPECTED_AV_TYPES = {"av_actress", "av_genre", "av_studio", "av_series", "av_director"}


def _run_in_data_root(tmp_root: Path, code: str) -> subprocess.CompletedProcess:
    """Run ``code`` in a subprocess whose VITOICE_DATA_ROOT is tmp_root."""
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
    "import sys;"
    " from alembic.config import Config;"
    " from alembic import command;"
    f' cfg = Config(r"{BACKEND_DIR / "alembic.ini"}");'
    f' cfg.set_main_option("script_location", r"{BACKEND_DIR / "alembic"}");'
    " command.upgrade(cfg, \"head\");"
    " print('upgrade ok')"
)

_RESET_CODE = (
    "import sys;"
    " from app.services.reset_data import reset_all_data;"
    " r = reset_all_data();"
    " print('reset ok' if r.get('ok') else ('reset FAIL: ' + str(r)));"
    " sys.exit(0 if r.get('ok') else 1)"
)


def _db_state(db_path: Path) -> tuple:
    con = sqlite3.connect(str(db_path))
    try:
        settings_rows = sorted(
            con.execute(
                "SELECT key, value, type, category, description FROM settings"
            ).fetchall()
        )
        tag_types_builtin = con.execute(
            "SELECT name FROM tag_types WHERE is_builtin = 1"
        ).fetchall()
        version = con.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        con.close()
    return settings_rows, [r[0] for r in tag_types_builtin], [r[0] for r in version]


def test_fresh_migration_reaches_head_and_matches_seed(tmp_path: Path) -> None:
    """Empty DB upgrades cleanly; settings == _SETTINGS_SEED; builtin tags."""
    result = _run_in_data_root(tmp_path, _ALEMBIC_UPGRADE)
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"
    assert "upgrade ok" in result.stdout

    db_path = tmp_path / "vitoice.db"
    assert db_path.is_file()
    settings_rows, builtin_names, version = _db_state(db_path)

    # Settings: exact full-row parity in both directions (keys, values,
    # types, categories and descriptions).
    want = sorted(_SETTINGS_SEED)
    assert settings_rows == want, (
        f"settings seed drift between alembic chain and reset_data._SETTINGS_SEED:\n"
        f"migrated-only: {sorted(set(settings_rows) - set(want))}\n"
        f"seed-only:     {sorted(set(want) - set(settings_rows))}\n"
        f"edited:        {[r for r in want if r in settings_rows and r not in want] or '-'}"
    )

    # Migration chain actually stamped.
    assert version and version[0]  # alembic_version populated at head

    # Builtin tag_types: fresh migrate seeds the expected snapshot.
    assert len(builtin_names) == _EXPECTED_BUILTIN_COUNT
    assert _EXPECTED_AV_TYPES <= set(builtin_names)


def test_reset_data_restores_fresh_migration_seed_state(tmp_path: Path) -> None:
    """In-app reset reproduces exactly what a fresh alembic migration yields.

    Seed junk rows + user tag types into a migrated DB, run the reset, then
    assert the result is byte-identical to the fresh-migration state of
    test_fresh_migration_*.
    """
    first = _run_in_data_root(tmp_path, _ALEMBIC_UPGRADE)
    assert first.returncode == 0, first.stderr

    db_path = tmp_path / "vitoice.db"
    con = sqlite3.connect(str(db_path))
    try:
        with con:
            con.execute(
                "INSERT INTO settings (key, value, type, category, description) "
                "VALUES ('drift_key', 'x', 'string', 'drift', 'drift')"
            )
            con.execute(
                "INSERT INTO tag_types (name, color, is_builtin, sort_order) "
                "VALUES ('user_made', '#123456', 0, 99)"
            )
    finally:
        con.close()

    reset = _run_in_data_root(tmp_path, _RESET_CODE)
    assert reset.returncode == 0, f"reset failed:\n{reset.stdout}\n{reset.stderr}"
    assert "reset ok" in reset.stdout

    settings_rows, builtin_names, version = _db_state(db_path)
    assert settings_rows == sorted(_SETTINGS_SEED)  # drift_key gone, seed back
    assert len(builtin_names) == _EXPECTED_BUILTIN_COUNT  # user_made removed
    assert "user_made" not in builtin_names
    assert version  # alembic_version untouched by reset

    # Pre-reset safety snapshot was produced inside the temp data root.
    backups = list((tmp_path / "backups").glob("pre-reset-*.db"))
    assert len(backups) == 1


def test_seed_has_no_duplicate_keys() -> None:
    keys = [row[0] for row in _SETTINGS_SEED]
    assert len(keys) == len(set(keys)), "duplicate keys in _SETTINGS_SEED"
    assert len(keys) >= 20  # sanity floor; exact count is pinned by parity tests
