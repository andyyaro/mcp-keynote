"""Minimal pure-Python PNG rendering for the image-route workarounds.

AppleScript cannot set a shape's fill color (read-only `background fill
type`, probed), so colored panels are rendered as PNGs and placed via the
verified image-insertion path. No Pillow: a rounded-rect RGBA raster with
supersampled corner anti-aliasing, written with struct+zlib.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

from .error_handler import ParameterError

_SCALE = 2  # rendered pixels per Keynote point (retina-crisp when scaled back)
_SS = 4  # supersample grid per corner pixel edge


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png_rgba(path: str | Path, width: int, height: int, rows: list[bytes]) -> None:
    raw = b"".join(b"\x00" + row for row in rows)
    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )


def _corner_alpha(px: float, py: float, radius: float) -> float:
    """Supersampled coverage of one pixel against a circle of ``radius``
    centered at (radius, radius); (px, py) in corner-local coordinates."""
    hits = 0
    step = 1.0 / _SS
    for sy in range(_SS):
        for sx in range(_SS):
            x = px + (sx + 0.5) * step
            y = py + (sy + 0.5) * step
            if math.hypot(radius - x, radius - y) <= radius:
                hits += 1
    return hits / (_SS * _SS)


def render_panel_png(
    path: str | Path,
    width_pt: float,
    height_pt: float,
    rgb_65535: tuple[int, int, int],
    radius_pt: float = 0,
    opacity: float = 100,
) -> tuple[int, int]:
    """Render a solid rounded-rect panel; returns the pixel dimensions."""
    if width_pt <= 0 or height_pt <= 0:
        raise ParameterError("Panel width and height must be positive.")
    if not 0 <= opacity <= 100:
        raise ParameterError("Panel opacity must be 0-100.")
    w = max(2, round(width_pt * _SCALE))
    h = max(2, round(height_pt * _SCALE))
    r = max(0, round(radius_pt * _SCALE))
    r = min(r, w // 2, h // 2)
    r8, g8, b8 = (min(255, c // 257) for c in rgb_65535)
    a8 = round(255 * opacity / 100)
    solid_px = bytes((r8, g8, b8, a8))
    clear_px = b"\x00\x00\x00\x00"

    # Coverage for one corner block (r x r pixels), computed once and mirrored.
    corner: list[list[float]] = [
        [_corner_alpha(float(x), float(y), float(r)) for x in range(r)] for y in range(r)
    ]

    def row_bytes(y: int) -> bytes:
        if r == 0 or r <= y < h - r:
            return solid_px * w
        cy = y if y < r else h - 1 - y  # corner-local row (top or mirrored bottom)
        left = bytearray()
        for x in range(r):
            alpha = corner[cy][x]
            if alpha <= 0:
                left += clear_px
            elif alpha >= 1:
                left += solid_px
            else:
                left += bytes((r8, g8, b8, round(a8 * alpha)))
        middle = solid_px * (w - 2 * r)
        right = bytearray()
        for x in range(r - 1, -1, -1):
            alpha = corner[cy][x]
            if alpha <= 0:
                right += clear_px
            elif alpha >= 1:
                right += solid_px
            else:
                right += bytes((r8, g8, b8, round(a8 * alpha)))
        return bytes(left) + middle + bytes(right)

    unique_rows: dict[int, bytes] = {}
    rows: list[bytes] = []
    for y in range(h):
        key = y if (y < r or y >= h - r) else -1
        if key not in unique_rows:
            unique_rows[key] = row_bytes(y)
        rows.append(unique_rows[key])
    write_png_rgba(path, w, h, rows)
    return w, h
