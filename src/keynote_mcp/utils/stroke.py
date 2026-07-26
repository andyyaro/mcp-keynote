"""Pure-Python PNG rendering of styled connector strokes.

Keynote's AppleScript `line` class has NO stroke API at all: its complete
property record is start/end point, position, width, height, rotation,
reflection, locked, parent, class (probed at v3.1.0 — see docs/CEILING.md).
There is no stroke color, no stroke width, no dash pattern and no arrowhead.
So a connector whose *style* carries meaning (dotted black = invocation,
solid maroon = data path, dotted gray = a denied path) has to be rendered to
a transparent PNG and placed via the verified image-insertion path, exactly
the way `render.render_panel_png` works around the read-only shape fill.

Same constraints as `render.py`: struct + zlib only, no Pillow, no numpy,
supersampled anti-aliasing, 2 rendered pixels per Keynote point.

Coordinate convention
---------------------
The caller passes SLIDE coordinates for the two endpoints. This module
returns the slide-space box the image must be placed at, such that::

    slide_x = origin_x + (px + 0.5) / _SCALE
    slide_y = origin_y + (py + 0.5) / _SCALE

for the CENTER of image pixel (px, py). The returned box size is always
exactly ``pixels / _SCALE``, so Keynote displays the PNG at precisely 2 px
per point and the mapping above holds after placement. Place the image with
its top-left at (origin_x, origin_y) and the drawn stroke lands on the
requested endpoints.
"""

from __future__ import annotations

import bisect
import math
from pathlib import Path

from .error_handler import ParameterError
from .render import _SCALE, _SS, write_png_rgba

# Half the diagonal of one pixel: the separation that proves a pixel is
# wholly inside / wholly outside a half-plane, so it needs no supersampling.
_HALF_DIAG = math.sqrt(0.5)

# Dash patterns as MULTIPLES OF THE STROKE WIDTH, alternating on/off runs
# (so a heavier line gets proportionally longer dashes). Points, not pixels.
_DASH_PATTERNS: dict[str, tuple[float, ...]] = {
    "solid": (),
    "dash": (3.0, 3.0),
    "dot": (1.0, 2.0),
    "dashdot": (3.0, 2.0, 1.0, 2.0),
}
# Names the design tokens use for the same three things.
_DASH_ALIASES: dict[str, str] = {
    "dotted": "dot",
    "dashed": "dash",
    "dash-dot": "dashdot",
    "dashdotted": "dashdot",
}

_ARROW_LENGTH = 4.0  # arrowhead length, in stroke widths
_ARROW_WIDTH = 3.0  # arrowhead base width, in stroke widths

_MAX_PIXELS = 40_000_000  # refuse to allocate an absurd raster

_Point = tuple[float, float]
_Plane = tuple[float, float, float]  # (a, b, c); inside <=> a*x + b*y + c <= 0


def _line_planes(poly: list[_Point]) -> list[_Plane]:
    """Inward-negative half-planes for a convex polygon, orientation-agnostic."""
    planes: list[_Plane] = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        nx, ny = -(by - ay), bx - ax
        norm = math.hypot(nx, ny)
        if norm == 0:
            continue
        nx, ny = nx / norm, ny / norm
        c = -(nx * ax + ny * ay)
        # Orient so that the polygon's interior evaluates negative.
        ox, oy = poly[(i + 2) % n]
        if nx * ox + ny * oy + c > 0:
            nx, ny, c = -nx, -ny, -c
        planes.append((nx, ny, c))
    return planes


def _polygon_row_span(poly: list[_Point], y: float) -> tuple[float, float] | None:
    """x-range of a polygon on the horizontal line ``y`` (None if it misses)."""
    xs: list[float] = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay <= y < by) or (by <= y < ay):
            xs.append(ax + (y - ay) / (by - ay) * (bx - ax))
    if not xs:
        return None
    return min(xs), max(xs)


def _circle_row_span(cx: float, cy: float, r: float, y: float) -> tuple[float, float] | None:
    dy = y - cy
    if abs(dy) >= r:
        return None
    half = math.sqrt(r * r - dy * dy)
    return cx - half, cx + half


