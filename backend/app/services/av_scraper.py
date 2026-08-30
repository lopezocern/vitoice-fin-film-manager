"""AV (Adult Video) scraping service — multi-source metadata fetcher.

Primary source: JavBus (https://www.javbus.com)
Fallback sources: JavDB (https://javdb.com), JavLibrary (https://www.javlibrary.com),
3xplanet (https://3xplanet.com)

Scrape order: JavBus → JavDB → JavLibrary → 3xplanet
Poster download: source cover URL → DMM constructed URL (final fallback)

This module handles libraries with ``ScrapeMode.AV``. It parses the Japanese
AV番号 (e.g. ``DASS-699-C`` → ``DASS-699``) from the filename, queries the
sources for metadata (title, actresses, studio, genres, release date, cover),
and returns a ``ScrapeResult`` compatible with the TMDB scraper flow.

The scraper is fault tolerant: network errors return ``ScrapeResult(matched=False)``
rather than raising, so batch scraping continues with the next item.
"""
import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.proxy import get_proxy_url

logger = logging.getLogger("vitoice.av_scraper")

# ---- Source base URLs ----
_JAVBUS_BASE = "https://www.javbus.com"
_JAVDB_BASE = "https://javdb.com"
_JAVLIB_BASE = "https://www.javlibrary.com"

# Browser-like User-Agent to avoid being blocked by basic bot detection.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def parse_av_fancode(filename: str) -> str | None:
    """Extract the AV番号 from a filename.

    Handles common naming patterns:
        ``DASS-699-C 百永纱里奈.mp4`` → ``DASS-699``
        ``ROYD-262-C.mp4``            → ``ROYD-262``
        ``SDMUA-012 百永さりな.mp4``    → ``SDMUA-012``
        ``OFES-003.mp4``              → ``OFES-003``
        ``390JAC-107仓木诗织.mp4``     → ``390JAC-107``  (数字前缀番号)
        ``300MIUM-777.mp4``           → ``300MIUM-777`` (数字前缀番号)
        ``MKBD-S03.mp4``              → ``MKBD-S03``    (数字部分带字母前缀)
        ``Tokyo-Hot-n0476.mp4``       → ``N0476``       (Tokyo-Hot 系列)
        ``FC2-PPV-4903567.mp4``       → ``FC2-PPV-4903567``
        ``030315-819 Caribbean ...``   → ``030315-819`` (Caribbean 日期号)

    Returns the uppercased ``PREFIX-NUMBER`` string, or ``None`` if no番号
    pattern is found.
    """
    stem = Path(filename).stem
    # These families do not fit the regular maker-number shape. Match them
    # before the generic expression so ``Tokyo-Hot-n0476`` is not mistaken
    # for ``HOT-N0476`` and ``FC2-PPV-...`` is not truncated to ``FC-2``.
    tokyo_hot = re.search(r"(?i)(?:tokyo[-_ ]?hot[-_ ]*)?(n\d{4,6})(?!\d)", stem)
    if tokyo_hot and re.search(r"(?i)tokyo[-_ ]?hot", stem):
        return tokyo_hot.group(1).upper()

    fc2 = re.search(r"(?i)(?<![A-Za-z0-9])FC2[-_ ]?PPV[-_ ]?(\d{5,8})(?!\d)", stem)
    if fc2:
        return f"FC2-PPV-{fc2.group(1)}"

    # Caribbeancom uses a numeric release date followed by an item number
    # (for example 030315-819). It has no alphabetic maker prefix, so handle
    # it before the generic AV pattern.
    caribbean = re.search(r"(?<!\d)(\d{6})[-_ ](\d{3,4})(?!\d)", stem)
    if caribbean:
        return f"{caribbean.group(1)}-{caribbean.group(2)}"

    # 番号支持两种形态: 字母开头 (DASS-699) 与 数字前缀 (390JAC-107 / 300MIUM-777)。
    # 数字前缀为可选组 (\d{2,4}); 番号后可紧跟中文标题/女优名, 因此不要求结尾边界。
    # 数字部分允许一个可选前导字母 ([A-Za-z]?), 以兼容 MKBD-S03 这类带 S 的番号。
    m = re.match(r"^(\d{2,4})?([A-Za-z]{2,6})[-_]?([A-Za-z]?\d{2,5})", stem)
    if not m:
        # Try finding anywhere in the string as fallback.
        # 不用 \b: Python 的 \w 默认含中文, 番号后紧跟中文时 \b 会被阻断。
        m = re.search(r"(?<![A-Za-z0-9])(\d{2,4})?([A-Za-z]{2,6})[-_]?([A-Za-z]?\d{2,5})", stem)
    if not m:
        return None
    num_prefix = m.group(1) or ""
    prefix = m.group(2).upper()
    number = m.group(3)
    return f"{num_prefix}{prefix}-{number}"


