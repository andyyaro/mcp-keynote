"""render_stroke_png: real PNGs whose pixels carry the requested stroke.

Keynote has no stroke API (docs/CEILING.md), so a connector's meaning lives
entirely in these pixels — a "dotted" line that quietly renders solid, or an
image box that is off by half a line width, is a wrong diagram, not a
cosmetic slip. Every assertion here therefore measures the raster and the
returned placement box, never "the file exists". Decoded with Pillow (a dev
dependency, already used by the integration harness).
"""

import itertools
import math

import pytest
from PIL import Image

from keynote_mcp.utils import ParameterError
from keynote_mcp.utils.stroke import render_stroke_png

MAROON = (35466, 8224, 21074)  # #8A2052, the design system's data-path color
MAROON_8 = (138, 32, 82)
SCALE = 2  # rendered pixels per point, shared with render.py


def _alpha(path):
    """Return (width, height, alpha(x, y)) for a rendered stroke."""
    im = Image.open(path).convert("RGBA")
    px = im.load()
    return im.size[0], im.size[1], (lambda x, y: px[x, y][3])


def _rgba(path):
    im = Image.open(path).convert("RGBA")
    px = im.load()
    return im.size[0], im.size[1], (lambda x, y: px[x, y])


def _to_slide(box, ix, iy):
    """Center of image pixel (ix, iy) in slide points, per the documented map."""
    ox, oy = box[0], box[1]
    return ox + (ix + 0.5) / SCALE, oy + (iy + 0.5) / SCALE


def _row_index(box, slide_y):
    return (slide_y - box[1]) * SCALE - 0.5


def _col_index(box, slide_x):
    return (slide_x - box[0]) * SCALE - 0.5


def _runs(alpha, width, y, threshold=128):
    """Lengths of the consecutive opaque runs along image row ``y``."""
    out = []
    run = 0
    for x in range(width):
        if alpha(x, y) >= threshold:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out


def _dist_to_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _ink_near(box, path, cx, cy, radius):
    """Total ink (in whole-pixel equivalents) within ``radius`` points of a slide point."""
    w, h, alpha = _alpha(path)
    total = 0.0
    for iy in range(h):
        for ix in range(w):
            a = alpha(ix, iy)
            if not a:
                continue
            sx, sy = _to_slide(box, ix, iy)
            if math.hypot(sx - cx, sy - cy) <= radius:
                total += a / 255.0
    return total


def _ink_beside_axis(box, path, axis_y, half_band, x_range):
    """Ink further than ``half_band`` points from a horizontal stroke's axis."""
    w, h, alpha = _alpha(path)
    total = 0.0
    for iy in range(h):
        for ix in range(w):
            a = alpha(ix, iy)
            if not a:
                continue
            sx, sy = _to_slide(box, ix, iy)
            if x_range[0] <= sx <= x_range[1] and abs(sy - axis_y) > half_band:
                total += a / 255.0
    return total


class TestPlacementBox:
    def test_box_is_whole_pixels_at_two_per_point(self, tmp_path):
        out = tmp_path / "s.png"
        ox, oy, bw, bh, pw, ph = render_stroke_png(
            out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=4
        )
        assert (bw, bh) == (pw / SCALE, ph / SCALE)  # exact 2 px/pt after placement
        w, h, _ = _alpha(out)
        assert (w, h) == (pw, ph)
        # Tight: 200pt long + a half width each end + 1px of anti-alias slack.
        assert ox == pytest.approx(100 - 2 - 0.5)
        assert oy == pytest.approx(100 - 2 - 0.5)
        assert bw == pytest.approx(205.0)
        assert bh == pytest.approx(5.0)

    def test_drawn_pixels_land_on_the_requested_segment(self, tmp_path):
        out = tmp_path / "s.png"
        x1, y1, x2, y2 = 200.0, 140.0, 560.0, 380.0
        box = render_stroke_png(out, x1, y1, x2, y2, rgb_65535=MAROON, width_pt=6)
        w, h, alpha = _alpha(out)
        opaque = 0
        for iy in range(h):
            for ix in range(w):
                if alpha(ix, iy) < 250:
                    continue
                opaque += 1
                sx, sy = _to_slide(box, ix, iy)
                # Fully-inked pixels must lie within the stroke's half width.
                assert _dist_to_segment(sx, sy, x1, y1, x2, y2) <= 3.0 + 0.5
        assert opaque > 1000

    def test_both_endpoints_are_inked(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 300, 500, 700, 260, rgb_65535=MAROON, width_pt=5)
        _, _, alpha = _alpha(out)
        for sx, sy in ((300, 500), (700, 260)):
            ix = round(_col_index(box, sx))
            iy = round(_row_index(box, sy))
            assert alpha(ix, iy) >= 250, f"no ink at endpoint ({sx}, {sy})"

    def test_reversed_endpoints_give_the_same_box(self, tmp_path):
        a = render_stroke_png(tmp_path / "a.png", 100, 100, 400, 260, rgb_65535=MAROON)
        b = render_stroke_png(tmp_path / "b.png", 400, 260, 100, 100, rgb_65535=MAROON)
        assert a == b


