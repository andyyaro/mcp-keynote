"""Deck style configuration.

A style names the typography, palette, and layout metrics every content tool
falls back to, so callers stop re-deriving coordinates and font choices per
deck. Resolution order (first hit wins):

1. An explicit ``style`` argument - a built-in name or a path to a TOML file.
2. ``.keynote-mcp.toml`` next to the deck's save path (or the cwd for tools
   that have no path in hand).
3. The built-in ``plain`` style, which imposes nothing beyond the existing
   tool defaults (the Keynote theme keeps styling text).

TOML files use the same keys as the ``DeckStyle`` fields, flat or under a
``[style]`` table. Colors are ``#RRGGBB`` hex or ``r,g,b`` (0-65535); empty
string means "leave it to the Keynote theme". Fractions are of the slide's
width/height so one style works at any slide size.
"""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .error_handler import ParameterError, parse_color

CONFIG_BASENAME = ".keynote-mcp.toml"


@dataclass(frozen=True)
class DeckStyle:
    """Complete styling contract consulted by content tools and build_deck."""

    name: str = "plain"
    keynote_theme: str = "White"
    width: int = 1920
    height: int = 1080
    # Typography. Empty font/color = leave the Keynote theme's default alone.
    title_font: str = ""
    title_size: float = 66
    title_color: str = ""
    subtitle_font: str = ""
    subtitle_size: float = 32
    subtitle_color: str = ""
    body_font: str = ""
    body_size: float = 24
    body_color: str = ""
    code_font: str = "Menlo"
    code_size: float = 18
    code_color: str = "#24292F"
    quote_font: str = ""
    quote_size: float = 34
    quote_color: str = ""
    accent_color: str = "#3B6ECC"
    # Layout metrics as fractions of slide width/height.
    margin_x_frac: float = 0.07
    margin_top_frac: float = 0.08
    margin_bottom_frac: float = 0.08
    gap_frac: float = 0.035
    # Tables.
    table_font: str = ""
    table_font_size: float = 18
    table_header_font_size: float = 18
    table_header_bg: str = "#2F4B7C"
    table_header_color: str = "#FFFFFF"
    # Rendered-image panels (add_colored_panel).
    panel_color: str = "#EDF1F7"
    panel_radius: int = 24

    # --- derived metrics -----------------------------------------------------

    def margin_x(self, slide_width: float) -> float:
        return round(slide_width * self.margin_x_frac)

    def margin_top(self, slide_height: float) -> float:
        return round(slide_height * self.margin_top_frac)

    def margin_bottom(self, slide_height: float) -> float:
        return round(slide_height * self.margin_bottom_frac)

    def gap(self, slide_height: float) -> float:
        return round(slide_height * self.gap_frac)

    def content_width(self, slide_width: float) -> float:
        return slide_width - 2 * self.margin_x(slide_width)


_FIELD_NAMES = {f.name for f in dataclasses.fields(DeckStyle)}
_COLOR_FIELDS = [f.name for f in dataclasses.fields(DeckStyle) if f.name.endswith("color")] + [
    "table_header_bg"
]

