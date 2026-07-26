"""Native tables, charts, lines, rendered panels, and element styling.

Everything here was probed live against Keynote 14.5 before being built
(docs/CAPABILITY_MATRIX.md): native tables and the Compatibility-Suite
``add chart`` command work; shape fill color does not, hence the rendered
``add_colored_panel``.
"""

from __future__ import annotations

import os
import tempfile

from mcp.types import TextContent, Tool

from ..utils import (
    AppleScriptRunner,
    ParameterError,
    parse_color,
    validate_coordinates,
    validate_index,
    validate_number,
    validate_slide_number,
)
from ..utils.render import render_panel_png
from ..utils.styles import resolve_style
from .fragments import (
    RESOLVE_DOC,
    Argv,
    chart_fragment,
    image_fragment,
    line_fragment,
    run_single_fragment,
    table_fragment,
)

_DOC_ARG = {
    "type": "string",
    "description": "Document name (optional, defaults to front document)",
}

# Element classes addressable by the styling tools. Values are trusted
# literals - only these may be interpolated into AppleScript source.
_STYLE_ELEMENT_MAP = {
    "text": "text item",
    "image": "image",
    "shape": "shape",
    "line": "line",
}

_RANGE_UNIT_MAP = {
    "characters": "character",
    "words": "word",
    "paragraphs": "paragraph",
}


# One consistent routing signal on every element-creating primitive: with 59
# tools on the surface, a model asked for a 15-slide deck will otherwise chain
# ~5 of these per slide. They stay for editing; build_deck authors.
_EDIT_TAG = (
    " Edits an existing deck one element at a time; to author a deck (or add "
    "several slides at once) use build_deck, which builds all of them in one call."
)