class TestSolidBody:
    def test_continuous_run_of_the_requested_color(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=4)
        w, _, rgba = _rgba(out)
        row = round(_row_index(box, 100.0))
        for sx in (110, 200, 250, 290):
            assert rgba(round(_col_index(box, sx)), row) == (*MAROON_8, 255)
        _, _, alpha = _alpha(out)
        runs = _runs(alpha, w, row)
        assert len(runs) == 1  # solid means solid
        assert runs[0] >= 200 * SCALE - 2

    def test_measured_thickness_matches_width_pt(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=4)
        _, h, alpha = _alpha(out)
        col = round(_col_index(box, 200.0))
        weighted = sum(alpha(col, iy) / 255.0 for iy in range(h)) / SCALE
        assert weighted == pytest.approx(4.0, abs=0.25)
        counted = sum(1 for iy in range(h) if alpha(col, iy) >= 128) / SCALE
        assert abs(counted - 4.0) <= 1.0 / SCALE  # within one pixel

    def test_thickness_follows_width_pt(self, tmp_path):
        thicknesses = []
        for width_pt in (2, 6, 12):
            out = tmp_path / f"s{width_pt}.png"
            box = render_stroke_png(out, 50, 300, 250, 300, rgb_65535=MAROON, width_pt=width_pt)
            _, h, alpha = _alpha(out)
            col = round(_col_index(box, 150.0))
            thicknesses.append(sum(alpha(col, iy) / 255.0 for iy in range(h)) / SCALE)
        assert thicknesses == pytest.approx([2.0, 6.0, 12.0], abs=0.3)

    def test_corners_are_fully_transparent(self, tmp_path):
        out = tmp_path / "s.png"
        render_stroke_png(
            out, 100, 100, 400, 300, rgb_65535=MAROON, width_pt=5, start_arrow=True, end_arrow=True
        )
        w, h, alpha = _alpha(out)
        assert [alpha(0, 0), alpha(w - 1, 0), alpha(0, h - 1), alpha(w - 1, h - 1)] == [0, 0, 0, 0]


