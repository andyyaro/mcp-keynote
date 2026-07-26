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
    # Superseded by [style.palette]: a design system names 9 accents, not 1.
    # Kept so existing style files keep loading; nothing reads it.
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

    # --- named vocabularies (Phase 9 Task 9) --------------------------------
    #
    # Added after trying to express a REAL design system (a 35-slide technical
    # architecture deck) as a style file and finding the flat 27-scalar schema
    # could carry 3 of its ~60 concepts. Each of these is a map, because the
    # design system names things - and the names ARE the design:
    #
    #   type       role -> {font, size, color}. 22 named type styles against 5
    #              element-keyed slots meant every text element re-specified a
    #              font/size/color triple that a role name carries once.
    #   palette    name -> hex. The deck's colours are referents ("zone.private",
    #              "accent.crimson"), not decoration; a single accent_color
    #              could not hold 20 of them.
    #   connectors name -> {color, width, dash}. Stroke style IS the semantics
    #              in an architecture diagram. Only expressible now that
    #              styled_line can render one.
    #   zones      name -> {x, y, width, height}. Named canvas bands (title,
    #              canvas, legend) that content must respect.
    #   modules    name -> {width, height, pitch, origin_x, origin_y}. An n-up
    #              grid with a real gutter, so "the 3rd account column" is a
    #              name rather than a hand-computed x.
    type: dict[str, dict[str, object]] = dataclasses.field(default_factory=dict)
    palette: dict[str, str] = dataclasses.field(default_factory=dict)
    connectors: dict[str, dict[str, object]] = dataclasses.field(default_factory=dict)
    zones: dict[str, dict[str, float]] = dataclasses.field(default_factory=dict)
    modules: dict[str, dict[str, float]] = dataclasses.field(default_factory=dict)
    # Identity metadata, so a built deck can record which revision made it.
    version: str = ""
    description: str = ""

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

    # --- named-vocabulary lookups -------------------------------------------

    def resolve_color(self, value: str) -> str:
        """Resolve a '@name' palette reference; pass anything else through.

        Lets an element say ``"color": "@zone.private"`` so the meaning is in
        the spec and the hex lives in one place.
        """
        if value.startswith("@"):
            key = value[1:]
            if key not in self.palette:
                raise ParameterError(
                    f"Unknown palette colour {value!r}. "
                    f"Style {self.name!r} defines: {sorted(self.palette) or '(none)'}"
                )
            return self.palette[key]
        return value

    def type_role(self, role: str) -> dict[str, object]:
        if role not in self.type:
            raise ParameterError(
                f"Unknown type role {role!r}. "
                f"Style {self.name!r} defines: {sorted(self.type) or '(none)'}"
            )
        return self.type[role]

    def connector(self, name: str) -> dict[str, object]:
        if name not in self.connectors:
            raise ParameterError(
                f"Unknown connector {name!r}. "
                f"Style {self.name!r} defines: {sorted(self.connectors) or '(none)'}"
            )
        return self.connectors[name]

    def module_origin(self, name: str, index: int) -> tuple[float, float, float, float]:
        """(x, y, width, height) of the index-th cell of a named grid module."""
        if name not in self.modules:
            raise ParameterError(
                f"Unknown grid module {name!r}. "
                f"Style {self.name!r} defines: {sorted(self.modules) or '(none)'}"
            )
        mod = self.modules[name]
        pitch = float(mod.get("pitch", mod.get("width", 0)))
        return (
            float(mod.get("origin_x", 0)) + pitch * (index - 1),
            float(mod.get("origin_y", 0)),
            float(mod.get("width", 0)),
            float(mod.get("height", 0)),
        )


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


# Fields whose TOML value is a table of named entries, not a scalar.
_MAP_FIELDS = {"type", "palette", "connectors", "zones", "modules"}

# What each named entry may contain. Keys outside these are rejected, so a
# misspelt "colour" fails loudly instead of being silently ignored - the same
# principle as the server's unknown-argument guard.
_MAP_ENTRY_KEYS: dict[str, set[str]] = {
    "type": {"font", "size", "color"},
    "connectors": {"color", "width", "dash", "start_arrow", "end_arrow", "meaning"},
    "zones": {"x", "y", "width", "height", "align"},
    "modules": {"width", "height", "pitch", "origin_x", "origin_y"},
}


