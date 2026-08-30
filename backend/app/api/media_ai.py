"""AI tag generation route — AI-powered tag suggestions for media items.

Extracted from media.py for API physical isolation.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.schemas.media import AIRescrapeResponse, AITagSuggestion
# Single source of truth for the S7 single-resource gate — reuse the one in
# media.py instead of keeping a drifting copy.
from app.api.media import _get_media_or_404  # noqa: E402

router = APIRouter(prefix="/media", tags=["media-ai"])

logger = logging.getLogger("vitoice")


@router.post("/{media_id}/ai-tags", response_model=list[AITagSuggestion])
async def generate_ai_tags(media_id: int, db: AsyncSession = Depends(get_db)):
    """Generate AI tag suggestions for a media item and persist them.

    Delegates to app.services.ai_tagger.tag_media_with_ai, which calls the
    configured OpenAI-compatible provider and writes VideoTag rows with
    source="ai", is_verified=False. Returns the list of applied suggestions
    (empty when no key is set or the model returns nothing).
    """
    await _get_media_or_404(db, media_id)

    from app.services.ai_tagger import AIConfigError, tag_media_with_ai

    try:
        applied = await tag_media_with_ai(media_id)
    except AIConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        detail = ""
        try:
            body = exc.response.json()
            detail = body.get("error", {}).get("message") or body.get("message") or ""
        except Exception:  # noqa: BLE001
            detail = (exc.response.text or "")[:200]
        hint = {
            401: "API Key 无效或未授权",
            403: "无权限（检查 Key 或账户额度）",
            404: "接口地址不存在（检查 Base URL）",
            429: "请求过于频繁或额度不足",
        }.get(code, f"HTTP {code}")
        msg = hint + (f"：{detail}" if detail else "")
        logger.warning("AI tagging failed for media %s: %s", media_id, msg)
        raise HTTPException(
            status_code=502, detail=f"AI 标签生成失败（{msg}）"
        )
    except httpx.TimeoutException:
        logger.warning("AI tagging timeout for media %s", media_id)
        raise HTTPException(
            status_code=502, detail="AI 标签生成超时（请检查网络或稍后重试）"
        )
    except Exception as exc:  # noqa: BLE001 — surface as 502 to the client
        logger.warning("AI tagging failed for media %s: %s", media_id, exc)
        raise HTTPException(
            status_code=502, detail="AI 标签生成失败，请检查 AI 配置或稍后重试"
        )

    return applied


@router.post("/{media_id}/ai-rescrape", response_model=AIRescrapeResponse)
async def ai_rescrape_media(media_id: int, db: AsyncSession = Depends(get_db)):
    """AI-assisted rescrape: retry TMDB scraping using an AI-suggested query.

    When regular TMDB scraping fails (the regex filename parser produces a
    query that doesn't match), this endpoint asks the configured AI provider
    to analyze the media's filename and existing metadata and suggest a
    clean title + year. It then retries the TMDB search with that query and,
    on a match, persists the updated metadata (title / year / overview /
    poster / tags).

    Flow:
      1. Load the media's filename and existing metadata.
      2. Ask the AI to suggest a clean title + year (requires AI config).
      3. Retry the TMDB search using the suggested query.
      4. If matched, update the media metadata.
      5. Return the outcome (success/fail + suggested + matched info).

    Only applies to TMDB-mode libraries (MOVIE / TV / CUSTOM) — AV-mode
    libraries use 番号-based JavBus scraping and are rejected.
    """
    media = await _get_media_or_404(db, media_id)

    # AV-mode libraries use JavBus (番号-based), not TMDB title search.
    lib = await db.get(MediaLibrary, media.library_id)
    scrape_mode = lib.scrape_mode if lib else ScrapeMode.MOVIE
    if scrape_mode == ScrapeMode.AV:
        raise HTTPException(
            status_code=400,
            detail="AI 重刮仅支持 TMDB（电影/剧集）模式，限制内容模式请使用番号刮削",
        )

    # --- Require TMDB configuration ---
    from app.services.scraper import (
        TMDBConfigError,
        _load_tmdb_config_from_db,
        scrape_media,
    )

    tmdb_cfg = await _load_tmdb_config_from_db()
    if not tmdb_cfg.api_key:
        raise HTTPException(
            status_code=400,
            detail="未配置 TMDB API Key（请在设置 → 刮削中填写并保存）",
        )

    # --- 1+2. Ask the AI for a clean title + year ---
    from app.services.ai_tagger import AIConfigError, suggest_rescrape_query

    try:
        suggested_title, suggested_year = await suggest_rescrape_query(media_id)
    except AIConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPStatusError as exc:
        # Extract the real error from the AI provider's response body so the
        # user sees "API Key 无效" instead of a generic "AI 调用失败".
        code = exc.response.status_code
        detail = ""
        try:
            body = exc.response.json()
            detail = body.get("error", {}).get("message") or body.get("message") or ""
        except Exception:  # noqa: BLE001
            detail = (exc.response.text or "")[:200]
        hint = {
            401: "API Key 无效或未授权",
            403: "无权限（检查 Key 或账户额度）",
            404: f"接口地址不存在（检查 Base URL）",
            429: "请求过于频繁或额度不足",
        }.get(code, f"HTTP {code}")
        msg = hint + (f"：{detail}" if detail else "")
        logger.warning("AI rescrape call failed for media %s: %s", media_id, msg)
        raise HTTPException(status_code=502, detail=f"AI 调用失败（{msg}）")
    except httpx.TimeoutException:
        logger.warning("AI rescrape timeout for media %s", media_id)
        raise HTTPException(
            status_code=502, detail="AI 调用超时（请检查网络或稍后重试）"
        )
    except httpx.HTTPError as exc:
        logger.warning("AI rescrape network error for media %s: %s", media_id, exc)
        raise HTTPException(
            status_code=502, detail="AI 调用失败，请检查 AI 配置或网络"
        )

    if not suggested_title:
        raise HTTPException(
            status_code=502,
            detail="AI 未能生成有效的搜索建议，请稍后重试或手动重命名",
        )

    # --- 3+4. Retry TMDB search with the suggested query ---
    try:
        result = await scrape_media(
            media_id,
            tmdb_cfg,
            query_override=suggested_title,
            year_override=suggested_year,
        )
    except TMDBConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502, detail="TMDB 请求失败，请检查网络或 API 配置"
        )

    # scrape_media commits in its own session; commit the current transaction
    # so any stale state is flushed and subsequent reads see the new data.
    await db.commit()

    return AIRescrapeResponse(
        success=result.matched,
        suggested_title=suggested_title,
        suggested_year=suggested_year,
        matched_title=result.title if result.matched else None,
        matched_year=result.year if result.matched else None,
        message=result.message,
    )
