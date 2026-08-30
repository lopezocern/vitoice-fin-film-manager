"""Tooling diagnostic routes — check availability of external binaries."""
import os
import re
import shutil

from fastapi import APIRouter, HTTPException, Query

from app.config import settings

router = APIRouter(prefix="/tools", tags=["tools"])

# Reasonable limits for the custom path parameter
_MAX_PATH_LEN = 1024
# Reject control chars, null bytes, and shell metacharacters that could be
# used for injection if the path were ever passed to a subprocess.
_PATH_DENY_RE = re.compile(r"[\x00-\x1f<>|`$]")


def _tool_available(path: str) -> bool:
    """Check whether an external tool is runnable.

    ``path`` may be a bare command (resolved via PATH) or an absolute path.
    """
    if os.path.isabs(path):
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which(path) is not None


def _validate_tool_path(path: str) -> str:
    """Validate a user-supplied tool path to prevent abuse.

    - Rejects null bytes and shell metacharacters
    - Enforces a maximum length
    - For relative paths, ensures only a simple command name (no separators)
    """
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="路径不能为空")
    path = path.strip()
    if len(path) > _MAX_PATH_LEN:
        raise HTTPException(status_code=400, detail="路径过长")
    if _PATH_DENY_RE.search(path):
        raise HTTPException(status_code=400, detail="路径包含非法字符")
    # Relative paths must be simple command names (no path separators)
    if not os.path.isabs(path) and ("/" in path or "\\" in path):
        raise HTTPException(status_code=400, detail="相对路径不能包含路径分隔符")
    return path


@router.get("/check")
async def check_tools(
    tool: str | None = Query(None),
    path: str | None = Query(None),
) -> dict:
    """Report whether ffmpeg / ffprobe / yt-dlp are available.

    When ``tool`` and ``path`` are provided, checks the specified binary at
    the given location instead of using the global config value (M9 fix).
    The frontend uses this to validate user-entered custom binary paths.
    """
    if tool and path:
        safe_path = _validate_tool_path(path)
        return {"tool": tool, "path": safe_path, "available": _tool_available(safe_path)}

    return {
        "ffmpeg": _tool_available(settings.ffmpeg_path),
        "ffprobe": _tool_available(settings.ffprobe_path),
        "ytdlp": _tool_available(settings.ytdlp_path),
    }