def _validated_map(key: str, value: object, source: str) -> dict[str, object]:
    """Validate one named-vocabulary table."""
    if not isinstance(value, dict):
        raise ParameterError(
            f"Style {source}: [{key}] must be a table of named entries, got {type(value).__name__}"
        )
    if key == "palette":
        out: dict[str, object] = {}
        for name, hex_value in value.items():
            if not isinstance(hex_value, str):
                raise ParameterError(
                    f"Style {source}: palette.{name} must be a colour string, "
                    f"got {type(hex_value).__name__}"
                )
            out[name] = hex_value
        return out
    allowed = _MAP_ENTRY_KEYS[key]
    result: dict[str, object] = {}
    for name, entry in value.items():
        if not isinstance(entry, dict):
            raise ParameterError(
                f"Style {source}: [{key}.{name}] must be a table, got {type(entry).__name__}"
            )
        unknown = sorted(set(entry) - allowed)
        if unknown:
            raise ParameterError(
                f"Style {source}: [{key}.{name}] has unknown keys {unknown}; "
                f"valid: {sorted(allowed)}"
            )
        result[name] = dict(entry)
    return result


# Styles shipped as TOML rather than as Python literals, because they are large
# enough that a literal would be unreadable - and because shipping the same file
# format users write is the honest test of it.
_SHIPPED_STYLE_DIR = Path(__file__).resolve().parent.parent / "styles"


def _load_shipped_styles() -> None:
    """Register every .keynote-mcp.toml shipped inside the package."""
    if not _SHIPPED_STYLE_DIR.is_dir():
        return
    for path in sorted(_SHIPPED_STYLE_DIR.glob("*.keynote-mcp.toml")):
        try:
            style = load_style_file(path)
        except ParameterError:  # pragma: no cover - a shipped style is tested
            continue
        BUILTIN_STYLES[style.name or path.name.split(".")[0]] = style


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
    # Expected types come from the dataclass ANNOTATIONS, not the runtime
    # type of the default value: a float field with a whole-number default
    # (title_size = 66) stores an int, and typing against it would wrongly
    # reject a TOML `title_size = 70.5`.
    annotations = {f.name: f.type for f in dataclasses.fields(DeckStyle)}
    for key, value in data.items():
        if key == "extends":
            continue
        # Named vocabularies are TABLES, not scalars. The loader only accepted
        # str/float/int before, which is why a real design system could not be
        # expressed: its type roles, palette, connectors, zones and grid
        # modules are all maps.
        if key in _MAP_FIELDS:
            values[key] = _validated_map(key, value, source)
            continue
        expected: type = str if annotations[key] == "str" else float
        if annotations[key] == "int":
            expected = int
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if not isinstance(value, expected) or isinstance(value, bool):
            raise ParameterError(
                f"Style {source}: key {key!r} must be {expected.__name__}, "
                f"got {type(value).__name__}"
            )
        values[key] = value
    style = DeckStyle(**values)
    for color_field in _COLOR_FIELDS:
        parse_color(getattr(style, color_field))  # raises ParameterError if bad
    # Every colour in a named vocabulary is validated too, so a typo surfaces
    # when the style loads rather than mid-build on slide 23.
    for name, hex_value in style.palette.items():
        try:
            parse_color(hex_value)
        except ParameterError as e:
            raise ParameterError(f"Style {source}: palette.{name}: {e}") from None
    for role, spec in style.type.items():
        if "color" in spec:
            try:
                parse_color(style.resolve_color(str(spec["color"])))
            except ParameterError as e:
                raise ParameterError(f"Style {source}: type.{role}.color: {e}") from None
    for name, spec in style.connectors.items():
        if "color" in spec:
            try:
                parse_color(style.resolve_color(str(spec["color"])))
            except ParameterError as e:
                raise ParameterError(f"Style {source}: connectors.{name}.color: {e}") from None
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


# Shipped TOML styles register after the loader is defined.
_load_shipped_styles()