# =====================================================================
# Source 2: JavDB (https://javdb.com)
# =====================================================================

async def _fetch_javdb_page(
    client: httpx.AsyncClient, fancode: str, base_url: str | None = None
) -> str | None:
    """Search JavDB by fancode and return the detail page HTML.

    JavDB search returns a list of results; we match by fancode and fetch
    the detail page. Returns None if not found or blocked.

    ``base_url`` overrides the default site root (mirror / proxy support);
    falls back to the built-in ``_JAVDB_BASE`` constant when not provided.
    """
    base = (base_url or _JAVDB_BASE).rstrip("/")
    search_url = f"{base}/search?q={fancode}"
    try:
        resp = await client.get(
            search_url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": base,
            },
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        search_html = resp.text
    except httpx.HTTPError as exc:
        logger.warning("JavDB search failed for %s: %s", fancode, exc)
        return None

    # Parse search results to find matching detail page URL
    soup = BeautifulSoup(search_html, "html.parser")
    # Each search result is a .box or .grid-item with a link containing the fancode
    detail_url = None
    for link in soup.select(".box a, .grid-item a, .movie-list a"):
        href = link.get("href", "")
        text = link.get_text(strip=True)
        # Match if the fancode appears in the link text or title
        if fancode.upper() in text.upper() or fancode.upper() in href.upper():
            if href.startswith("/"):
                detail_url = base + href
            elif href.startswith("http"):
                detail_url = href
            break

    # Fallback: try direct URL pattern /v/{fancode}
    if not detail_url:
        # Some JavDB detail pages use /v/ prefix, but IDs are not always the fancode
        # Try the first search result if available
        first_link = soup.select_one(".box a[href*='/v/'], a[href*='/v/']")
        if first_link:
            href = first_link.get("href", "")
            if href.startswith("/"):
                detail_url = base + href
            elif href.startswith("http"):
                detail_url = href

    if not detail_url:
        return None

    # Fetch detail page
    try:
        resp = await client.get(
            detail_url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": search_url,
            },
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        logger.warning("JavDB detail fetch failed for %s: %s", fancode, exc)
        return None