class TestDashPatterns:
    def test_dashed_alternates_along_its_length(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=3, dash="dash")
        w, _, alpha = _alpha(out)
        row = round(_row_index(box, 100.0))
        runs = _runs(alpha, w, row)
        # 9pt on / 9pt off over 200pt is about 11 dashes; a solid render is 1.
        assert 6 <= len(runs) <= 20, f"expected a dashed line, got {len(runs)} run(s)"
        ink = sum(runs) / (200 * SCALE)
        assert 0.3 < ink < 0.8, f"ink fraction {ink:.2f} is not dashed"

    def test_dotted_is_finer_than_dashed(self, tmp_path):
        row_runs = {}
        for name in ("dash", "dot"):
            out = tmp_path / f"{name}.png"
            box = render_stroke_png(
                out, 100, 100, 400, 100, rgb_65535=MAROON, width_pt=3, dash=name
            )
            w, _, alpha = _alpha(out)
            row_runs[name] = _runs(alpha, w, round(_row_index(box, 100.0)))
        assert len(row_runs["dot"]) > len(row_runs["dash"])
        assert max(row_runs["dot"]) < min(row_runs["dash"])

    def test_dashdot_alternates_two_run_lengths(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(
            out, 100, 100, 500, 100, rgb_65535=MAROON, width_pt=4, dash="dashdot"
        )
        w, _, alpha = _alpha(out)
        runs = _runs(alpha, w, round(_row_index(box, 100.0)))
        assert len(runs) >= 6
        long_runs = [r for r in runs if r > sum(runs) / len(runs)]
        short_runs = [r for r in runs if r <= sum(runs) / len(runs)]
        assert long_runs and short_runs
        assert min(long_runs) > max(short_runs) * 1.5

    def test_dashes_scale_with_width(self, tmp_path):
        counts = []
        for width_pt in (2, 8):
            out = tmp_path / f"s{width_pt}.png"
            box = render_stroke_png(
                out, 100, 100, 500, 100, rgb_65535=MAROON, width_pt=width_pt, dash="dash"
            )
            w, _, alpha = _alpha(out)
            counts.append(len(_runs(alpha, w, round(_row_index(box, 100.0)))))
        assert counts[0] > counts[1] * 2  # dash length is a multiple of the width

    def test_dashes_are_measured_along_a_diagonal(self, tmp_path):
        out = tmp_path / "s.png"
        x1, y1, x2, y2 = 100.0, 100.0, 400.0, 400.0
        box = render_stroke_png(out, x1, y1, x2, y2, rgb_65535=MAROON, width_pt=4, dash="dash")
        w, h, alpha = _alpha(out)
        # Walk the segment itself and count ink transitions along it.
        samples = 1200
        seq = []
        for k in range(samples + 1):
            t = k / samples
            sx, sy = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            ix = round(_col_index(box, sx))
            iy = round(_row_index(box, sy))
            seq.append(alpha(min(max(ix, 0), w - 1), min(max(iy, 0), h - 1)) >= 128)
        transitions = sum(1 for a, b in itertools.pairwise(seq) if a != b)
        assert transitions >= 10, "a dashed diagonal rendered as a solid line"
        assert 0.3 < sum(seq) / len(seq) < 0.8

    def test_sub_pixel_dashes_degrade_to_solid(self, tmp_path):
        """A hairline's dash period is finer than a pixel; render it solid rather
        than as a row of unresolvable smudges."""
        out = tmp_path / "s.png"
        box = render_stroke_png(
            out, 100, 100, 200, 100, rgb_65535=MAROON, width_pt=0.05, dash="dot"
        )
        w, _, alpha = _alpha(out)
        runs = _runs(alpha, w, round(_row_index(box, 100.0)), threshold=1)
        assert len(runs) == 1

    def test_dash_aliases_match_canonical_names(self, tmp_path):
        for alias, canonical in (("dotted", "dot"), ("dashed", "dash"), ("dash-dot", "dashdot")):
            a = tmp_path / f"{alias}.png"
            c = tmp_path / f"{canonical}.png"
            render_stroke_png(a, 10, 10, 210, 10, rgb_65535=MAROON, width_pt=3, dash=alias)
            render_stroke_png(c, 10, 10, 210, 10, rgb_65535=MAROON, width_pt=3, dash=canonical)
            assert a.read_bytes() == c.read_bytes()


class TestAntiAliasing:
    def test_diagonal_has_partial_alpha_at_its_edges(self, tmp_path):
        out = tmp_path / "s.png"
        render_stroke_png(out, 100, 100, 340, 260, rgb_65535=MAROON, width_pt=5)
        w, h, alpha = _alpha(out)
        partial = sum(1 for iy in range(h) for ix in range(w) if 20 < alpha(ix, iy) < 235)
        assert partial > 100, "diagonal stroke is not anti-aliased"

    def test_horizontal_edges_stay_crisp(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=4)
        _, h, alpha = _alpha(out)
        col = round(_col_index(box, 200.0))
        column = [alpha(col, iy) for iy in range(h)]
        assert sum(1 for a in column if a == 255) >= 6


class TestArrowheads:
    def test_end_arrow_adds_ink_at_the_end_only(self, tmp_path):
        plain = tmp_path / "plain.png"
        arrow = tmp_path / "arrow.png"
        args = {"rgb_65535": MAROON, "width_pt": 4}
        box_plain = render_stroke_png(plain, 150, 200, 450, 200, **args)
        box_arrow = render_stroke_png(arrow, 150, 200, 450, 200, end_arrow=True, **args)
        # An arrowhead is the only thing that can put ink outside the 4pt body.
        assert _ink_beside_axis(box_plain, plain, 200, 3, (430, 470)) < 1.0
        assert _ink_beside_axis(box_arrow, arrow, 200, 3, (430, 470)) > 30.0
        assert _ink_beside_axis(box_arrow, arrow, 200, 3, (130, 170)) < 1.0
        assert _ink_near(box_arrow, arrow, 450, 200, 16) > _ink_near(box_plain, plain, 450, 200, 16)
        assert _ink_near(box_arrow, arrow, 150, 200, 16) == pytest.approx(
            _ink_near(box_plain, plain, 150, 200, 16), rel=0.05
        )

    def test_start_arrow_adds_ink_at_the_start_only(self, tmp_path):
        plain = tmp_path / "plain.png"
        arrow = tmp_path / "arrow.png"
        args = {"rgb_65535": MAROON, "width_pt": 4}
        box_plain = render_stroke_png(plain, 150, 200, 450, 200, **args)
        box_arrow = render_stroke_png(arrow, 150, 200, 450, 200, start_arrow=True, **args)
        assert _ink_beside_axis(box_arrow, arrow, 200, 3, (130, 170)) > 30.0
        assert _ink_beside_axis(box_arrow, arrow, 200, 3, (430, 470)) < 1.0
        assert _ink_near(box_arrow, arrow, 150, 200, 16) > _ink_near(box_plain, plain, 150, 200, 16)
        assert _ink_near(box_arrow, arrow, 450, 200, 16) == pytest.approx(
            _ink_near(box_plain, plain, 450, 200, 16), rel=0.05
        )

    def test_both_arrows(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(
            out, 150, 200, 450, 200, rgb_65535=MAROON, width_pt=4, start_arrow=True, end_arrow=True
        )
        assert _ink_beside_axis(box, out, 200, 3, (130, 170)) > 30.0
        assert _ink_beside_axis(box, out, 200, 3, (430, 470)) > 30.0
        assert _ink_beside_axis(box, out, 200, 3, (280, 320)) < 1.0  # body stays 4pt

    def test_arrow_tip_is_at_the_endpoint_and_the_body_does_not_overshoot(self, tmp_path):
        out = tmp_path / "s.png"
        x1, y1, x2, y2 = 100.0, 100.0, 400.0, 100.0
        box = render_stroke_png(out, x1, y1, x2, y2, rgb_65535=MAROON, width_pt=4, end_arrow=True)
        w, h, alpha = _alpha(out)
        max_x = max(
            _to_slide(box, ix, iy)[0] for iy in range(h) for ix in range(w) if alpha(ix, iy) >= 128
        )
        assert max_x == pytest.approx(x2, abs=0.75)  # tip at the endpoint, no overshoot
        # The head is wider than the 4pt body a few points behind the tip.
        col = round(_col_index(box, x2 - 8))
        head = sum(alpha(col, iy) / 255.0 for iy in range(h)) / SCALE
        assert head > 5.0

    def test_short_stroke_swallowed_by_its_arrowheads(self, tmp_path):
        """Both heads are longer than the segment: heads only, no body, no crash."""
        out = tmp_path / "s.png"
        box = render_stroke_png(
            out, 200, 200, 210, 200, rgb_65535=MAROON, width_pt=4, start_arrow=True, end_arrow=True
        )
        w, h, alpha = _alpha(out)
        assert sum(alpha(ix, iy) for iy in range(h) for ix in range(w)) > 0
        assert _ink_beside_axis(box, out, 200, 3, (190, 220)) > 10.0

    def test_arrow_widens_the_placement_box(self, tmp_path):
        plain = render_stroke_png(tmp_path / "p.png", 100, 100, 400, 100, rgb_65535=MAROON)
        arrow = render_stroke_png(
            tmp_path / "a.png", 100, 100, 400, 100, rgb_65535=MAROON, end_arrow=True
        )
        assert arrow[5] > plain[5]  # taller box: the head is wider than the line
        assert arrow[1] < plain[1]  # and its origin moved up to contain it


class TestColorAndOpacity:
    def test_opacity_scales_the_alpha_channel(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=6, opacity=50)
        _, _, rgba = _rgba(out)
        pixel = rgba(round(_col_index(box, 200.0)), round(_row_index(box, 100.0)))
        assert pixel[:3] == MAROON_8  # color is not premultiplied
        assert pixel[3] in (127, 128)

    def test_zero_opacity_renders_nothing(self, tmp_path):
        out = tmp_path / "s.png"
        render_stroke_png(out, 100, 100, 300, 100, rgb_65535=MAROON, width_pt=6, opacity=0)
        w, h, alpha = _alpha(out)
        assert max(alpha(ix, iy) for iy in range(h) for ix in range(w)) == 0

    def test_color_is_the_high_byte_of_the_65535_triple(self, tmp_path):
        out = tmp_path / "s.png"
        box = render_stroke_png(out, 10, 10, 210, 10, rgb_65535=(65535, 0, 32896), width_pt=4)
        _, _, rgba = _rgba(out)
        assert rgba(round(_col_index(box, 100.0)), round(_row_index(box, 10.0))) == (
            255,
            0,
            128,
            255,
        )


class TestRejections:
    @pytest.mark.parametrize("width_pt", [0, -1, -0.5])
    def test_non_positive_width(self, tmp_path, width_pt):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, 100, 0, rgb_65535=MAROON, width_pt=width_pt)

    @pytest.mark.parametrize("opacity", [-0.1, 101, 1000])
    def test_out_of_range_opacity(self, tmp_path, opacity):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, 100, 0, rgb_65535=MAROON, opacity=opacity)

    @pytest.mark.parametrize("dash", ["wiggly", "", "DOTS", "solid ish", "none"])
    def test_unknown_dash_name(self, tmp_path, dash):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, 100, 0, rgb_65535=MAROON, dash=dash)

    @pytest.mark.parametrize("end", [(0, 0), (0.0000001, 0)])
    def test_zero_length_segment(self, tmp_path, end):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, end[0], end[1], rgb_65535=MAROON)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_inputs(self, tmp_path, bad):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, bad, 100, rgb_65535=MAROON)

    def test_absurdly_large_raster(self, tmp_path):
        with pytest.raises(ParameterError):
            render_stroke_png(tmp_path / "s.png", 0, 0, 20000, 20000, rgb_65535=MAROON)

    def test_nothing_written_when_rejected(self, tmp_path):
        out = tmp_path / "s.png"
        with pytest.raises(ParameterError):
            render_stroke_png(out, 0, 0, 100, 0, rgb_65535=MAROON, width_pt=0)
        assert not out.exists()


