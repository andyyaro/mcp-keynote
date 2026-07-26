"""render_panel_png: real, decodable PNGs with the right geometry, color,
opacity, and corner transparency. Decoded by hand (zlib + struct; color type
6, filter byte 0 per row, exactly as write_png_rgba emits)."""

import struct
import zlib

import pytest

from keynote_mcp.utils import ParameterError
from keynote_mcp.utils.render import render_panel_png

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _decode(path):
    """Return (width, height, pixel) where pixel(x, y) -> (r, g, b, a)."""
    blob = open(path, "rb").read()
    assert blob[:8] == _SIGNATURE
    pos = 8
    ihdr = None
    idat = b""
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos : pos + 4])
        tag = blob[pos + 4 : pos + 8]
        data = blob[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", data)
        elif tag == b"IDAT":
            idat += data
        pos += 12 + length
    width, height, bit_depth, color_type, _, _, _ = ihdr
    assert bit_depth == 8
    assert color_type == 6  # RGBA
    raw = zlib.decompress(idat)
    stride = 1 + width * 4
    assert len(raw) == stride * height

    def pixel(x, y):
        row = raw[y * stride : (y + 1) * stride]
        assert row[0] == 0  # filter byte 0 per row
        return tuple(row[1 + x * 4 : 5 + x * 4])

    return width, height, pixel


class TestRenderPanelPng:
    def test_square_corners_solid_color(self, tmp_path):
        out = tmp_path / "p.png"
        w, h = render_panel_png(out, 150, 100, (65535, 0, 32896), radius_pt=0)
        assert (w, h) == (300, 200)  # 2 rendered px per point
        width, height, pixel = _decode(out)
        assert (width, height) == (300, 200)
        # r=65535 -> 255, g=0, b=32896//257=128; opacity 100 -> alpha 255
        assert pixel(0, 0) == (255, 0, 128, 255)
        assert pixel(150, 100) == (255, 0, 128, 255)

    def test_rounded_corner_is_transparent_center_opaque(self, tmp_path):
        out = tmp_path / "p.png"
        render_panel_png(out, 100, 100, (65535, 65535, 65535), radius_pt=20)
        width, height, pixel = _decode(out)
        assert pixel(0, 0)[3] == 0  # corner clipped away
        assert pixel(width // 2, height // 2) == (255, 255, 255, 255)
        # edge midpoints are inside the rounded rect
        assert pixel(width // 2, 0)[3] == 255

    def test_opacity_scales_alpha(self, tmp_path):
        out = tmp_path / "p.png"
        render_panel_png(out, 50, 50, (0, 0, 0), radius_pt=0, opacity=50)
        _, _, pixel = _decode(out)
        assert pixel(25, 25) == (0, 0, 0, 128)

    def test_radius_larger_than_half_min_dimension_is_clamped(self, tmp_path):
        out = tmp_path / "p.png"
        w, h = render_panel_png(out, 40, 20, (1000, 1000, 1000), radius_pt=500)
        assert (w, h) == (80, 40)
        width, height, pixel = _decode(out)
        # still a valid raster with an opaque center despite the huge radius
        assert pixel(width // 2, height // 2)[3] == 255
        assert pixel(0, 0)[3] == 0

    def test_non_positive_size_raises(self, tmp_path):
        with pytest.raises(ParameterError, match="positive"):
            render_panel_png(tmp_path / "p.png", 0, 10, (0, 0, 0))
        with pytest.raises(ParameterError, match="positive"):
            render_panel_png(tmp_path / "p.png", 10, -1, (0, 0, 0))

    def test_bad_opacity_raises(self, tmp_path):
        with pytest.raises(ParameterError, match="opacity"):
            render_panel_png(tmp_path / "p.png", 10, 10, (0, 0, 0), opacity=101)
        with pytest.raises(ParameterError, match="opacity"):
            render_panel_png(tmp_path / "p.png", 10, 10, (0, 0, 0), opacity=-1)
