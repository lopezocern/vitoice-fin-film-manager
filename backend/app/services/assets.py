"""Asset file cleanup helpers — thumbnail/poster removal with path safety."""
from pathlib import Path


def cleanup_asset_files(media) -> None:
    """Delete thumbnail and poster files from disk (best-effort).

    Security: only files inside the managed poster/thumbnail directories are
    ever deleted — a poisoned poster_path/thumbnail_path pointing at an
    arbitrary file is ignored instead of unlinked.
    """
    from app.config import settings

    asset_roots = (
        settings.poster_dir.resolve(),
        settings.thumbnail_dir.resolve(),
    )
    for asset_path in [media.thumbnail_path, media.poster_path]:
        if not asset_path:
            continue
        try:
            p = Path(asset_path).resolve()
        except (OSError, RuntimeError):
            continue
        if not any(p == root or root in p.parents for root in asset_roots):
            continue
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass