"""SSRF guard for user-supplied network URLs.

Only http/https URLs with a resolvable host are accepted by the network
stream / check / metadata endpoints. This prevents ``file://`` and other
non-HTTP schemes from being passed to httpx or ffmpeg/ffprobe.

Private / link-local / loopback IPs are intentionally NOT blocked here: the
desktop app legitimately supports LAN media servers. Loopback SSRF has little
incremental risk on a single-user local desktop process that already binds to
127.0.0.1.
"""

from urllib.parse import urlparse


_SAFE_SCHEMES = {"http", "https"}


def validate_http_url(url: str) -> None:
    """Raise ``ValueError`` when ``url`` is not a safe HTTP(S) target."""
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in _SAFE_SCHEMES:
        raise ValueError("仅支持 http/https 网络源")
    if not parsed.hostname:
        raise ValueError("网络源缺少主机名")