BUILTIN_STYLES: dict[str, DeckStyle] = {
    "plain": DeckStyle(name="plain"),
    # Corporate light: strong navy headings, generous margins, cool table headers.
    "boardroom": DeckStyle(
        name="boardroom",
        keynote_theme="White",
        title_font="Helvetica Neue Bold",
        title_size=64,
        title_color="#16294A",
        subtitle_font="Helvetica Neue",
        subtitle_size=30,
        subtitle_color="#44506B",
        body_font="Helvetica Neue",
        body_size=24,
        body_color="#222733",
        code_font="Menlo",
        code_size=17,
        code_color="#1F2A3C",
        quote_font="Helvetica Neue Light",
        quote_size=36,
        quote_color="#16294A",
        accent_color="#1F4E9E",
        table_font="Helvetica Neue",
        table_header_bg="#16294A",
        table_header_color="#FFFFFF",
        panel_color="#E8EDF6",
    ),
    # Dark stage deck: Black theme, warm accent, high-contrast text.
    "midnight": DeckStyle(
        name="midnight",
        keynote_theme="Black",
        title_font="Helvetica Neue Bold",
        title_size=68,
        title_color="#F5F6F8",
        subtitle_font="Helvetica Neue",
        subtitle_size=30,
        subtitle_color="#C8CCD6",
        body_font="Helvetica Neue",
        body_size=24,
        body_color="#E4E7EC",
        code_font="Menlo",
        code_size=17,
        code_color="#9ECE6A",
        quote_font="Helvetica Neue Light",
        quote_size=36,
        quote_color="#F5F6F8",
        accent_color="#E8A33D",
        table_font="Helvetica Neue",
        table_header_bg="#E8A33D",
        table_header_color="#141414",
        panel_color="#23262E",
    ),
    # Editorial serif: Georgia headings for report-style decks.
    "editorial": DeckStyle(
        name="editorial",
        keynote_theme="White",
        title_font="Georgia Bold",
        title_size=60,
        title_color="#232323",
        subtitle_font="Georgia Italic",
        subtitle_size=30,
        subtitle_color="#555555",
        body_font="Georgia",
        body_size=23,
        body_color="#2B2B2B",
        code_font="Menlo",
        code_size=16,
        code_color="#333333",
        quote_font="Georgia Italic",
        quote_size=38,
        quote_color="#6B3A2A",
        accent_color="#A2543C",
        table_font="Georgia",
        table_header_bg="#EFE9E3",
        table_header_color="#3A2A20",
        panel_color="#F5F1EC",
    ),
}


def _style_from_mapping(data: dict[str, object], source: str) -> DeckStyle:
    """Build a DeckStyle from a TOML mapping, validating keys and colors."""
    if "style" in data and isinstance(data["style"], dict):
        data = data["style"]
    base_name = data.get("extends", "plain")
    if not isinstance(base_name, str) or base_name not in BUILTIN_STYLES:
        raise ParameterError(f"Style {source}: 'extends' must be one of {sorted(BUILTIN_STYLES)}")
    values = dataclasses.asdict(BUILTIN_STYLES[base_name])
    unknown = [k for k in data if k not in _FIELD_NAMES and k != "extends"]
    if unknown:
        raise ParameterError(
            f"Style {source}: unknown keys {unknown}. Valid keys: {sorted(_FIELD_NAMES)}"
        )
    for key, value in data.items():
        if key == "extends":
            continue
        expected = type(values[key])
        if expected is float and isinstance(value, int):
            value = float(value)
        if not isinstance(value, expected):
            raise ParameterError(
                f"Style {source}: key {key!r} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )
        values[key] = value
    style = DeckStyle(**values)
    for color_field in _COLOR_FIELDS:
        parse_color(getattr(style, color_field))  # raises ParameterError if bad
    return style


def load_style_file(path: str | Path) -> DeckStyle:
    p = Path(path).expanduser()
    if not p.is_file():
        raise ParameterError(f"Style file not found: {p}")
    try:
        data = tomllib.loads(p.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ParameterError(f"Style file {p} is not valid TOML: {e}") from None
    return _style_from_mapping(data, str(p))


def resolve_style(style: str = "", near_path: str | Path = "") -> DeckStyle:
    """Resolve a style per the module-docstring order."""
    if style:
        if style in BUILTIN_STYLES:
            return BUILTIN_STYLES[style]
        if style.endswith(".toml") or "/" in style or style.startswith("~"):
            return load_style_file(style)
        raise ParameterError(
            f"Unknown style {style!r}. Built-ins: {sorted(BUILTIN_STYLES)}; or pass "
            "a path to a .toml style file."
        )
    if near_path:
        candidate = Path(near_path).expanduser()
        if candidate.suffix:
            candidate = candidate.parent
        config = candidate / CONFIG_BASENAME
        if config.is_file():
            return load_style_file(config)
    cwd_config = Path.cwd() / CONFIG_BASENAME
    if cwd_config.is_file():
        return load_style_file(cwd_config)
    return BUILTIN_STYLES["plain"]


def style_color(style: DeckStyle, field_name: str) -> tuple[int, int, int] | None:
    """Parsed RGB for a style color field (None when deferred to the theme)."""
    return parse_color(getattr(style, field_name))