def _parse_javdb_html(html: str, fancode: str, base_url: str | None = None) -> dict | None:
    """Parse a JavDB detail page into a metadata dict."""
    base = (base_url or _JAVDB_BASE).rstrip("/")
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # --- Title ---
    title_tag = soup.select_one("h2 .current-title, h2 strong")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        result["title"] = re.sub(r"^\s*[A-Za-z]+-\d+\s*", "", raw).strip()

    # --- Cover ---
    cover_img = soup.select_one(".video-cover img, img.video-cover, .column-video-cover img")
    if cover_img:
        src = cover_img.get("src") or cover_img.get("data-src") or cover_img.get("data-srcset")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = base + src
            result["cover_url"] = src

    # --- Info panel ---
    panel = soup.select_one(".movie-panel-info, .panel-block")
    if panel:
        for row in panel.select(".panel-block, .info-item"):
            label_tag = row.select_one("strong, .header")
            if not label_tag:
                continue
            label = label_tag.get_text(strip=True).rstrip(":：")
            links = row.select("a")
            value_text = row.get_text(separator=" ", strip=True)

            if label in ("日期", "Date", "發行日期"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", value_text)
                if m:
                    result["release_date"] = m.group(1)
            elif label in ("時長", "Runtime", "Duration"):
                m = re.search(r"(\d+)\s*分", value_text)
                if m:
                    result["runtime_minutes"] = int(m.group(1))
            elif label in ("導演", "Director"):
                if links:
                    result["director"] = links[0].get_text(strip=True)
            elif label in ("片商", "Studio", "Maker", "製作商"):
                if links:
                    result["studio"] = links[0].get_text(strip=True)
            elif label in ("發行", "Label", "Publisher", "發行商"):
                if links:
                    result["label"] = links[0].get_text(strip=True)
            elif label in ("系列", "Series"):
                if links:
                    result["series"] = links[0].get_text(strip=True)
            elif label in ("類別", "Genre", "Genres", "類型"):
                genres = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
                if genres:
                    result["genres"] = genres
            elif label in ("演員", "Actors", "Actress", "Cast"):
                actresses = []
                for a in links:
                    name = a.get_text(strip=True)
                    # Filter out male actors (marked with ♂) and empty names
                    if name and "♂" not in name:
                        actresses.append(name)
                if actresses:
                    result["actresses"] = actresses

    # Fallback: og:image for cover
    if "cover_url" not in result:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            result["cover_url"] = og["content"]

    if "title" not in result:
        result["title"] = fancode

    return result


# =====================================================================
# Source 3: JavLibrary (https://www.javlibrary.com)
# =====================================================================

async def _fetch_javlib_page(
    client: httpx.AsyncClient, fancode: str, base_url: str | None = None
) -> str | None:
    """Search JavLibrary by fancode and return the detail page HTML.

    JavLibrary may redirect directly to the detail page for unique matches,
    or return a search results list for ambiguous matches.

    ``base_url`` overrides the default site root (mirror / proxy support).
    """
    base = (base_url or _JAVLIB_BASE).rstrip("/")
    search_url = f"{base}/cn/vl_searchbyid.php?keyword={fancode}"
    try:
        resp = await client.get(
            search_url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": base,
            },
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        html = resp.text

        # Check if we got a search results page (multiple results)
        # vs. direct redirect to detail page
        soup = BeautifulSoup(html, "html.parser")

        # If there's a video detail (#rightcolumn), we're on the detail page
        if soup.select_one("#rightcolumn, #video_title"):
            return html

        # Search results: find the first result matching the fancode
        for link in soup.select(".videothumblist .title a, .list .title a, a[href*='?v=']"):
            text = link.get_text(strip=True)
            href = link.get("href", "")
            if fancode.upper() in text.upper():
                if href.startswith("/"):
                    detail_url = base + href
                else:
                    detail_url = href
                try:
                    resp2 = await client.get(
                        detail_url,
                        headers={
                            "User-Agent": _UA,
                            "Accept": "text/html,application/xhtml+xml",
                            "Referer": search_url,
                        },
                        follow_redirects=True,
                    )
                    resp2.raise_for_status()
                    return resp2.text
                except httpx.HTTPError as exc:
                    logger.warning("JavLibrary detail fetch failed: %s", exc)
                    return None

        # No match found in search results
        return None
    except httpx.HTTPError as exc:
        logger.warning("JavLibrary search failed for %s: %s", fancode, exc)
        return None


def _parse_javlib_html(html: str, fancode: str, base_url: str | None = None) -> dict | None:
    """Parse a JavLibrary detail page into a metadata dict."""
    base = (base_url or _JAVLIB_BASE).rstrip("/")
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # --- Title ---
    title_tag = soup.select_one("#video_title h3, #rightcolumn h3, .post-title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        result["title"] = re.sub(r"^\s*[A-Za-z]+-\d+\s*", "", raw).strip()

    # --- Cover ---
    cover_img = soup.select_one("#video_jacket_img, .jacket img, img.jacket")
    if cover_img:
        src = cover_img.get("src") or cover_img.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = base + src
            result["cover_url"] = src

    # --- Info panel ---
    info = soup.select_one("#video_info, #rightcolumn")
    if info:
        # Director
        for a in info.select(".director a, span.director a"):
            name = a.get_text(strip=True)
            if name:
                result["director"] = name
                break

        # Maker (Studio)
        for a in info.select(".maker a, span.maker a"):
            name = a.get_text(strip=True)
            if name:
                result["studio"] = name
                break

        # Label (Publisher)
        for a in info.select(".label a, span.label a"):
            name = a.get_text(strip=True)
            if name:
                result["label"] = name
                break

        # Release date
        date_el = info.select_one("#video_date .text, #video_date td")
        if date_el:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", date_el.get_text())
            if m:
                result["release_date"] = m.group(1)

        # Runtime
        length_el = info.select_one("#video_length .text, #video_length span")
        if length_el:
            m = re.search(r"(\d+)", length_el.get_text())
            if m:
                result["runtime_minutes"] = int(m.group(1))

        # Genres
        genres = [
            a.get_text(strip=True)
            for a in info.select(".genre a, span.genre a")
            if a.get_text(strip=True) and "/star/" not in a.get("href", "")
        ]
        if genres:
            result["genres"] = genres

        # Actresses
        actresses = [
            a.get_text(strip=True)
            for a in info.select(".star a, span.star a, .cast a")
            if a.get_text(strip=True)
        ]
        if actresses:
            result["actresses"] = actresses

    # Fallback: og:image
    if "cover_url" not in result:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            result["cover_url"] = og["content"]

    if "title" not in result:
        result["title"] = fancode

    return result


async def _fetch_javbus_page(
    client: httpx.AsyncClient, fancode: str, base_url: str | None = None
) -> str | None:
    """Fetch the JavBus HTML page for a given番号.

    Returns the HTML text, or ``None`` if the page is not found / inaccessible.

    ``base_url`` overrides the default site root (mirror / proxy support).
    """
    base = (base_url or _JAVBUS_BASE).rstrip("/")
    url = f"{base}/{fancode}"
    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": base,
            },
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        logger.warning("JavBus fetch failed for %s: %s", fancode, exc)
        return None


def _parse_javbus_html(html: str, fancode: str, base_url: str | None = None) -> dict | None:
    """Parse a JavBus HTML page into a metadata dict.

    Returns ``None`` if parsing fails. The dict contains:
        title, actresses, genres, studio, release_date, runtime, cover_url,
        fanart_url, label, series, director
    """
    base = (base_url or _JAVBUS_BASE).rstrip("/")
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # --- Title ---
    title_tag = soup.select_one("h3")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        # Clean up: remove leading番号 if present
        result["title"] = re.sub(r"^\s*[A-Za-z]+-\d+\s*", "", raw_title).strip()
    else:
        t = soup.select_one("title")
        if t:
            result["title"] = t.get_text(strip=True).split(" - ")[0].strip()

    # --- Cover image ---
    # JavBus cover is usually in a big <a> with hover image in .photothumb or
    # the main screenshot image. Try multiple selectors.
    cover_img = soup.select_one("a.bigImage img, .photothumb img, .col-md-9 .screenshot img")
    if cover_img:
        src = cover_img.get("src") or cover_img.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = base + src
            result["cover_url"] = src

    # --- Actresses: look for .star-name a (primary) or a[href*="/star/"] (fallback) ---
    # Only use .star-name a — it gives clean actress names without duplicates.
    # The a[href*='/star/'] selector also matches avatar <img> wrappers with empty text.
    actress_links = soup.select(".star-name a")
    if not actress_links:
        # Fallback: all /star/ links with non-empty text
        actress_links = [
            a for a in soup.select("a[href*='/star/']")
            if a.get_text(strip=True)
        ]
    actresses = []
    seen = set()
    for a in actress_links:
        name = a.get_text(strip=True)
        if name and name not in seen:
            seen.add(name)
            actresses.append(name)
    if actresses:
        result["actresses"] = actresses

    # --- Genres: look for .genre a (skip buttons and actress links) ---
    # JavBus sometimes nests actress links inside .genre spans, so we filter
    # out any link whose href contains '/star/' (actress page) or whose text
    # is the "多選提交" (multi-select submit) button.
    genre_links = soup.select(".genre a")
    genres = []
    for a in genre_links:
        href = a.get("href", "")
        name = a.get_text(strip=True)
        if not name or name == "多選提交":
            continue
        if "/star/" in href:
            continue  # actress link, not a genre
        genres.append(name)
    if genres:
        result["genres"] = genres

    # --- Info panel: studio, label, series, release date, runtime, director ---
    # Each info row is a <p> with <span class="header">label:</span> value
    info_section = soup.select_one(".col-md-3.info, .info, #video-info")
    if info_section:
        for p in info_section.find_all("p"):
            header = p.select_one(".header")
            if not header:
                continue
            label_text = header.get_text(strip=True).rstrip(":：")
            links = p.select("a")
            value_text = p.get_text(separator=" ", strip=True)

            if label_text in ("製作商", "Studio", "Maker"):
                if links:
                    result["studio"] = links[0].get_text(strip=True)
            elif label_text in ("發行商", "Label", "Publisher"):
                if links:
                    result["label"] = links[0].get_text(strip=True)
            elif label_text in ("系列", "Series"):
                if links:
                    result["series"] = links[0].get_text(strip=True)
            elif label_text in ("發行日期", "Release Date", "Date"):
                m_date = re.search(r"(\d{4}-\d{2}-\d{2})", value_text)
                if m_date:
                    result["release_date"] = m_date.group(1)
            elif label_text in ("長度", "Runtime", "Length", "Duration"):
                m_runtime = re.search(r"(\d+)\s*分", value_text)
                if m_runtime:
                    result["runtime_minutes"] = int(m_runtime.group(1))
                else:
                    m_runtime = re.search(r"(\d+)", value_text)
                    if m_runtime:
                        result["runtime_minutes"] = int(m_runtime.group(1))
            elif label_text in ("導演", "Director"):
                if links:
                    result["director"] = links[0].get_text(strip=True)

    # If no cover found via selectors, try og:image meta
    if "cover_url" not in result:
        og = soup.select_one('meta[property="og:image"]')
        if og:
            src = og.get("content")
            if src:
                result["cover_url"] = src

    # If title not found, use番号 as fallback
    if "title" not in result:
        result["title"] = fancode

    return result


def _build_dmm_poster_url(fancode: str) -> str:
    """Build a DMM poster URL from a fancode.

    DASS-699 -> https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/dass00699/dass00699pl.jpg
    """
    parts = fancode.split("-", 1)
    if len(parts) != 2:
        return ""
    prefix = parts[0].lower()
    number = parts[1].zfill(5)
    dmm_id = f"{prefix}{number}"
    return f"https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/{dmm_id}/{dmm_id}pl.jpg"


async def _download_av_poster(
    client: httpx.AsyncClient,
    url: str,
    media_id: int,
    fancode: str = "",
    base_url: str | None = None,
) -> str | None:
    """Download a poster image to the local poster directory. Returns path.

    Tries the JavBus cover URL first (requires browser-like Sec-Fetch headers
    to avoid 403), then falls back to a DMM poster URL constructed from the
    fancode. ``base_url`` supplies the Referer origin (source root).
    """
    referer = (base_url or _JAVBUS_BASE).rstrip("/")
    # Full browser-like headers — JavBus requires Sec-Fetch-* to serve images.
    img_headers = {
        "User-Agent": _UA,
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"{referer}/{fancode}" if fancode else referer,
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }

    settings.poster_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.poster_dir / f"{media_id}.jpg"

    # Attempt 1: JavBus cover URL
    if url:
        try:
            resp = await client.get(url, headers=img_headers, follow_redirects=True)
            resp.raise_for_status()
            await asyncio.to_thread(dest.write_bytes, resp.content)
            logger.info("AV poster downloaded from JavBus: %s (%d bytes)", url, len(resp.content))
            return str(dest)
        except httpx.HTTPError as exc:
            logger.warning("AV poster download from JavBus failed: %s", exc)

    # Attempt 2: DMM fallback
    if fancode:
        dmm_url = _build_dmm_poster_url(fancode)
        try:
            resp = await client.get(
                dmm_url,
                headers={
                    "User-Agent": _UA,
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
            await asyncio.to_thread(dest.write_bytes, resp.content)
            logger.info("AV poster downloaded from DMM: %s (%d bytes)", dmm_url, len(resp.content))
            return str(dest)
        except httpx.HTTPError as exc:
            logger.warning("AV poster download from DMM failed: %s", exc)

    return None


# =====================================================================
# Source 4: 3xplanet (https://3xplanet.com)
# URL pattern: {base}/{fancode_lowercase}/
# Page layout: <article> with h1 title + a flat sequence of <p> key: value
# rows (品番/発売日/収録時間/メーカー/ジャンル/出演者 + Starring/Studio/Tags),
# cover image is an <img> whose src contains "/cover/".
# =====================================================================


def _3xplanet_slug_candidates(fancode: str) -> list[str]:
    """Return likely 3xplanet slugs in cheapest-first lookup order."""
    slug = fancode.strip().lower().replace("_", "-")
    candidates = [slug]
    # Leaked releases commonly live below this category-prefixed slug.
    if re.fullmatch(r"\d{2,5}[a-z]{2,6}-[a-z]?\d{2,5}", slug):
        candidates.append(f"uncen-leaked-{slug}")
    return candidates


def _find_3xplanet_detail_url(search_html: str, fancode: str, base: str) -> str | None:
    """Find an exact fancode-bearing detail link in a search result page."""
    expected = {
        candidate.rstrip("/").lower()
        for candidate in _3xplanet_slug_candidates(fancode)
    }
    soup = BeautifulSoup(search_html, "html.parser")
    for link in soup.select("a[href]"):
        detail_url = urljoin(f"{base}/", link.get("href", ""))
        parsed = urlparse(detail_url)
        if parsed.netloc != urlparse(base).netloc:
            continue
        slug = parsed.path.strip("/").split("/")[-1].lower()
        if slug in expected:
            return detail_url
    return None


async def _fetch_3xplanet_page(
    client: httpx.AsyncClient, fancode: str, base_url: str | None = None
) -> str | None:
    """Fetch a 3xplanet detail page for a given番号.

    3xplanet 的详情页 slug 并非固定 ``{fancode}/``——分类前缀（如
    ``uncen-leaked-``）会让真实 URL 变成 ``uncen-leaked-{fancode}/``
    这类形态，直接按番号构造会 404。因此先尝试直接 slug，失败后用
    站内搜索定位详情页真实 URL 再抓取。

    Returns the HTML text, or ``None`` if the page is not found / inaccessible.
    """
    base = (base_url or "https://3xplanet.com").rstrip("/")
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": base,
    }

    async def _get(url: str) -> httpx.Response | None:
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            logger.warning("3xplanet fetch failed for %s: %s", url, exc)
            return None

    # Attempt 1: known direct slugs, including category-prefixed leaked pages.
    for slug in _3xplanet_slug_candidates(fancode):
        resp = await _get(f"{base}/{slug}/")
        if resp is not None:
            return resp.text

    # Attempt 2: site search locates the real detail URL (category-prefixed slug)
    resp = await _get(f"{base}/search/{fancode}")
    if resp is None:
        return None
    detail = _find_3xplanet_detail_url(resp.text, fancode, base)
    if not detail:
        logger.info("3xplanet search found no detail link for %s", fancode)
        return None
    resp = await _get(detail)
    return resp.text if resp is not None else None


def _clean_jp_en_names(val: str) -> list[str]:
    """从 'うみ (Umi), ひなた (Hinata)' 提取日文名；无日文时回退英文部分。"""
    jp = val.split("(")[0]
    names = [x.strip() for x in jp.split(",") if x.strip()]
    if names:
        return names
    en = val.split("(")[-1].rstrip(")").strip()
    return [x.strip() for x in en.split(",") if x.strip()]


def _parse_3xplanet_field(result: dict, key: str, val: str) -> None:
    """按 key 写入 3xplanet 元数据字段（兼容新旧两版布局的 key 命名）。"""
    if not val or val == "—":
        return
    if key in ("発売日", "配信開始日", "Release Date"):
        m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", val)
        if m:
            result["release_date"] = (
                f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            )
    elif key in ("収録時間", "Duration"):
        m = re.search(r"(\d+)", val)
        if m:
            result["runtime_minutes"] = int(m.group(1))
    elif key in ("メーカー", "Studio"):
        result["studio"] = val
    elif key in ("レーベル", "Label"):
        result["label"] = val
    elif key in ("ジャンル", "Genres"):
        genres = _clean_jp_en_names(val)
        if genres:
            result["genres"] = genres
    elif key in ("出演者", "Actress", "Starring"):
        names = _clean_jp_en_names(val)
        if names:
            result["actresses"] = names


def _parse_3xplanet_jsonld(soup: BeautifulSoup, result: dict) -> None:
    """从 JSON-LD Article.keywords 兜底 genres（2026 改版后部分页面无信息面板）。"""
    if result.get("genres") or result.get("actresses"):
        return
    for sc in soup.select('script[type="application/ld+json"]'):
        txt = sc.string or ""
        if '"keywords"' not in txt:
            continue
        m = re.search(r'"keywords":\s*(\[[^\]]*\])', txt)
        if not m:
            continue
        try:
            kw = json.loads(m.group(1))
        except Exception:
            kw = []
        kw = [str(k).strip() for k in kw if str(k).strip()]
        if not kw:
            continue
        if not result.get("genres"):
            result["genres"] = kw
        # 双词且两个单词均首字母大写 → 女优名候选（如 "Hirose Riona"），
        # 排除 "Nice ass"/"Small breasts" 这类小写第二词的非人名关键词。
        if not result.get("actresses"):
            candidates = [
                k for k in kw
                if re.fullmatch(r"[A-Z][a-zA-Z]+ [A-Z][a-zA-Z]+", k)
            ]
            if candidates:
                result["actresses"] = candidates
                # 从 genres 中剔除女优名，避免同一名字被重复打 av_actress + av_genre
                result["genres"] = [g for g in result.get("genres", []) if g not in candidates]
        break


def _parse_3xplanet_html(html: str, fancode: str, base_url: str | None = None) -> dict | None:
    """Parse a 3xplanet detail page into a metadata dict.

    Returns ``None`` if parsing fails. Fields follow the same convention as
    the other AV parsers: title, actresses, genres, studio, release_date
    (YYYY-MM-DD), runtime_minutes, cover_url.

    2026 改版支持三层元数据来源（优先级从高到低）：
      1. ``<dl class="xplanet-specs">`` dt/dd 面板（新版标准布局）
      2. 旧版 ``<article> p`` key:value 行（历史布局兼容）
      3. JSON-LD Article.keywords（无信息面板时兜底 genres/actresses）
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # --- Title (h1, strip the leading fancode) ---
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(strip=True)
        m = re.match(rf"^\s*{re.escape(fancode)}[\s\-_]*", title, re.IGNORECASE)
        if m:
            title = title[m.end():]
        result["title"] = title.strip()
    else:
        return None

    # --- New layout (2026): <dl class="xplanet-specs"> dt/dd pairs ---
    dl = soup.select_one("dl.xplanet-specs")
    if dl:
        current_key: str | None = None
        for el in dl.find_all(["dt", "dd"]):
            if el.name == "dt":
                current_key = el.get_text(strip=True).split("/")[0].strip()
            elif el.name == "dd" and current_key:
                _parse_3xplanet_field(result, current_key, el.get_text(" ", strip=True).strip())
                current_key = None

    # --- Legacy layout: key: value rows inside <article> ---
    if not result:
        for p in soup.select("article p"):
            txt = p.get_text(" ", strip=True)
            if ":" not in txt:
                continue
            key, _, val = txt.partition(":")
            key = key.strip()
            val = val.strip()
            if key == "品番":
                continue
            _parse_3xplanet_field(result, key, val)

    # --- JSON-LD keywords 兜底 ---
    _parse_3xplanet_jsonld(soup, result)

    # --- Cover image: any <img> whose src contains /cover/ ---
    for img in soup.select("article img"):
        src = img.get("src") or img.get("data-src") or ""
        if "/cover/" in src:
            result["cover_url"] = src
            break
    if "cover_url" not in result:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            result["cover_url"] = og["content"]

    if not result.get("title"):
        return None
    return result


# =====================================================================
# Parser registry & entry point
# =====================================================================

_AV_PARSERS: dict[str, tuple] = {
    "javbus": (_fetch_javbus_page, _parse_javbus_html),
    "javdb": (_fetch_javdb_page, _parse_javdb_html),
    "javlibrary": (_fetch_javlib_page, _parse_javlib_html),
    "3xplanet": (_fetch_3xplanet_page, _parse_3xplanet_html),
}


def _infer_av_parser(name: str, base_url: str) -> str:
    """Guess which HTML parser a configured AV source needs.

    Matches on the source name / base URL substring; mirrors usually keep
    the upstream name. Falls back to the JavBus parser.
    """
    text = f"{name} {base_url}".lower()
    if "javdb" in text:
        return "javdb"
    if "javlib" in text:
        return "javlibrary"
    if "3xplanet" in text:
        return "3xplanet"
    return "javbus"


def _av_meta_complete(meta: dict) -> bool:
    """元数据完整度评估。

    有 title 且（演员/类型/工作室任一非空）视为高质量结果，直接采用；
    否则（如 JavBus 上资料缺失的片子，信息面板只有番号/0分鐘/0000-00-00）
    视为残缺，继续尝试后续源以拿到更完整的数据。没有任何源完整时，
    回退到第一个残缺结果（至少保留了 title）。
    """
    if not meta.get("title"):
        return False
    if meta.get("actresses") or meta.get("genres") or meta.get("studio"):
        return True
    return False


async def scrape_av_media(
    media_id: int,
    file_name: str,
    sources: list["ScrapeSource"] | None = None,
    *,
    keep_custom_poster: bool = False,
) -> tuple["ScrapeResult", dict | None]:
    """Scrape a single AV media item using multi-source fallback.

    Source order: JavBus → JavDB → JavLibrary (or the configured chain from
    ``scrape_sources.av`` when provided).
    Each source is tried in order; the first successful match wins.
    Poster download always tries the source cover URL first, then DMM as fallback.
    When ``keep_custom_poster`` is True (user uploaded their own cover), the
    poster download is skipped — the existing cover is preserved.

    Returns a ``(ScrapeResult, scrape_data | None)`` tuple for consistent
    unpacking by the caller.  ``scrape_data`` is ``None`` on failure.
    Never raises for "no match" — only for hard configuration errors.
    """
    from app.services.scraper import ScrapeResult, ScrapeSource

    fancode = parse_av_fancode(file_name)
    if not fancode:
        return ScrapeResult(matched=False, message=f"无法从文件名解析番号: {file_name}"), None

    # Source definitions: (name, fetch_fn, parse_fn, base_url)
    if sources:
        source_specs: list[tuple[str, object, object, str]] = []
        for s in sources:
            if not isinstance(s, ScrapeSource) or s.kind != "html" or not s.base_url:
                continue
            parser = s.parser or _infer_av_parser(s.name, s.base_url)
            impl = _AV_PARSERS.get(parser)
            if impl:
                source_specs.append((s.name, impl[0], impl[1], s.base_url))
    else:
        source_specs = [
            ("JavBus", _fetch_javbus_page, _parse_javbus_html, _JAVBUS_BASE),
            ("JavDB", _fetch_javdb_page, _parse_javdb_html, _JAVDB_BASE),
            ("JavLibrary", _fetch_javlib_page, _parse_javlib_html, _JAVLIB_BASE),
            ("3xplanet", _fetch_3xplanet_page, _parse_3xplanet_html, "https://3xplanet.com"),
        ]

    if not source_specs:
        return ScrapeResult(matched=False, message="AV 数据源配置无效（无可用 html 源）"), None

    meta: dict | None = None
    source_name: str = ""
    source_base: str = ""
    cover_url: str | None = None
    # 残缺结果兜底：所有源都无完整数据时，回退第一个有 title 的结果
    fallback_meta: dict | None = None
    fallback_name: str = ""
    fallback_base: str = ""

    async with httpx.AsyncClient(timeout=30, proxy=await get_proxy_url()) as client:
        for name, fetch_fn, parse_fn, base in source_specs:
            try:
                html = await fetch_fn(client, fancode, base_url=base)  # type: ignore[arg-type]
                if not html:
                    logger.info("AV scrape: %s returned no page for %s", name, fancode)
                    continue

                parsed = parse_fn(html, fancode, base_url=base)  # type: ignore[arg-type]
                if not parsed:
                    logger.info("AV scrape: %s parse failed for %s", name, fancode)
                    continue

                # 数据残缺（无演员/类型/工作室）时不立即采纳——继续尝试后续源，
                # 避免 JavBus 上资料缺失的片子（仅番号/0分鐘/0000-00-00）被
                # 当作成功匹配而拿到近乎空的数据。
                if _av_meta_complete(parsed):
                    meta = parsed
                    source_name = name
                    source_base = base
                    cover_url = meta.get("cover_url")
                    logger.info("AV scrape: %s matched for %s", name, fancode)
                    break
                if fallback_meta is None:
                    fallback_meta = parsed
                    fallback_name = name
                    fallback_base = base
                    logger.info(
                        "AV scrape: %s partial result for %s (incomplete, keep as fallback)",
                        name, fancode,
                    )
            except Exception as exc:
                logger.warning("AV scrape: %s error for %s: %s", name, fancode, exc)
                continue

        if meta is None:
            if fallback_meta is not None:
                meta = fallback_meta
                source_name = fallback_name
                source_base = fallback_base
                cover_url = meta.get("cover_url")
                logger.info("AV scrape: no complete source, using %s partial for %s", source_name, fancode)
            else:
                return ScrapeResult(
                    matched=False,
                    message=f"所有源均未找到番号: {fancode}",
                ), None

        # Download cover as poster (source cover → DMM fallback)
        # 用户上传过封面时跳过下载，保留自定义封面。
        local_poster = None
        if not keep_custom_poster:
            local_poster = (
                await _download_av_poster(client, cover_url, media_id, fancode, base_url=source_base)
                if cover_url else None
            )
            if not local_poster:
                local_poster = await _download_av_poster(
                    client, "", media_id, fancode, base_url=source_base
                )

    # Build scrape_data (compatible with the detail page's ScrapeData interface)
    scrape_data: dict = {
        "fancode": fancode,
        "actresses": meta.get("actresses") or [],
        "genres": meta.get("genres") or [],
        "studio": meta.get("studio"),
        "label": meta.get("label"),
        "series": meta.get("series"),
        "director": meta.get("director"),
        "release_date": meta.get("release_date"),
        "runtime_minutes": meta.get("runtime_minutes"),
        "cover_url": cover_url,
        "source": source_name,
    }

    # Build title: 番号 + first actress if available
    title = meta.get("title") or fancode
    actresses = meta.get("actresses") or []
    if actresses:
        title = f"{fancode} {actresses[0]}"

    # Parse year from release_date（0000-00-00 视为无效）
    year: int | None = None
    release = meta.get("release_date") or ""
    if len(release) >= 4 and release[:4].isdigit():
        y = int(release[:4])
        if y > 0:
            year = y

    return ScrapeResult(
        matched=True,
        title=title,
        year=year,
        overview=None,
        poster_path=local_poster,
        genre_count=len(meta.get("genres") or []),
        message=f"ok (source: {source_name})",
    ), scrape_data