class TestDesignSystemStyles:
    """The eight semantic connector styles from the SDH visual identity."""

    @pytest.mark.parametrize(
        ("name", "style", "hex_color", "width_pt"),
        [
            ("config", "solid", (0, 0, 0), 5),
            ("logical", "dotted", (0, 0, 0), 3),
            ("auth", "solid", (51400, 51400, 51400), 3),
            ("data", "solid", MAROON, 5),
            ("dataReturn", "dotted", MAROON, 3),
            ("logStream", "dotted", (61937, 39578, 51400), 4),
            ("monitoring", "dotted", (19018, 37008, 55769), 4),
            ("denied", "dotted", (43690, 43690, 43690), 3),
        ],
    )
    def test_every_semantic_style_renders(self, tmp_path, name, style, hex_color, width_pt):
        out = tmp_path / f"{name}.png"
        box = render_stroke_png(
            out,
            200,
            300,
            600,
            300,
            rgb_65535=hex_color,
            width_pt=width_pt,
            dash=style,
            end_arrow=True,
        )
        w, _, alpha = _alpha(out)
        runs = _runs(alpha, w, round(_row_index(box, 300.0)))
        assert runs, f"{name} rendered no ink"
        if style == "solid":
            assert len(runs) == 1
        else:
            assert len(runs) >= 5, f"{name} should be visibly dotted"
