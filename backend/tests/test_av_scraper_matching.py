"""Regression tests for adult filename and 3xplanet URL matching."""

import httpx
import pytest

from app.services.av_scraper import (
    _fetch_3xplanet_page,
    _find_3xplanet_detail_url,
    parse_av_fancode,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Tokyo-Hot-n0476.mp4", "N0476"),
        ("259LUXU-1100.mp4", "259LUXU-1100"),
        ("FC2-PPV-4903567.mp4", "FC2-PPV-4903567"),
        ("030315-819 Caribbean 大桥未久.mp4", "030315-819"),
        ("011015-780 Caribbean 大桥未久.mp4", "011015-780"),
        ("DASS-699-C.mp4", "DASS-699"),
    ],
)
def test_parse_av_fancode_special_families(filename: str, expected: str) -> None:
    assert parse_av_fancode(filename) == expected


def test_find_3xplanet_detail_url_accepts_relative_prefixed_slug() -> None:
    html = '<a href="/uncen-leaked-259luxu-1100/">259LUXU-1100</a>'

    assert _find_3xplanet_detail_url(
        html, "259LUXU-1100", "https://3xplanet.com"
    ) == "https://3xplanet.com/uncen-leaked-259luxu-1100/"


@pytest.mark.asyncio
async def test_fetch_3xplanet_uses_special_direct_slugs() -> None:
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        pages = {
            "https://3xplanet.com/n0476/": "tokyo-hot-page",
            "https://3xplanet.com/uncen-leaked-259luxu-1100/": "luxu-page",
            "https://3xplanet.com/fc2-ppv-4903567/": "fc2-page",
        }
        body = pages.get(str(request.url))
        return httpx.Response(200 if body else 404, text=body or "")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await _fetch_3xplanet_page(client, "N0476") == "tokyo-hot-page"
        assert await _fetch_3xplanet_page(client, "259LUXU-1100") == "luxu-page"
        assert await _fetch_3xplanet_page(client, "FC2-PPV-4903567") == "fc2-page"

    assert "https://3xplanet.com/259luxu-1100/" in requested
    assert "https://3xplanet.com/uncen-leaked-259luxu-1100/" in requested
