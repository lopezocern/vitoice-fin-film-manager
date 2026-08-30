"""AI tagging service — OpenAI-compatible API.

Works with any OpenAI-compatible provider (OpenAI, DeepSeek, Kimi, etc.)
— just configure the base URL, API token, and model name in settings.

Config resolution order (highest priority first):
1. Explicit overrides passed into call_ai_api() (used by the "test connection"
   endpoint so it can validate exactly what the user typed).
2. Database `settings` table (what the user saved in the UI).
3. Environment-based app.config.settings defaults.
"""
import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select

from app.config import settings
from app.services.proxy import get_proxy_url
from app.database import async_session
from app.models.media import Media
from app.models.setting import Setting
from app.models.tag import Tag, TagType, VideoTag
from app.models.enums import MediaType


class AIConfigError(Exception):
    """Raised when AI configuration is incomplete (e.g. missing API key)."""


@dataclass
class AIConfig:
    base_url: str
    api_key: str
    model: str


def resolve_ai_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    db_rows: dict[str, str] | None = None,
) -> AIConfig:
    """Merge overrides -> DB settings -> env defaults into a normalized AIConfig.

    `db_rows` is an optional {key: value} map already read from the settings
    table; when omitted, only overrides and env defaults are considered.
    """
    db_rows = db_rows or {}

    key = (api_key if api_key is not None else db_rows.get("ai_api_key"))
    if not key:
        key = settings.ai_api_key
    key = (key or "").strip()

    base = base_url if base_url is not None else db_rows.get("ai_base_url")
    base = (base or "").strip()
    if not base:
        base = settings.ai_api_base or "https://api.openai.com/v1"
    base = base.rstrip("/")

    mdl = model if model is not None else db_rows.get("ai_model")
    mdl = (mdl or "").strip()
    if not mdl:
        mdl = settings.ai_model or "gpt-4o-mini"

    return AIConfig(base_url=base, api_key=key, model=mdl)


async def _load_ai_config_from_db() -> AIConfig:
    """Read AI settings from the database and resolve into an AIConfig."""
    keys = ["ai_base_url", "ai_api_key", "ai_model"]
    async with async_session() as session:
        result = await session.execute(select(Setting).where(Setting.key.in_(keys)))
        rows = {s.key: (s.value or "") for s in result.scalars().all()}
    return resolve_ai_config(db_rows=rows)


def _build_request(cfg: AIConfig, prompt: str) -> tuple[str, dict, dict]:
    """Return (url, headers, json_payload) for an OpenAI-compatible endpoint."""
    base = cfg.base_url
    if base.endswith("/chat/completions"):
        url = base
    else:
        url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1000,
    }
    return url, headers, payload


async def _chat_completion(cfg: AIConfig, prompt: str) -> str:
    """Perform one chat completion. Raises on any error (for the test path)."""
    if not cfg.api_key:
        raise AIConfigError("未配置 AI API Token（请在设置 → AI 中填写并保存）")

    url, headers, payload = _build_request(cfg, prompt)

    # 60s timeout: AI providers can be slow, especially for complex prompts
    async with httpx.AsyncClient(timeout=60, proxy=await get_proxy_url()) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]

# AI prompt template — structured output for tag extraction
TAG_PROMPT = """你是一个视频标签分析助手。根据以下视频信息，生成合适的标签。

视频标题: {title}
文件名: {filename}
时长: {duration}秒
分辨率: {width}x{height}

请返回 JSON 格式的标签建议，包含以下字段:
{{
  "tags": [
    {{
      "name": "标签名",
      "type": "actor|genre|theme|custom|collection",
      "confidence": 0.0-1.0
    }}
  ]
}}

注意:
- 标签名应简洁准确
- confidence 表示你对这个标签的把握程度
- 如果信息不足以判断，返回空数组
- 只返回 JSON，不要其他文字"""


