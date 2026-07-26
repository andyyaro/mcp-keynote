"""Unsplash tools with a faked aiohttp session - no network."""

from unittest.mock import patch

import pytest

from keynote_mcp.tools import unsplash as unsplash_module
from keynote_mcp.tools.unsplash import UnsplashTools


class FakeResponse:
    def __init__(self, status=200, payload=None, body=b"image-bytes"):
        self.status = status
        self._payload = payload
        self._body = body
        self.content = self

    async def json(self):
        return self._payload

    async def text(self):
        return "rate limit exceeded"

    async def iter_chunked(self, _size):
        yield self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


PHOTO = {
    "id": "abc123",
    "description": "a cat",
    "width": 4000,
    "height": 3000,
    "likes": 42,
    "user": {"name": "Photographer"},
    "links": {"html": "https://unsplash.com/p/abc123", "download_location": "https://dl"},
    "urls": {"regular": "https://img/regular.jpg"},
}


@pytest.fixture
def tools(mock_subprocess_run, monkeypatch, tmp_path):
    monkeypatch.setenv("UNSPLASH_KEY", "test-key")
    monkeypatch.setattr(unsplash_module.tempfile, "gettempdir", lambda: str(tmp_path))
    return UnsplashTools()


def _with_session(responses):
    session = FakeSession(responses)
    return patch.object(unsplash_module.aiohttp, "ClientSession", lambda: session), session


async def test_search_formats_results(tools):
    ctx, _ = _with_session([FakeResponse(payload={"results": [PHOTO]})])
    with ctx:
        result = await tools.search_unsplash_images("cat")
    text = result[0].text
    assert "a cat" in text
    assert "Photographer" in text
    assert "4000x3000" in text


async def test_search_no_results(tools):
    ctx, _ = _with_session([FakeResponse(payload={"results": []})])
    with ctx:
        result = await tools.search_unsplash_images("nothing")
    assert "No images found" in result[0].text


async def test_search_api_error_surfaces_status(tools):
    ctx, _ = _with_session([FakeResponse(status=403)])
    with ctx:
        result = await tools.search_unsplash_images("cat")
    assert "403" in result[0].text


async def test_add_image_downloads_and_inserts(tools, mock_subprocess_run):
    ctx, session = _with_session(
        [
            FakeResponse(payload={"results": [PHOTO]}),
            FakeResponse(body=b"jpeg-bytes"),
            FakeResponse(payload={}),
        ]
    )
    with ctx:
        result = await tools.add_unsplash_image_to_slide(1, "cat", x=10, y=20)
    assert "Successfully added image" in result[0].text
    # AppleScript insertion happened with the downloaded path via argv
    cmd = mock_subprocess_run.call_args.args[0]
    assert cmd[0] == "/usr/bin/osascript"
    assert any("unsplash_abc123" in arg for arg in cmd)
    # download stat endpoint pinged per Unsplash API guidelines
    assert "https://dl" in session.requests


async def test_add_image_index_out_of_range(tools):
    ctx, _ = _with_session([FakeResponse(payload={"results": [PHOTO]})])
    with ctx:
        result = await tools.add_unsplash_image_to_slide(1, "cat", image_index=5)
    assert "out of range" in result[0].text


async def test_add_image_missing_url(tools):
    photo = dict(PHOTO, urls={})
    ctx, _ = _with_session([FakeResponse(payload={"results": [photo]})])
    with ctx:
        result = await tools.add_unsplash_image_to_slide(1, "cat")
    assert "download URL" in result[0].text


async def test_random_image(tools, mock_subprocess_run):
    ctx, _ = _with_session(
        [
            FakeResponse(payload=PHOTO),
            FakeResponse(body=b"jpeg-bytes"),
            FakeResponse(payload={}),
        ]
    )
    with ctx:
        result = await tools.get_random_unsplash_image(1, query="dog")
    assert "Successfully added random image" in result[0].text


async def test_random_image_api_error(tools):
    ctx, _ = _with_session([FakeResponse(status=500)])
    with ctx:
        result = await tools.get_random_unsplash_image(1)
    assert "500" in result[0].text


async def test_download_failure_reported(tools):
    ctx, _ = _with_session([FakeResponse(payload={"results": [PHOTO]}), FakeResponse(status=404)])
    with ctx:
        result = await tools.add_unsplash_image_to_slide(1, "cat")
    assert "download failed" in result[0].text.lower()