class ObjectTools:
    """Native object tools built on the Phase A probe results."""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="add_table",
                description=(
                    "Add a NATIVE Keynote table filled from a 2-D data array "
                    "(rows of cells; strings, numbers, booleans; a string "
                    "starting with '=' becomes a live formula, e.g. '=SUM(B2:B4)'). "
                    "Keynote requires at least 2 rows and 2 columns. Header row "
                    "styling (background/text color, font) comes from the resolved "
                    "style unless overridden. Returns the table's index and settled "
                    "geometry. The table is fully editable in Keynote afterwards." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "data": {
                            "type": "array",
                            "items": {"type": "array"},
                            "description": (
                                'Rows of cell values, e.g. [["Region","Q1"],'
                                '["North",120]]. Minimum 2x2.'
                            ),
                        },
                        "x": {"type": "number", "description": "X in points (optional)"},
                        "y": {"type": "number", "description": "Y in points (optional)"},
                        "width": {"type": "number", "description": "Width in points (optional)"},
                        "height": {"type": "number", "description": "Height in points (optional)"},
                        "header_row": {
                            "type": "boolean",
                            "description": "First data row is a styled header (default true)",
                        },
                        "header_column": {
                            "type": "boolean",
                            "description": "First column is a header column (default false)",
                        },
                        "font_name": {"type": "string", "description": "Table font (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Cell font size in points (optional)",
                        },
                        "column_widths": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Per-column widths in points (optional)",
                        },
                        "style": {
                            "type": "string",
                            "description": (
                                "Style for header colors/fonts: built-in name "
                                "(plain/boardroom/midnight/editorial) or a "
                                ".toml path (optional; defaults to "
                                ".keynote-mcp.toml discovery)"
                            ),
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "data"],
                },
            ),
            Tool(
                name="add_chart",
                description=(
                    "Add a NATIVE Keynote chart (theme-styled, editable in "
                    "Keynote's UI). chart_type: bar, stacked_bar, horizontal_bar, "
                    "stacked_horizontal_bar, line, area, stacked_area, pie, "
                    "scatter, or any of those with a _3d suffix. data is rows "
                    "matching row_names, each row one value per column_name. "
                    "LIMIT (AppleScript has no chart-editing API): the chart's "
                    "data cannot be changed after creation - to update it, "
                    "delete_element the chart and add a new one. The tool "
                    "switches the document's current slide to the target slide "
                    "(required by Keynote, or nothing is created). Pie charts: "
                    "slices come from the axis you group by (one slice per "
                    "entry, using its first value); when only one axis has "
                    "multiple entries the tool groups by that axis "
                    "automatically." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "chart_type": {
                            "type": "string",
                            "description": "Chart type (see tool description)",
                        },
                        "row_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Name of each data row (series or category)",
                        },
                        "column_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Name of each data column",
                        },
                        "data": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "number"}},
                            "description": "Rows of numbers; shape [row_names x column_names]",
                        },
                        "group_by": {
                            "type": "string",
                            "enum": ["row", "column"],
                            "description": "Group series by data rows or columns (default row)",
                        },
                        "x": {"type": "number", "description": "X in points (optional)"},
                        "y": {"type": "number", "description": "Y in points (optional)"},
                        "width": {"type": "number", "description": "Width in points (optional)"},
                        "height": {"type": "number", "description": "Height in points (optional)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": [
                        "slide_number",
                        "chart_type",
                        "row_names",
                        "column_names",
                        "data",
                    ],
                },
            ),
            Tool(
                name="add_line",
                description=(
                    "Add a straight line from (x1,y1) to (x2,y2) in points. "
                    "Returns the line's index and settled geometry. (Keynote has "
                    "no scriptable connectors - endpoints are fixed coordinates.)" + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "x1": {"type": "number", "description": "Start X in points"},
                        "y1": {"type": "number", "description": "Start Y in points"},
                        "x2": {"type": "number", "description": "End X in points"},
                        "y2": {"type": "number", "description": "End Y in points"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "x1", "y1", "x2", "y2"],
                },
            ),
            Tool(
                name="add_colored_panel",
                description=(
                    "Add a solid-color (optionally rounded) rectangle panel. "
                    "IMPORTANT: this is a RENDERED PNG placed as an image, not a "
                    "native shape, because AppleScript cannot set shape fill "
                    "colors (read-only in Keynote's dictionary) - so the panel is "
                    "not recolorable inside Keynote afterwards, only "
                    "moved/resized/deleted like any image. Add panels BEFORE the "
                    "text that sits on them: z-order follows creation order and "
                    "cannot be changed via AppleScript." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "x": {"type": "number", "description": "X in points"},
                        "y": {"type": "number", "description": "Y in points"},
                        "width": {"type": "number", "description": "Width in points"},
                        "height": {"type": "number", "description": "Height in points"},
                        "color": {
                            "type": "string",
                            "description": (
                                "Fill color '#RRGGBB' or 'r,g,b' 0-65535 "
                                "(optional; defaults to the style's panel_color)"
                            ),
                        },
                        "radius": {
                            "type": "number",
                            "description": "Corner radius in points (optional; style default)",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Fill opacity 0-100 (optional, default 100)",
                        },
                        "style": {
                            "type": "string",
                            "description": "Style name or .toml path for defaults (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "x", "y", "width", "height"],
                },
            ),
            Tool(
                name="style_text_range",
                description=(
                    "Style a sub-range of an existing text item: color, font, "
                    "and/or size of characters, words, or paragraphs start..end "
                    "(1-based, inclusive). Bold/italic = pass the bold/italic "
                    "font face name (e.g. 'Helvetica-Bold') - Keynote's "
                    "dictionary has no style attribute, only the font name."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "item_index": {
                            "type": "integer",
                            "description": "Text item index (1-based, from add_*/get_slide_content)",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["characters", "words", "paragraphs"],
                            "description": "Range unit (default characters)",
                        },
                        "start": {"type": "integer", "description": "First unit (1-based)"},
                        "end": {"type": "integer", "description": "Last unit (inclusive)"},
                        "color": {
                            "type": "string",
                            "description": "'#RRGGBB' or 'r,g,b' 0-65535 (optional)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "font_size": {"type": "number", "description": "Size in points (optional)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "item_index", "start", "end"],
                },
            ),
            Tool(
                name="replace_image",
                description=(
                    "Replace an existing image's file in place, preserving its "
                    "position and size on the slide."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "image_index": {
                            "type": "integer",
                            "description": "Image index (1-based)",
                        },
                        "image_path": {
                            "type": "string",
                            "description": "Path to the replacement image file",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "image_index", "image_path"],
                },
            ),
            Tool(
                name="set_element_style",
                description=(
                    "Set rotation (0-359 degrees), reflection, and/or lock state "
                    "on a text item, image, shape, or line. Rotation/reflection "
                    "are not available on tables or charts (not in Keynote's "
                    "dictionary)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "enum": ["text", "image", "shape", "line"],
                            "description": "Element type",
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "rotation": {
                            "type": "number",
                            "description": "Rotation in degrees 0-359 (optional)",
                        },
                        "reflection_showing": {
                            "type": "boolean",
                            "description": "Show a reflection (optional)",
                        },
                        "reflection_value": {
                            "type": "number",
                            "description": "Reflection strength 0-100 (optional)",
                        },
                        "locked": {
                            "type": "boolean",
                            "description": "Lock the element against manual edits (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "element_type", "element_index"],
                },
            ),
        ]

    # ------------------------------------------------------------------ tools

    async def add_table(
        self,
        slide_number: int,
        data: list[list[object]],
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        header_row: bool = True,
        header_column: bool = False,
        font_name: str = "",
        font_size: float | None = None,
        column_widths: list[float] | None = None,
        style: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            x_pos, y_pos = validate_coordinates(x, y)
            deck_style = resolve_style(style)
            argv = Argv()
            argv.ref(doc_name)
            lines = table_fragment(
                argv,
                "TB",
                data,
                x=x_pos,
                y=y_pos,
                width=width,
                height=height,
                header_row=header_row,
                header_column=header_column,
                font_name=font_name or deck_style.table_font,
                font_size=font_size if font_size is not None else deck_style.table_font_size,
                header_font_size=deck_style.table_header_font_size,
                header_bg=parse_color(deck_style.table_header_bg),
                header_color=parse_color(deck_style.table_header_color),
                column_widths=column_widths,
            )
            index, pos, size = run_single_fragment(self.runner, doc_name, slide_number, argv, lines)
            rows, cols = len(data), len(data[0])
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added {rows}x{cols} table to slide {slide_number} "
                        f"(table index {index}) at ({pos.replace(',', ', ')}), "
                        f"size {size.replace(',', 'x')}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add table: {e}")]

    async def add_chart(
        self,
        slide_number: int,
        chart_type: str,
        row_names: list[str],
        column_names: list[str],
        data: list[list[float]],
        group_by: str = "row",
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            argv = Argv()
            argv.ref(doc_name)
            lines = chart_fragment(
                argv,
                "CH",
                chart_type=chart_type,
                row_names=row_names,
                column_names=column_names,
                data=data,
                group_by=group_by,
                x=x,
                y=y,
                width=width,
                height=height,
            )
            index, pos, size = run_single_fragment(self.runner, doc_name, slide_number, argv, lines)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added native {chart_type} chart to slide {slide_number} "
                        f"(chart index {index}) at ({pos.replace(',', ', ')}), "
                        f"size {size.replace(',', 'x')}. Note: chart data is "
                        "write-once - delete and re-add to change it."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add chart: {e}")]

    async def add_line(
        self,
        slide_number: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            argv = Argv()
            argv.ref(doc_name)
            lines = line_fragment("LN", x1=x1, y1=y1, x2=x2, y2=y2)
            index, _pos, _size = run_single_fragment(
                self.runner, doc_name, slide_number, argv, lines
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added line to slide {slide_number} (line index {index}) "
                        f"from ({x1:g}, {y1:g}) to ({x2:g}, {y2:g})"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add line: {e}")]

    async def add_colored_panel(
        self,
        slide_number: int,
        x: float,
        y: float,
        width: float,
        height: float,
        color: str = "",
        radius: float | None = None,
        opacity: float = 100,
        style: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            deck_style = resolve_style(style)
            rgb = parse_color(color or deck_style.panel_color)
            if rgb is None:  # pragma: no cover - panel_color always set
                raise ParameterError("Panel color could not be resolved.")
            corner = radius if radius is not None else deck_style.panel_radius
            validate_number(corner, "radius", minimum=0, maximum=500)
            validate_number(opacity, "opacity", minimum=0, maximum=100)
            tmp_dir = tempfile.mkdtemp(prefix="keynote-mcp-panel-")
            png_path = os.path.join(tmp_dir, "panel.png")
            render_panel_png(png_path, width, height, rgb, corner, opacity)
            argv = Argv()
            argv.ref(doc_name)
            lines = image_fragment(
                argv,
                "PN",
                png_path,
                x=x,
                y=y,
                width=width,
                height=height,
                description="colored panel",
            )
            index, pos, size = run_single_fragment(self.runner, doc_name, slide_number, argv, lines)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added colored panel to slide {slide_number} (image index "
                        f"{index}) at ({pos.replace(',', ', ')}), size "
                        f"{size.replace(',', 'x')}. Rendered PNG, not a native "
                        "shape - recolor by replacing it, not in Keynote."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add colored panel: {e}")]

    async def style_text_range(
        self,
        slide_number: int,
        item_index: int,
        start: int,
        end: int,
        unit: str = "characters",
        color: str = "",
        font_name: str = "",
        font_size: float | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            validate_index(item_index, "item_index")
            validate_index(start, "start")
            validate_index(end, "end")
            if end < start:
                raise ParameterError(f"end ({end}) must be >= start ({start}).")
            if unit not in _RANGE_UNIT_MAP:
                raise ParameterError(
                    f"Invalid unit {unit!r}. Must be one of {sorted(_RANGE_UNIT_MAP)}."
                )
            rgb = parse_color(color)
            if rgb is None and not font_name and font_size is None:
                raise ParameterError(
                    "Nothing to style: pass at least one of color/font_name/font_size."
                )
            unit_cls = _RANGE_UNIT_MAP[unit]
            range_expr = f"{unit_cls}s {start} thru {end} of object text of text item {item_index}"
            ops = []
            if font_name:
                ops.append(f"set font of {range_expr} to (item 2 of argv)")
            if font_size is not None:
                validate_number(font_size, "font_size", minimum=1, maximum=500)
                size_val = int(font_size) if float(font_size).is_integer() else font_size
                ops.append(f"set size of {range_expr} to {size_val}")
            if rgb:
                ops.append(f"set color of {range_expr} to {{{rgb[0]}, {rgb[1]}, {rgb[2]}}}")
            body = "\n".join(ops)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        tell slide {slide_number} of targetDoc
                            {body}
                        end tell
                    end tell
                end run
                """,
                doc_name,
                font_name,
            )
            what = ", ".join(
                w
                for w, on in (
                    (f"font={font_name}", bool(font_name)),
                    (f"size={font_size:g}" if font_size is not None else "", font_size is not None),
                    (f"color={color}", bool(rgb)),
                )
                if on
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Styled {unit} {start}-{end} of text item {item_index} on "
                        f"slide {slide_number} ({what})"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to style text range: {e}")]

    async def replace_image(
        self,
        slide_number: int,
        image_index: int,
        image_path: str,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            validate_index(image_index, "image_index")
            image_path = os.path.realpath(os.path.expanduser(image_path))
            if not os.path.isfile(image_path):
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to replace image: file does not exist: {image_path}",
                    )
                ]
            # The bare-text form of `file name` raises -1703; POSIX file works
            # and preserves geometry (probed live).
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set imagePath to item 2 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        tell slide {slide_number} of targetDoc
                            if not (exists image {image_index}) then
                                error "No image at index {image_index}" number -1719
                            end if
                            set file name of image {image_index} to POSIX file imagePath
                        end tell
                    end tell
                end run
                """,
                doc_name,
                image_path,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Replaced image {image_index} on slide {slide_number} with "
                        f"{os.path.basename(image_path)} (geometry preserved)"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to replace image: {e}")]

    async def set_element_style(
        self,
        slide_number: int,
        element_type: str,
        element_index: int,
        rotation: float | None = None,
        reflection_showing: bool | None = None,
        reflection_value: float | None = None,
        locked: bool | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            validate_index(element_index, "element_index")
            if element_type not in _STYLE_ELEMENT_MAP:
                raise ParameterError(
                    f"Invalid element type {element_type!r}. "
                    f"Must be one of {sorted(_STYLE_ELEMENT_MAP)}."
                )
            cls = _STYLE_ELEMENT_MAP[element_type]
            ops = []
            changes = []
            if rotation is not None:
                validate_number(rotation, "rotation", minimum=0, maximum=359)
                ops.append(f"set rotation of targetItem to {int(rotation)}")
                changes.append(f"rotation={int(rotation)}")
            if reflection_showing is not None:
                flag = "true" if reflection_showing else "false"
                ops.append(f"set reflection showing of targetItem to {flag}")
                changes.append(f"reflection_showing={flag}")
            if reflection_value is not None:
                validate_number(reflection_value, "reflection_value", minimum=0, maximum=100)
                ops.append(f"set reflection value of targetItem to {int(reflection_value)}")
                changes.append(f"reflection_value={int(reflection_value)}")
            if locked is not None:
                flag = "true" if locked else "false"
                ops.append(f"set locked of targetItem to {flag}")
                changes.append(f"locked={flag}")
            if not ops:
                raise ParameterError(
                    "Nothing to set: pass at least one of rotation/"
                    "reflection_showing/reflection_value/locked."
                )
            body = "\n".join(ops)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        tell slide {slide_number} of targetDoc
                            if not (exists {cls} {element_index}) then
                                error "No {cls} at index {element_index}" number -1719
                            end if
                            set targetItem to {cls} {element_index}
                            {body}
                        end tell
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Styled {element_type} {element_index} on slide "
                        f"{slide_number}: {', '.join(changes)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set element style: {e}")]