async def call_ai_api(
    prompt: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> str | None:
    """Call the configured AI provider.

    When no overrides are supplied, configuration is loaded from the database
    settings table (falling back to env defaults). Returns the text response,
    or None on any failure (used by the tagging pipeline, which is fault
    tolerant). For error details, use `call_ai_api_checked`.
    """
    try:
        if base_url is None and api_key is None and model is None:
            cfg = await _load_ai_config_from_db()
        else:
            cfg = resolve_ai_config(base_url=base_url, api_key=api_key, model=model)
        return await _chat_completion(cfg, prompt)
    except (AIConfigError, httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        return None


async def call_ai_api_checked(
    prompt: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[bool, str, str | None]:
    """Like call_ai_api but returns (ok, message, text) with real error detail.

    Used by the "test connection" endpoint so the UI can show why it failed.
    """
    try:
        cfg = resolve_ai_config(base_url=base_url, api_key=api_key, model=model)
    except Exception as exc:  # noqa: BLE001
        return False, f"配置解析失败：{exc}", None

    try:
        text = await _chat_completion(cfg, prompt)
    except AIConfigError as exc:
        return False, str(exc), None
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        detail = ""
        try:
            body = exc.response.json()
            detail = body.get("error", {}).get("message") or body.get("message") or ""
        except Exception:  # noqa: BLE001
            detail = (exc.response.text or "")[:200]
        hint = {
            401: "API Token 无效或未授权",
            403: "无权限（检查 Token 或账户额度）",
            404: f"接口地址不存在（检查 API 地址：{cfg.base_url}）",
            429: "请求过于频繁或额度不足",
        }.get(code, f"HTTP {code}")
        msg = f"{hint}" + (f"：{detail}" if detail else "")
        return False, f"AI 调用失败（{msg}）", None
    except httpx.TimeoutException:
        return False, f"连接超时（检查网络或 API 地址：{cfg.base_url}）", None
    except httpx.HTTPError as exc:
        return False, f"网络错误：{exc}（API 地址：{cfg.base_url}）", None
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return False, f"响应解析失败（可能非兼容接口）：{exc}", None

    return True, f"连接成功（model={cfg.model}）", text


async def tag_media_with_ai(media_id: int) -> list[dict]:
    """Generate AI tags for a single media file.

    Returns list of {name, type, confidence} dicts.
    Tags are saved to VideoTag with source="ai" and is_verified=False
    (pending user review).

    Raises AIConfigError when no key is configured, and httpx errors on
    provider/network failures — so the caller (the API endpoint) can return
    a meaningful HTTP status to the user.
    """
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            return []

        # Build prompt
        prompt = TAG_PROMPT.format(
            title=media.title,
            filename=media.file_name,
            duration=int(media.duration or 0),
            width=media.width or 0,
            height=media.height or 0,
        )

    # Call AI — use _load_ai_config_from_db + _chat_completion directly so
    # config/network errors propagate to the caller (unlike call_ai_api
    # which swallows them and returns None).
    cfg = await _load_ai_config_from_db()
    if not cfg.api_key:
        raise AIConfigError("未配置 AI API Token（请在设置 → AI 中填写并保存）")

    response_text = await _chat_completion(cfg, prompt)
    if not response_text:
        return []

    # Parse JSON response
    try:
        # Strip markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        suggested_tags = data.get("tags", [])
    except (json.JSONDecodeError, KeyError):
        return []

    # Apply tags (create if needed, with source="ai", is_verified=False)
    applied = []
    async with async_session() as session:
        # Load all tag types for mapping
        result = await session.execute(select(TagType))
        tag_types = {tt.name: tt.id for tt in result.scalars().all()}

        for tag_info in suggested_tags:
            tag_name = tag_info.get("name", "").strip()
            tag_type_name = tag_info.get("type", "custom")
            confidence = float(tag_info.get("confidence", 0.5))

            if not tag_name:
                continue

            type_id = tag_types.get(tag_type_name, tag_types.get("custom"))

            # Find or create tag
            result = await session.execute(
                select(Tag).where(Tag.name == tag_name, Tag.tag_type_id == type_id)
            )
            tag = result.scalar_one_or_none()

            if not tag:
                tag = Tag(name=tag_name, tag_type_id=type_id)
                session.add(tag)
                await session.flush()

            # Check if VideoTag already exists
            result = await session.execute(
                select(VideoTag).where(
                    VideoTag.media_id == media_id,
                    VideoTag.tag_id == tag.id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                continue

            # Create VideoTag with AI source
            video_tag = VideoTag(
                media_id=media_id,
                tag_id=tag.id,
                source="ai",
                confidence=confidence,
                is_verified=False,  # Pending user review
            )
            session.add(video_tag)
            applied.append({
                "name": tag_name,
                "type": tag_type_name,
                "confidence": confidence,
            })

        await session.commit()

    return applied


async def tag_media_batch_with_ai(
    library_id: int | None = None,
    task_id: int | None = None,
    unverified_only: bool = True,
) -> int:
    """AI-tag multiple media files.

    Called by TaskManager as a task worker.
    """
    from app.tasks.manager import task_manager

    tagged_count = 0

    async with async_session() as session:
        query = select(Media.id, Media.title, Media.file_name).where(
            Media.media_type != MediaType.NETWORK
        )
        if library_id is not None:
            query = query.where(Media.library_id == library_id)

        result = await session.execute(query)
        rows = result.fetchall()

    total = len(rows)
    for i, (media_id, title, file_name) in enumerate(rows):
        # Surface the media being analyzed so the task drawer can show
        # "正在分析：《标题》" instead of a bare progress counter.
        if task_id:
            await task_manager.update_progress(
                task_id, current=i + 1, total=total,
                subtitle=title or file_name or f"媒体 #{media_id}",
            )
        tags = await tag_media_with_ai(media_id)
        if tags:
            tagged_count += 1

    return tagged_count


async def suggest_tags_for_media(media_id: int) -> list[str]:
    """Return AI-suggested tag names for a media item without persisting them.

    Used by the GET /tags/suggest endpoint. Returns an empty list when no AI
    key is configured or the provider returns nothing. Does NOT write VideoTag
    rows — it is purely advisory.
    """
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            return []

        prompt = TAG_PROMPT.format(
            title=media.title,
            filename=media.file_name,
            duration=int(media.duration or 0),
            width=media.width or 0,
            height=media.height or 0,
        )

    response_text = await call_ai_api(prompt)
    if not response_text:
        return []

    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        suggestions = data.get("tags", [])
        return [str(t.get("name", "")).strip() for t in suggestions if t.get("name")]
    except (json.JSONDecodeError, KeyError, AttributeError):
        return []


# AI prompt template — clean title + year extraction for rescraping.
# Used when the regex filename parser fails to match on TMDB: the AI analyzes
# the raw filename (with all its quality/codec/group noise) and suggests a
# clean, searchable title + release year for a second TMDB attempt.
RESCRAPE_PROMPT = """你是一个视频文件名分析助手。请分析以下视频文件名和已有元数据，推断出最可能的电影或剧集的正式标题和发行年份，用于在 TMDB（The Movie Database）中搜索。

文件名: {filename}
当前标题: {title}
当前年份: {year}

请返回 JSON 格式：
{{
  "title": "清理后的正式标题（去除画质/编码/发行组/季集标记等噪声，保留真实作品名；中文文件名优先返回英文标题以便 TMDB 搜索）",
  "year": 2024
}}

注意:
- 标题应为作品的正式名称，不要包含 1080p/x264/BluRay 等技术标记
- 年份为 4 位数字（1900-2099），如无法确定则为 null
- 只返回 JSON，不要其他文字"""


async def suggest_rescrape_query(media_id: int) -> tuple[str | None, int | None]:
    """Ask the AI to analyze a media filename and suggest a clean title + year.

    Used by the AI-rescrape endpoint as a fallback when the regular regex
    filename parser fails to match on TMDB. Loads the configured AI provider
    from the database and calls it directly (errors propagate so the endpoint
    can return a meaningful HTTP status).

    Returns ``(title, year)`` — title is None when the AI response cannot be
    parsed. Raises ``AIConfigError`` when no AI key is configured, and
    ``httpx`` errors on provider/network failures.
    """
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            raise AIConfigError("媒体不存在")

        prompt = RESCRAPE_PROMPT.format(
            filename=media.file_name or media.title or "",
            title=media.title or "",
            year=media.year or "",
        )

    # Use the DB-loaded config + checked completion so config/network errors
    # propagate to the endpoint (unlike call_ai_api which swallows them).
    cfg = await _load_ai_config_from_db()
    if not cfg.api_key:
        raise AIConfigError("未配置 AI API Token（请在设置 → AI 中填写并保存）")

    response_text = await _chat_completion(cfg, prompt)

    try:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        title = (data.get("title") or "").strip() or None
        year_raw = data.get("year")
        year = int(year_raw) if year_raw and str(year_raw).isdigit() else None
        return title, year
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, None