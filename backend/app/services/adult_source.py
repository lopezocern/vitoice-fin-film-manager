"""Adult aggregator network source resolver (javgg-style).

Resolves a JAV fancode into playable stream URLs by walking the standard
aggregator chain:

    article page ({base}/jav/{fancode}/)
      -> pre-rendered embed iframes (#dooplay_player_content .source-box)
      -> each embed page yields a playable m3u8:
           turboplay  : plain m3u8 in HTML (no signature)
           vidhide    : signed hls2 URL inside a Dean-Edwards-packed script
           streamwish : signed hls2 URL inside a packed script (hls2 often
                        returns 403; hls3 unsigned channel is the fallback)
           dood       : no m3u8 — an IP-bound mp4 minted on demand via
                        /pass_md5 (see mint_dood_url); the embed page is stored

Signed URLs carry `e=129600` (36h) — they expire and the embed page must
be re-fetched to mint a fresh signature.

ISOLATION: this module ONLY serves adult aggregator sources. It is wired to
the `network_allow_adult` master switch (endpoint layer) and its UI entry is
gated by `show_restricted`. It never touches normal network sources
(media_urls / media_import).
"""
import copy
import logging
import random
import re
import string
import time
import urllib.parse

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.errors import RequestsError
from app.services.proxy import get_proxy_url

logger = logging.getLogger("vitoice.adult_source")

# Cloudflare TLS fingerprint: javgg intermittently blocks specific
# impersonations (403). Rotate through a candidate list on failure and
# remember the last one that worked — different fingerprints pass at
# different times / under different CF rate-limit states.
_IMPERSONATIONS = ("chrome110", "firefox133", "safari17_0", "edge101")
_last_working_impersonation: str | None = None

# A configured-but-dead proxy (e.g. proxy_enabled=true while Clash isn't
# listening on 127.0.0.1) makes every request fail with curl (7). Once detected
# we skip it for a short window so a single resolution — which fans out to
# several embed fetches — doesn't pay the connect timeout on every hop.
_PROXY_DEAD_TTL_S = 60
_proxy_dead_until = 0.0

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_REQUEST_TIMEOUT = 20.0
# Signed URL validity: e=<seconds>; 129600s = 36h (observed on vidhide/streamwish)
_EXPIRES_E_DEFAULT = 129600

# --- short-lived in-memory cache -----------------------------------------------
# javgg's Cloudflare rate-limits rapid repeat requests (403). Cache successful
# resolutions per fancode so refreshing / re-parsing the same title within a
# short window reuses the previous result instead of hammering the site.
# Signed URLs live 36h, so a 3-hour cache is safe and keeps javgg traffic low.
_CACHE_TTL_S = 3 * 3600
_cache: dict[str, tuple[float, dict]] = {}


def _next_impersonation() -> tuple[str, ...]:
    """Return impersonation candidates — the last working one first."""
    if _last_working_impersonation and _last_working_impersonation in _IMPERSONATIONS:
        return (_last_working_impersonation,) + tuple(
            i for i in _IMPERSONATIONS if i != _last_working_impersonation
        )
    return _IMPERSONATIONS


def _cache_get(base_url: str, fancode: str) -> dict | None:
    key = f"{base_url}|{fancode}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL_S:
        # deep copy so callers may annotate (e.g. "（缓存）") without
        # mutating the stored entry (which is the same dict the original
        # caller already received).
        return copy.deepcopy(hit[1])
    return None


def _cache_put(base_url: str, fancode: str, result: dict) -> None:
    if result.get("status") != "ok":
        return  # never cache failures
    if len(_cache) > 200:
        _cache.clear()
    _cache[f"{base_url}|{fancode}"] = (time.time(), result)

# --- Dean Edwards packer (simplified decoder) ---------------------------------

_PACKER_RE = re.compile(
    r"eval\(function\s*\(p,a,c,k,e,d\)\{[\s\S]*?\}\("
    r"'((?:[^'\\]|\\.)*)',\s*(\d+),\s*(\d+),\s*'((?:[^'\\]|\\.)*)'\.split\('\|'\)\s*\)\s*\)",
    re.S,
)


def _int_to_str(n: int, base: int) -> str:
    """JS Number.prototype.toString(radix) equivalent (2..36)."""
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    res = ""
    while n:
        n, r = divmod(n, base)
        res = digits[r] + res
    return res