def _dash_intervals(
    u0: float, u1: float, pattern: tuple[float, ...], width_px: float
) -> list[tuple[float, float]]:
    """Split [u0, u1] (distance along the segment, in pixels) into ink runs."""
    if u1 <= u0:
        return []
    if not pattern:
        return [(u0, u1)]
    runs = [p * width_px for p in pattern]
    period = sum(runs)
    span = u1 - u0
    # Nudge the period so a whole number of them fits: the stroke then both
    # starts and ends on ink instead of trailing off mid-gap.
    reps = max(1, round(span / period))
    scale = min(1.6, max(0.6, span / (reps * period)))
    if period * scale < 1.0:  # finer than a pixel: nothing to alternate
        return [(u0, u1)]
    intervals: list[tuple[float, float]] = []
    pos = u0
    index = 0
    while pos < u1 - 1e-9:
        run = runs[index % len(runs)] * scale
        if index % 2 == 0:
            intervals.append((pos, min(u1, pos + run)))
        pos += run
        index += 1
    return intervals


def render_stroke_png(
    path: str | Path,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    rgb_65535: tuple[int, int, int],
    width_pt: float = 2.0,
    dash: str = "solid",
    start_arrow: bool = False,
    end_arrow: bool = False,
    opacity: float = 100,
) -> tuple[float, float, float, float, int, int]:
    """Render a styled stroke; return (origin_x, origin_y, box_w, box_h, px_w, px_h).

    ``x1, y1, x2, y2`` are slide points. The returned origin/size is where the
    PNG must be placed for the drawn stroke to run between those two points
    (see the module docstring for the exact pixel<->slide mapping). Widths
    below 0.5pt and dash periods finer than a pixel cannot be resolved at
    2 px/pt: they render as a solid one-pixel hairline.
    """
    for value in (x1, y1, x2, y2, width_pt, opacity):
        if not math.isfinite(value):
            raise ParameterError("Stroke coordinates, width and opacity must be finite numbers.")
    if width_pt <= 0:
        raise ParameterError("Stroke width must be positive.")
    if not 0 <= opacity <= 100:
        raise ParameterError("Stroke opacity must be 0-100.")
    key = _DASH_ALIASES.get(str(dash).strip().lower(), str(dash).strip().lower())
    if key not in _DASH_PATTERNS:
        raise ParameterError(
            f"Unknown dash style '{dash}'. Use one of: {', '.join(sorted(_DASH_PATTERNS))}."
        )
    pattern = _DASH_PATTERNS[key]

    length_pt = math.hypot(x2 - x1, y2 - y1)
    if length_pt < 1e-6:
        raise ParameterError("Stroke endpoints must differ (zero-length segment).")

    # --- geometry in slide points -------------------------------------------
    ux, uy = (x2 - x1) / length_pt, (y2 - y1) / length_pt  # along the segment
    nx, ny = -uy, ux  # perpendicular
    # Never thinner than one rendered pixel: a hairline whose half width falls
    # between two subsample rows would otherwise disappear entirely.
    half_w = max(width_pt / 2.0, 0.5 / _SCALE)
    arrow_len = _ARROW_LENGTH * width_pt
    arrow_half = _ARROW_WIDTH * width_pt / 2.0

    triangles_pt: list[list[_Point]] = []
    if start_arrow:
        bx, by = x1 + ux * arrow_len, y1 + uy * arrow_len
        triangles_pt.append(
            [
                (x1, y1),
                (bx + nx * arrow_half, by + ny * arrow_half),
                (bx - nx * arrow_half, by - ny * arrow_half),
            ]
        )
    if end_arrow:
        bx, by = x2 - ux * arrow_len, y2 - uy * arrow_len
        triangles_pt.append(
            [
                (x2, y2),
                (bx + nx * arrow_half, by + ny * arrow_half),
                (bx - nx * arrow_half, by - ny * arrow_half),
            ]
        )

    # The body stops at the arrowhead base so it can never overshoot the tip.
    u_start = arrow_len if start_arrow else 0.0
    u_end = length_pt - arrow_len if end_arrow else length_pt
    has_body = u_end > u_start
    body_a = (x1 + ux * u_start, y1 + uy * u_start)
    body_b = (x1 + ux * u_end, y1 + uy * u_end)

    xs: list[float] = []
    ys: list[float] = []
    if has_body:  # round caps: the body reaches half a width past its ends
        for px, py in (body_a, body_b):
            xs += [px - half_w, px + half_w]
            ys += [py - half_w, py + half_w]
    for tri in triangles_pt:
        for px, py in tri:
            xs.append(px)
            ys.append(py)
    # One whole pixel of slack on every side: anti-aliased edges are never
    # clipped, and the border pixels (so the corners) stay fully transparent
    # because no geometry can reach into them.
    pad = 1.0 / _SCALE
    min_x, max_x = min(xs) - pad, max(xs) + pad
    min_y, max_y = min(ys) - pad, max(ys) + pad

    px_w = max(1, math.ceil((max_x - min_x) * _SCALE))
    px_h = max(1, math.ceil((max_y - min_y) * _SCALE))
    if px_w * px_h > _MAX_PIXELS:
        raise ParameterError("Stroke is too large to render (over 40M pixels).")
    origin_x, origin_y = min_x, min_y
    box_w, box_h = px_w / _SCALE, px_h / _SCALE

    # --- the same geometry, now in image pixels ------------------------------
    def to_px(p: _Point) -> _Point:
        return ((p[0] - origin_x) * _SCALE, (p[1] - origin_y) * _SCALE)

    p1 = to_px((x1, y1))
    radius = half_w * _SCALE
    triangles = [[to_px(v) for v in tri] for tri in triangles_pt]
    tri_planes = [_line_planes(tri) for tri in triangles]

    # Empty when the arrowheads have swallowed the whole segment.
    intervals = _dash_intervals(u_start * _SCALE, u_end * _SCALE, pattern, width_pt * _SCALE)
    starts = [a for a, _ in intervals]

    def body_distance(u: float, v: float) -> float:
        """Distance from (along, perpendicular) to the nearest ink run."""
        if not intervals:
            return math.inf
        best = math.inf
        index = bisect.bisect_right(starts, u)
        for k in (index - 1, index):
            if 0 <= k < len(intervals):
                a, b = intervals[k]
                du = a - u if u < a else (u - b if u > b else 0.0)
                best = min(best, abs(v) if du == 0.0 else math.hypot(du, v))
        return best

    def inside(px: float, py: float) -> bool:
        dx, dy = px - p1[0], py - p1[1]
        if body_distance(dx * ux + dy * uy, -dx * uy + dy * ux) <= radius:
            return True
        return any(all(a * px + b * py + c <= 0 for a, b, c in planes) for planes in tri_planes)

    def coverage(ix: int, iy: int) -> float:
        """Supersampled ink coverage of one pixel, as render.py does its corners."""
        cx, cy = ix + 0.5, iy + 0.5
        dx, dy = cx - p1[0], cy - p1[1]
        dist = body_distance(dx * ux + dy * uy, -dx * uy + dy * ux)
        if dist <= radius - _HALF_DIAG:
            return 1.0
        near = dist <= radius + _HALF_DIAG
        for planes in tri_planes:
            worst = max(a * cx + b * cy + c for a, b, c in planes)
            if worst <= -_HALF_DIAG:
                return 1.0
            if worst < _HALF_DIAG:
                near = True
        if not near:
            return 0.0
        hits = 0
        step = 1.0 / _SS
        for sy in range(_SS):
            sample_y = iy + (sy + 0.5) * step
            for sx in range(_SS):
                if inside(ix + (sx + 0.5) * step, sample_y):
                    hits += 1
        return hits / (_SS * _SS)

    # --- raster --------------------------------------------------------------
    r8, g8, b8 = (max(0, min(255, c // 257)) for c in rgb_65535)
    alpha_max = round(255 * opacity / 100)
    clear_row = bytes(px_w * 4)
    span_shapes: list[list[_Point]] = list(triangles)
    if has_body:
        a_px, b_px = to_px(body_a), to_px(body_b)
        span_shapes.append(
            [
                (a_px[0] + nx * radius, a_px[1] + ny * radius),
                (b_px[0] + nx * radius, b_px[1] + ny * radius),
                (b_px[0] - nx * radius, b_px[1] - ny * radius),
                (a_px[0] - nx * radius, a_px[1] - ny * radius),
            ]
        )

    rows: list[bytes] = []
    for iy in range(px_h):
        y = iy + 0.5
        spans: list[tuple[float, float]] = []
        if has_body:
            for cap in (to_px(body_a), to_px(body_b)):
                circle = _circle_row_span(cap[0], cap[1], radius, y)
                if circle is not None:
                    spans.append(circle)
        for poly in span_shapes:
            polygon = _polygon_row_span(poly, y)
            if polygon is not None:
                spans.append(polygon)
        if not spans:
            rows.append(clear_row)
            continue
        lo = max(0, math.floor(min(s[0] for s in spans) - 1.0))
        hi = min(px_w - 1, math.ceil(max(s[1] for s in spans) + 1.0))
        if lo > hi:
            rows.append(clear_row)
            continue
        row = bytearray(clear_row)
        for ix in range(lo, hi + 1):
            alpha = round(alpha_max * coverage(ix, iy))
            if alpha > 0:
                row[ix * 4 : ix * 4 + 4] = bytes((r8, g8, b8, alpha))
        rows.append(bytes(row))

    write_png_rgba(path, px_w, px_h, rows)
    return origin_x, origin_y, box_w, box_h, px_w, px_h
