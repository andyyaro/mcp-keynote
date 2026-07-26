"""PHASE 9 Task 5 — rendered elements must round-trip.

Panels and styled strokes are PNGs because AppleScript can neither fill a shape
nor style a line. That was strictly one-way: describe_deck saw
``{"type": "image", "path": "s1.e0.png"}`` and the colour, radius, dash and
arrowheads were gone. Worse, the PNG lived in a tempfile.mkdtemp that no longer
existed by read-back time, so a deck containing panels rebuilt to
``image file does not exist: s1.e0.png``.

The parameters therefore live in the FILENAME: Keynote embeds the bitmap and
keeps the basename, so the basename is the one thing that survives losing the
temp directory, copying the deck, or moving it to another machine. build_deck
re-renders from the decoded parameters, so no durable file is needed at all.
"""

from __future__ import annotations

import pytest

from keynote_mcp.utils.rendered_assets import (
    decode_rendered_asset,
    panel_filename,
    stroke_filename,
)


class TestPanelRoundTrip:
    @pytest.mark.parametrize(
        ("color", "radius", "opacity"),
        [
            ("#EFA3A0", 24, 100),  # the real deck's salmon
            ("#8E1F55", 0, 80),  # its maroon, square corners
            ("#A8C6DE", 16, 55),
            ("#000000", 500, 0),
        ],
    )
    def test_parameters_survive_the_filename(
        self, color: str, radius: float, opacity: float
    ) -> None:
        decoded = decode_rendered_asset(panel_filename(color, radius, opacity))
        assert decoded is not None
        assert decoded["type"] == "panel"
        assert decoded["color"] == color.upper()
        assert decoded["radius"] == radius
        assert decoded["opacity"] == opacity

    def test_uniquifier_does_not_break_decoding(self) -> None:
        """build_deck appends a per-element tag so two panels on one slide do
        not collide; it must not confuse the decoder."""
        decoded = decode_rendered_asset(panel_filename("#EFA3A0", 12, 90, "s3e11"))
        assert decoded is not None
        assert decoded["color"] == "#EFA3A0"
        assert decoded["radius"] == 12

    def test_fractional_radius(self) -> None:
        decoded = decode_rendered_asset(panel_filename("#123456", 2.5, 100))
        assert decoded is not None
        assert decoded["radius"] == 2.5


class TestStrokeRoundTrip:
    @pytest.mark.parametrize("dash", ["solid", "dash", "dashed", "dot", "dotted", "dashdot"])
    def test_every_dash_style_survives(self, dash: str) -> None:
        decoded = decode_rendered_asset(stroke_filename("#830041", 3, dash, False, True))
        assert decoded is not None
        assert decoded["type"] == "styled_line"
        assert decoded["dash"] == dash
        assert decoded["color"] == "#830041"
        assert decoded["stroke_width"] == 3

    @pytest.mark.parametrize(
        ("start", "end"), [(False, False), (True, False), (False, True), (True, True)]
    )
    def test_arrowheads_survive(self, start: bool, end: bool) -> None:
        decoded = decode_rendered_asset(stroke_filename("#000000", 2, "solid", start, end))
        assert decoded is not None
        assert decoded["start_arrow"] is start
        assert decoded["end_arrow"] is end

    def test_endpoint_offsets_survive_including_negatives(self) -> None:
        """The rendered box is padded by half a stroke width plus the arrowhead,
        so the image's x/y is NOT the line's start point."""
        name = stroke_filename(
            "#8E1F55", 4, "solid", False, True, offsets=(2.0, -3.5, 802.0, 40.25)
        )
        decoded = decode_rendered_asset(name)
        assert decoded is not None
        assert decoded["_endpoint_offsets"] == [2.0, -3.5, 802.0, 40.25]

    def test_offsets_are_optional(self) -> None:
        decoded = decode_rendered_asset(stroke_filename("#000000", 1, "dotted", False, False))
        assert decoded is not None
        assert "_endpoint_offsets" not in decoded

    def test_uniquifier_with_offsets(self) -> None:
        name = stroke_filename("#EFA3A0", 3, "dashed", True, True, "s2e7", (1.0, 1.0, 500.0, 1.0))
        decoded = decode_rendered_asset(name)
        assert decoded is not None
        assert decoded["dash"] == "dashed"
        assert decoded["_endpoint_offsets"] == [1.0, 1.0, 500.0, 1.0]


class TestForeignImagesAreLeftAlone:
    @pytest.mark.parametrize(
        "basename",
        [
            "pasted-movie.png",  # the real deck's 61 identical names
            "photo.jpg",
            "kmcp-notes.png",  # looks like ours, is not
            "kmcp-panel.png",  # missing every parameter
            "kmcp-panel-ZZZZZZ-r1-o1.png",  # not hex
            "kmcp-stroke-8E1F55.png",  # truncated
            "",
        ],
    )
    def test_returns_none_so_it_stays_a_plain_image(self, basename: str) -> None:
        assert decode_rendered_asset(basename) is None