def unpack_packer(js: str) -> str | None:
    """Decode a simplified Dean Edwards packed script. Returns plain JS or None."""
    m = _PACKER_RE.search(js)
    if not m:
        return None
    p_str, a_str, c_str, k_str = m.groups()
    try:
        a, c = int(a_str), int(c_str)
    except ValueError:
        return None
    k = k_str.split("|")
    plain = p_str
    for i in range(c - 1, -1, -1):
        if i < len(k) and k[i]:
            token = _int_to_str(i, a)
            plain = re.sub(r"\b" + re.escape(token) + r"\b", k[i], plain)
    return plain


# --- embed resolvers ----------------------------------------------------------

def _extract_embed_urls(page_html: str) -> list[tuple[str, str, str]]:
    """Extract pre-rendered embed iframes from a javgg article page.

    Returns [(nume, server_name, embed_url), ...] from #dooplay_player_content
    .source-box iframes (no_ajax mode). Server names come from the matching
    player option li's .server[data-text].
    """
    # Map nume -> server name from #playeroptionsul
    server_map: dict[str, str] = {}
    for m in re.finditer(
        r"player-option-(\d+)[^>]*>.*?data-text=['\"]([^'\"]+)['\"]",
        page_html,
        re.S,
    ):
        server_map[m.group(1)] = m.group(2)

    iframes = re.findall(
        r"id=['\"]source-player-(\d+)['\"][^>]*>.*?<iframe[^>]*src=['\"]([^'\"]+)['\"]",
        page_html,
        re.S,
    )
    out: list[tuple[str, str, str]] = []
    for nume, src in iframes:
        if src.startswith("//"):
            src = "https:" + src
        out.append((nume, server_map.get(nume, "server"), src))
    return out


def _resolve_turboplay(html: str) -> str | None:
    """Plain m3u8 in turbovidhls embed HTML (no signature)."""
    m = re.search(r"https://cdn\d*\.turboviplay\.com/[^\"'\s<>]+\.m3u8", html)
    return m.group(0) if m else None


def _resolve_packed_hls(html: str) -> tuple[str | None, str | None]:
    """Unpack the packed player config and pull hls2 (signed) + hls3 (unsigned).

    The CDN hostname behind ``hls2``/``hls3`` rotates frequently
    (dramiyos-cdn → premilkyway → acek-cdn → …), so matching fixed domains
    silently breaks whenever a provider switches CDN. Read the well-known
    player-config fields instead — the key names are stable across
    vidhide/streamwish/dood embeds.
    """
    plain = unpack_packer(html)
    if not plain:
        # Some embeds ship the config unpacked (or the packer shape differs);
        # fall back to scanning the raw HTML.
        plain = html

    def _field(key: str) -> str | None:
        m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', plain)
        if not m:
            return None
        value = m.group(1).replace("\\/", "/")
        # hls4-style relative paths (/stream/…) need the embed origin; skip them.
        return value if value.startswith("http") else None

    return _field("hls2"), _field("hls3")


def _signed_expires(url: str) -> int | None:
    """Extract the signed URL validity (e= seconds) from a query string."""
    m = re.search(r"[?&]e=(\d+)", url)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


# --- DoodStream ---------------------------------------------------------------
# DoodStream (playmogo / dood / dsvplay …) does not expose an m3u8. Its embed
# page hides a two-step flow:
#
#     embed page  ->  /pass_md5/{hash}/{token}  ->  prefix
#     final URL   =   prefix + <10 random chars> + ?token=<token>&expiry=<ms>
#
# The minted URL is an *unsigned-looking* mp4 (no extension, video/mp4, Range
# supported) that is bound to the IP that fetched /pass_md5 — a request from a
# different egress IP answers HTTP 200 with a tiny `error_wrong_ip` body instead
# of the stream. It is therefore NEVER persisted: we store the embed page and
# mint the mp4 on demand from the very client that streams it (same connection →
# same IP), with a short in-memory cache to spare repeated seeks.
_DOOD_HOSTS = ("playmogo", "dood", "dsvplay", "dooodster", "d000d")
_DOOD_MINT_TTL_S = 600
_dood_mint_cache: dict[str, tuple[float, str]] = {}


