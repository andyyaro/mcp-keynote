"""Round-tripping for the rendered-image workarounds.

AppleScript cannot fill a shape or style a line, so panels and styled strokes
are pure-Python PNGs placed as images. That works going out, but it was
strictly one-way: ``describe_deck`` saw ``{"type": "image", "path":
"s1.e0.png"}`` and the colour, radius, dash and arrowheads were simply gone.
Worse, the PNG was written to a ``tempfile.mkdtemp`` that no longer exists by
read-back time, so a deck containing panels round-tripped to
``image file does not exist: s1.e0.png`` and could not be rebuilt at all.

The fix is to encode the parameters in the FILENAME. Keynote embeds the bitmap
into the .key bundle at insert time and keeps the basename, so the basename is
the one piece of metadata that survives everything - copying the deck, losing
the temp directory, even sending the file to another machine.

  kmcp-panel-EFA3A0-r24-o100.png
  kmcp-stroke-8E1F55-w3-dotted-ae.png

``describe_deck`` decodes that back into ``{"type": "panel", "color":
"#EFA3A0", ...}``, which ``build_deck`` RE-RENDERS. So the round trip needs no
durable file: the parameters are the source of truth, not the bitmap.
"""

from __future__ import annotations

import re
from typing import Any

_PREFIX = "kmcp"

# kmcp-panel-<hex>-r<radius>-o<opacity>
_PANEL_RE = re.compile(
    rf"^{_PREFIX}-panel-([0-9A-Fa-f]{{6}})-r(\d+(?:_\d+)?)-o(\d+(?:_\d+)?)(?:-[0-9a-z]+)?$"
)

# kmcp-stroke-<hex>-w<width>-<dash>-<arrows>-p<dx1>v<dy1>v<dx2>v<dy2>
#
# The endpoint OFFSETS are part of the name because the rendered box is padded
# by half a stroke width plus the arrowhead extent, so the image's x/y is NOT
# the line's start point. Storing offsets rather than absolute coordinates
# means the endpoints stay correct even if a user drags the image afterwards.
_STROKE_RE = re.compile(
    rf"^{_PREFIX}-stroke-([0-9A-Fa-f]{{6}})-w(\d+(?:_\d+)?)-([a-z]+)-([a-z]*)"
    rf"(?:-p(n?\d+(?:_\d+)?v n?\d+(?:_\d+)?v n?\d+(?:_\d+)?v n?\d+(?:_\d+)?))?"
    rf"(?:-[0-9a-z]+)?$".replace(" ", "")
)


def _num(value: float) -> str:
    """Format a number for a filename: 24 -> '24', 2.5 -> '2_5'."""
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):g}".replace(".", "_")


def _unnum(text: str) -> float:
    negative = text.startswith("n")
    value = float(text.lstrip("n").replace("_", "."))
    return -value if negative else value


def _signed(value: float) -> str:
    """Filename-safe signed number: -2.5 -> 'n2_5' (a '-' would split fields)."""
    text = _num(abs(value))
    return f"n{text}" if value < 0 else text


def panel_filename(hex_color: str, radius: float, opacity: float, unique: str = "") -> str:
    """Name a rendered panel so describe_deck can decode it."""
    stem = f"{_PREFIX}-panel-{hex_color.lstrip('#').upper()}-r{_num(radius)}-o{_num(opacity)}"
    return f"{stem}-{unique}.png" if unique else f"{stem}.png"


def stroke_filename(
    hex_color: str,
    width: float,
    dash: str,
    start_arrow: bool,
    end_arrow: bool,
    unique: str = "",
    offsets: tuple[float, float, float, float] | None = None,
) -> str:
    """Name a rendered stroke so describe_deck can decode it.

    ``offsets`` are the two endpoints relative to the rendered image's origin.
    Without them the read-back knows the stroke's STYLE but not where the line
    actually ran, and the deck cannot be rebuilt.
    """
    arrows = ("s" if start_arrow else "") + ("e" if end_arrow else "")
    stem = f"{_PREFIX}-stroke-{hex_color.lstrip('#').upper()}-w{_num(width)}-{dash}-{arrows}"
    if offsets is not None:
        stem += "-p" + "v".join(_signed(v) for v in offsets)
    return f"{stem}-{unique}.png" if unique else f"{stem}.png"


def decode_rendered_asset(basename: str) -> dict[str, Any] | None:
    """Recover the parameters of a rendered panel/stroke from its filename.

    Returns None for any image this server did not render, which must keep
    being reported as a plain image.
    """
    stem = basename.rsplit(".", 1)[0]

    match = _PANEL_RE.match(stem)
    if match:
        return {
            "type": "panel",
            "color": f"#{match.group(1).upper()}",
            "radius": _unnum(match.group(2)),
            "opacity": _unnum(match.group(3)),
            "rendered": True,
        }

    match = _STROKE_RE.match(stem)
    if match:
        arrows = match.group(4)
        decoded: dict[str, Any] = {
            "type": "styled_line",
            "color": f"#{match.group(1).upper()}",
            "stroke_width": _unnum(match.group(2)),
            "dash": match.group(3),
            "start_arrow": "s" in arrows,
            "end_arrow": "e" in arrows,
            "rendered": True,
        }
        if match.group(5):
            decoded["_endpoint_offsets"] = [_unnum(v) for v in match.group(5).split("v")]
        return decoded
    return None