def is_dood_embed(url: str) -> bool:
    """True when ``url`` points at a DoodStream-family embed host."""
    lower = (url or "").lower()
    return any(h in lower for h in _DOOD_HOSTS)


async def mint_dood_url(embed_url: str) -> str | None:
    """Mint a fresh DoodStream mp4 URL from its embed page.

    Uses curl_cffi browser impersonation: the embed host sits behind Cloudflare
    and 403s any non-browser TLS fingerprint (plain httpx cannot fetch it). The
    result must be streamed from the same egress IP — a mismatch yields an HTTP
    200 `error_wrong_ip` body — so the caller re-mints on failure.
    Returns None on any failure; never raises.
    """
    page_html, _err = await _fetch_with_fallback(
        embed_url,
        {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    )
    if not page_html:
        return None
    m = re.search(r"/pass_md5/[^\"'\s<>]+", page_html)
    if not m:
        return None
    path = m.group(0)
    token = path.rstrip("/").rsplit("/", 1)[-1]
    parts = urllib.parse.urlparse(embed_url)
    prefix, _err = await _fetch_with_fallback(
        f"{parts.scheme}://{parts.netloc}{path}",
        {"User-Agent": _UA, "Accept": "*/*"},
        referer=embed_url,
    )
    prefix = (prefix or "").strip()
    if not prefix.startswith("http"):
        return None
    rand = "".join(random.choices(string.ascii_letters + string.digits, k=10))
    return f"{prefix}{rand}?token={token}&expiry={int(time.time() * 1000)}"


async def mint_dood_url_cached(embed_url: str) -> str | None:
    """``mint_dood_url`` with a short TTL cache (safe while the egress IP holds)."""
    hit = _dood_mint_cache.get(embed_url)
    if hit and time.time() - hit[0] < _DOOD_MINT_TTL_S:
        return hit[1]
    url = await mint_dood_url(embed_url)
    if url:
        if len(_dood_mint_cache) > 100:
            _dood_mint_cache.clear()
        _dood_mint_cache[embed_url] = (time.time(), url)
    return url


def invalidate_dood_mint(embed_url: str) -> None:
    """Drop a cached mint so the next call re-mints (used after a failed stream)."""
    _dood_mint_cache.pop(embed_url, None)


async def _try_get(
    url: str, headers: dict, impersonation: str, proxy: str | None
) -> tuple[str | None, str | None]:
    """One GET attempt. Returns (html, None), (None, "404"), or (None, err)."""
    try:
        async with AsyncSession(
            impersonate=impersonation, timeout=_REQUEST_TIMEOUT,
            allow_redirects=True, proxy=proxy,
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text, None
    except RequestsError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            return None, "404"
        return None, str(exc)


def _is_proxy_connect_error(err: str | None) -> bool:
    """True for curl (7)/(56) failures caused by the proxy itself being down."""
    if not err:
        return False
    e = err.lower()
    return "over proxy" in e or "curl: (7)" in e or "curl: (56)" in e


async def _fetch_with_fallback(
    url: str, headers: dict, referer: str | None = None
) -> tuple[str | None, str | None]:
    """GET ``url`` rotating TLS impersonations on 403/errors.

    If the configured proxy cannot be *connected to* (a local misconfiguration,
    not a site response), the request is retried once without it — a dead proxy
    must not take the whole aggregator offline. The proxy is then skipped for a
    short window so one resolution doesn't pay the connect timeout on every hop.

    Returns ``(html, None)`` on success, ``(None, "404")`` for not-found,
    or ``(None, error_message)`` otherwise. Never raises.
    """
    global _last_working_impersonation, _proxy_dead_until
    if referer:
        headers = {**headers, "Referer": referer}

    proxy = await get_proxy_url()
    if proxy and time.time() < _proxy_dead_until:
        proxy = None  # recently found dead — go straight to direct

    last_err: str | None = None
    for direct in (False, True):
        if direct:
            if not proxy:
                break  # no proxy configured → nothing to fall back from
            logger.warning("proxy %s unreachable, retrying %s directly", proxy, url)
        for imp in _next_impersonation():
            html, err = await _try_get(url, headers, imp, None if direct else proxy)
            if html is not None:
                _last_working_impersonation = imp
                return html, None
            if err == "404":
                return None, "404"
            last_err = err
            # A proxy connect failure is network-level — rotating TLS
            # impersonations cannot help, so stop and switch to direct.
            if not direct and proxy and _is_proxy_connect_error(err):
                _proxy_dead_until = time.time() + _PROXY_DEAD_TTL_S
                break
        if direct or not _is_proxy_connect_error(last_err):
            break
    return None, last_err



# --- public entry -------------------------------------------------------------

def parse_fancode(filename_or_code: str) -> str | None:
    """Extract a JAV fancode (e.g. ``SNOS-334`` or prefixed ``300MIUM-1334``) from a string."""
    m = re.search(r"\b(\d{1,5})?([A-Z]{2,6})[-_ ]?(\d{2,5})\b", filename_or_code.upper())
    if not m:
        return None
    prefix = m.group(1) or ""
    return f"{prefix}{m.group(2)}-{m.group(3)}"


async def resolve(
    fancode: str,
    base_url: str = "https://javgg.net",
) -> dict:
    """Resolve a fancode into playable streams from the aggregator.

    Returns a dict:
        {
          "status": "ok" | "no_match" | "error",
          "message": str,
          "fancode": str,
          "results": [ {server, nume, embed_url, m3u8_url, fallback_url?, expires_in?} ]
        }
    Never raises — all failures are folded into the result dict.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"status": "error", "message": "聚合站地址未配置", "fancode": fancode, "results": []}

    code = parse_fancode(fancode) or fancode.strip().upper()
    if not code:
        return {"status": "error", "message": f"无法解析番号: {fancode}", "fancode": fancode, "results": []}

    # Rate-limit guard: reuse a recent successful resolution for the same fancode.
    cached = _cache_get(base, code)
    if cached is not None:
        cached["message"] = cached.get("message", "") + "（缓存）"
        return cached

    page_url = f"{base}/jav/{code}/"
    headers = {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"}
    page_html, fetch_err = await _fetch_with_fallback(page_url, headers)
    if fetch_err == "404":
        return {"status": "no_match", "message": f"聚合站未找到 {code}", "fancode": code, "results": []}
    if page_html is None:
        msg = (
            f"聚合站拒绝了请求（403）——可能触发了访问频率限制，请稍后再试（{code}）"
            if "403" in (fetch_err or "")
            else f"聚合站请求失败: {fetch_err}"
        )
        return {"status": "error", "message": msg, "fancode": code, "results": []}

    embeds = _extract_embed_urls(page_html)
    if not embeds:
        return {"status": "no_match", "message": f"文章页未找到可用的播放源（{page_url}）", "fancode": code, "results": []}

    results: list[dict] = []
    for nume, server, embed_url in embeds:
        item: dict = {"server": server, "nume": nume, "embed_url": embed_url}

        # DoodStream: its playable mp4 is IP-bound + short-lived, so we keep the
        # embed page as the source and mint the stream at playback time (see
        # mint_dood_url). No embed fetch needed here.
        if "dood" in server.lower() or is_dood_embed(embed_url):
            item["m3u8_url"] = embed_url
            item["stream_kind"] = "dood"
            results.append(item)
            continue

        embed_html, fetch_err = await _fetch_with_fallback(
            embed_url,
            {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
            referer=page_url,
        )
        if embed_html is None:
            item["error"] = f"embed 请求失败: {fetch_err}"
            results.append(item)
            continue

        if "turboviplay" in embed_url or "turboplay" in server.lower():
            m3u8 = _resolve_turboplay(embed_html)
            if m3u8:
                item["m3u8_url"] = m3u8
        else:
            hls2, hls3 = _resolve_packed_hls(embed_html)
            if hls2:
                item["m3u8_url"] = hls2
                item["expires_in"] = _signed_expires(hls2) or _EXPIRES_E_DEFAULT
            if hls3:
                item["fallback_url"] = hls3
        if "m3u8_url" not in item:
            item["error"] = "未能从 embed 页解析出流地址"
        results.append(item)

    ok_count = sum(1 for r in results if r.get("m3u8_url"))
    status = "ok" if ok_count else "no_match"
    message = f"解析到 {ok_count}/{len(results)} 个可播放源" if ok_count else "所有源均未解析出流地址"
    result = {"status": status, "message": message, "fancode": code, "results": results}
    _cache_put(base, code, result)
    return result
