"""Native tables, charts, lines, rendered panels, and element styling.

Everything here was probed live against Keynote 14.5 before being built
(docs/CAPABILITY_MATRIX.md): native tables and the Compatibility-Suite
``add chart`` command work; shape fill color does not, hence the rendered
``add_colored_panel``.
"""

from __future__ import annotations

import os
import re
import tempfile

from mcp.types import TextContent, Tool

from ..utils import (
    AppleScriptRunner,
    ParameterError,
    parse_color,
    rgb65535_to_hex,
    validate_coordinates,
    validate_index,
    validate_number,
    validate_slide_number,
)
from ..utils.render import render_panel_png
from ..utils.rendered_assets import panel_filename, stroke_filename
from ..utils.stroke import render_stroke_png
from ..utils.styles import resolve_style
from .base import DocumentTargetedTools
from .fragments import (
    RESOLVE_DOC,
    Argv,
    _fmt_num,
    cell_value_expr,
    chart_fragment,
    exists_guard,
    image_fragment,
    line_fragment,
    parse_cell,
    parse_range,
    range_name,
    run_single_fragment,
    table_fragment,
)

_DOC_ARG = {
    "type": "string",
    "description": "Document name. Optional: defaults to the session document set by the last create_presentation/open_presentation, or to the only open presentation. With several open and no session default, the call fails and names them rather than guessing.",
}

# Element classes addressable by the styling tools. Values are trusted
# literals - only these may be interpolated into AppleScript source.
_STYLE_ELEMENT_MAP = {
    "text": "text item",
    "image": "image",
    "shape": "shape",
    "line": "line",
}

# Table range enums: trusted literals, the only values interpolated.
_TABLE_ALIGN_MAP = {
    "left": "left",
    "center": "center",
    "right": "right",
    "justify": "justify",
    "auto": "auto align",
}
_TABLE_VALIGN_MAP = {"top": "top", "center": "center", "bottom": "bottom"}
_TABLE_FORMAT_MAP = {
    "automatic": "automatic",
    "number": "number",
    "currency": "currency",
    "percent": "percent",
    "scientific": "scientific",
    "fraction": "fraction",
    "text": "text",
    "date_and_time": "date and time",
    "duration": "duration",
}
# Keynote keeps at least one body row/column beside the header/footer counts.
_MIN_BODY_ROWS = 1
_MIN_BODY_COLUMNS = 1
# Upper bound for one edit_table session, however many cells it writes.
_EDIT_TABLE_MAX_TIMEOUT = 300.0

_TABLE_STYLE_KEYS = frozenset(
    {
        "range",
        "font_name",
        "font_size",
        "text_color",
        "background_color",
        "alignment",
        "vertical_alignment",
        "wrap",
        "format",
    }
)

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


class ObjectTools(DocumentTargetedTools):
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
                name="edit_table",
                description=(
                    "Edit an EXISTING native table in place: write cell values, "
                    "grow or shrink it, change header/footer row counts, clear, "
                    "sort, merge/unmerge, style ranges (font, size, text and "
                    "background color, horizontal/vertical alignment, wrap, "
                    "number format) and set column widths/row heights. Pass only "
                    "what should change. Steps run in this order: size, header "
                    "counts, clear, values, sort, unmerge, merge, styles, "
                    "widths/heights; if one fails, the earlier ones stay applied "
                    "and the reply names the failed step. Ranges use A1 notation "
                    "('A1:C1', or 'B2' for one cell) and are checked against the "
                    "table's size after resizing. Shrinking deletes rows/columns "
                    "from the end, contents included. Columns added later do not "
                    "pick up add_table's header colors: style them explicitly. "
                    "table_index is the table's position among the slide's "
                    "tables (see get_slide_content)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "table_index": {
                            "type": "integer",
                            "description": "1-based index among the slide's tables",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "array"},
                            "description": (
                                "Rows of cell values written from start_cell. null "
                                "leaves a cell unchanged, '' empties it, a string "
                                "starting '=' is a formula. Rows may differ in length."
                            ),
                        },
                        "start_cell": {
                            "type": "string",
                            "description": "Top-left cell for values (default 'A1')",
                        },
                        "row_count": {
                            "type": "integer",
                            "description": "New total row count, min 2 (optional)",
                        },
                        "column_count": {
                            "type": "integer",
                            "description": "New total column count, min 2 (optional)",
                        },
                        "header_rows": {
                            "type": "integer",
                            "description": "Number of header rows (optional)",
                        },
                        "header_columns": {
                            "type": "integer",
                            "description": "Number of header columns (optional)",
                        },
                        "footer_rows": {
                            "type": "integer",
                            "description": "Number of footer rows (optional)",
                        },
                        "clear": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ranges to clear, contents AND formatting",
                        },
                        "sort": {
                            "type": "object",
                            "description": (
                                "Sort body rows: {column: 'B' or 2, direction: "
                                "'ascending'|'descending' (default ascending), rows?: "
                                "'A2:C9' to limit the sort}. Header rows stay in place."
                            ),
                        },
                        "unmerge": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ranges whose merged cells are split",
                        },
                        "merge": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ranges to merge, e.g. ['A1:C1']",
                        },
                        "styles": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "Range styles: [{range: 'A1:C1', font_name?, "
                                "font_size?, text_color?, background_color? (#RRGGBB "
                                "or r,g,b), alignment? (left/center/right/justify/"
                                "auto), vertical_alignment? (top/center/bottom), "
                                "wrap? (bool), format? (automatic/number/currency/"
                                "percent/scientific/fraction/text/date_and_time/"
                                "duration)}]"
                            ),
                        },
                        "column_widths": {
                            "type": "array",
                            "items": {"type": ["number", "null"]},
                            "description": "Per-column widths in points; null skips",
                        },
                        "row_heights": {
                            "type": "array",
                            "items": {"type": ["number", "null"]},
                            "description": "Per-row heights in points; null skips",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "table_index"],
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
                    "cannot be changed via AppleScript. The colour, radius and "
                    "opacity are encoded in the PNG's filename, so describe_deck "
                    "reports it back as type:'panel' with those values rather "
                    "than as an anonymous image, and build_deck re-renders it - "
                    "the round trip needs no durable file." + _EDIT_TAG
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
                name="styled_line",
                description=(
                    "Draw a connector whose COLOR, WIDTH, DASH PATTERN and "
                    "ARROWHEADS carry meaning - dotted black for an invocation, "
                    "solid maroon for a data path, dotted pink for a denied path. "
                    "Use this instead of add_line whenever the stroke means "
                    "something. Keynote's AppleScript has NO stroke API at all "
                    "(a line's whole property record is its two endpoints, "
                    "geometry, rotation, reflection and locked), so this renders "
                    "the stroke to a transparent PNG and places it, the same way "
                    "add_colored_panel handles fills. The result is an IMAGE, not "
                    "an editable Keynote line - but its parameters are encoded in "
                    "its filename, so describe_deck reports it back as a "
                    "styled_line and build_deck re-renders it. Use add_line for a "
                    "plain native divider you want to be editable in Keynote."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "x1": {"type": "number", "description": "Start X in points"},
                        "y1": {"type": "number", "description": "Start Y in points"},
                        "x2": {"type": "number", "description": "End X in points"},
                        "y2": {"type": "number", "description": "End Y in points"},
                        "color": {
                            "type": "string",
                            "description": "Stroke color as #RRGGBB or 'r,g,b' 0-65535 (default black)",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": (
                                "Stroke thickness in points (default 2). Below ~0.5pt "
                                "cannot be resolved at the 2 px/pt render scale and is "
                                "clamped to a hairline rather than vanishing."
                            ),
                        },
                        "dash": {
                            "type": "string",
                            "enum": [
                                "solid",
                                "dash",
                                "dashed",
                                "dot",
                                "dotted",
                                "dashdot",
                                "dash-dot",
                            ],
                            "description": "Dash pattern (default solid). Scales with stroke_width.",
                        },
                        "start_arrow": {
                            "type": "boolean",
                            "description": "Arrowhead at the start point (default false)",
                        },
                        "end_arrow": {
                            "type": "boolean",
                            "description": "Arrowhead at the end point (default false)",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "0-100 (default 100)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "x1", "y1", "x2", "y2"],
                },
            ),
            Tool(
                name="style_text_range",
                description=(
                    "Style a sub-range of an existing text item: color, font, "
                    "and/or size of characters, words, or paragraphs start..end "
                    "(1-based, inclusive). Bold/italic = pass the bold/italic "
                    "font face name (e.g. 'Helvetica-Bold') - Keynote's "
                    "dictionary has no style attribute, only the font name. "
                    "describe_deck reads the result back as the text item's "
                    "`runs`, and build_deck accepts `runs` on a text element - so "
                    "when you are AUTHORING a mixed-colour heading, put the runs "
                    "in the spec instead of calling this three times afterwards; "
                    "this tool is for editing text that already exists. The item "
                    "index comes from get_slide_content or describe_deck; an "
                    "index that is not on the slide is rejected (-1719) rather "
                    "than applied to a different element. Re-setting the item's "
                    "text (edit_text_item) discards every run."
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
            doc_slot = argv.reserve_doc()
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
            # Resolved AFTER the fragment builder has validated its
            # arguments, so invalid input never spends an Apple event and
            # never reports a document-ambiguity error in its place.
            doc_name = self._doc(doc_name)
            argv.fill(doc_slot, doc_name)
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

    async def edit_table(
        self,
        slide_number: int,
        table_index: int,
        values: list[list[object]] | None = None,
        start_cell: str = "A1",
        row_count: int | None = None,
        column_count: int | None = None,
        header_rows: int | None = None,
        header_columns: int | None = None,
        footer_rows: int | None = None,
        clear: list[str] | None = None,
        sort: dict[str, object] | None = None,
        unmerge: list[str] | None = None,
        merge: list[str] | None = None,
        styles: list[dict[str, object]] | None = None,
        column_widths: list[float | None] | None = None,
        row_heights: list[float | None] | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        try:
            validate_slide_number(slide_number)
            validate_index(table_index, "table_index")
            for name, count in (("row_count", row_count), ("column_count", column_count)):
                if count is not None:
                    validate_number(count, name, minimum=2, maximum=10000)
            for name, count in (
                ("header_rows", header_rows),
                ("header_columns", header_columns),
                ("footer_rows", footer_rows),
            ):
                if count is not None:
                    validate_number(count, name, minimum=0, maximum=10000)
            if not any(
                v is not None
                for v in (
                    values,
                    row_count,
                    column_count,
                    header_rows,
                    header_columns,
                    footer_rows,
                    clear,
                    sort,
                    unmerge,
                    merge,
                    styles,
                    column_widths,
                    row_heights,
                )
            ):
                raise ParameterError("Nothing to edit: pass at least one change.")

            doc_name = self._doc(doc_name)
            # Ranges are checked against the size the table will have, which
            # needs its current size first.
            current = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        {exists_guard("table", table_index, slide_number)}
                        tell table {table_index} of slide {slide_number} of targetDoc
                            return (row count as text) & "," & (column count as text) & ¬
                                "," & (header row count as text) & "," & ¬
                                (header column count as text) & "," & ¬
                                (footer row count as text)
                        end tell
                    end tell
                end run
                """,
                doc_name,
            )
            cur_rows, cur_cols, cur_hr, cur_hc, cur_fr = (int(v) for v in current.split(","))
            rows = int(row_count) if row_count is not None else cur_rows
            cols = int(column_count) if column_count is not None else cur_cols
            # Header/footer counts are checked against the size the table will
            # have, like every range: Keynote either refuses or clamps a count
            # the table cannot hold, and the reply must not claim a count the
            # document does not have.
            new_hr = int(header_rows) if header_rows is not None else cur_hr
            new_hc = int(header_columns) if header_columns is not None else cur_hc
            new_fr = int(footer_rows) if footer_rows is not None else cur_fr
            if new_hr + new_fr > rows - _MIN_BODY_ROWS:
                raise ParameterError(
                    f"{new_hr} header row(s) + {new_fr} footer row(s) leave fewer than "
                    f"{_MIN_BODY_ROWS} body row(s) in a {rows}-row table."
                )
            if new_hc > cols - _MIN_BODY_COLUMNS:
                raise ParameterError(
                    f"{new_hc} header column(s) leave fewer than {_MIN_BODY_COLUMNS} body "
                    f"column(s) in a {cols}-column table."
                )

            def in_bounds(ref: object, what: str) -> str:
                r1, c1, r2, c2 = parse_range(ref, what)
                if r2 > rows or c2 > cols:
                    raise ParameterError(f"{what}: {ref!r} is outside the {rows}x{cols} table.")
                return range_name(r1, c1, r2, c2)

            argv = Argv()
            argv.ref(doc_name)
            steps: list[tuple[str, list[str]]] = []
            done: list[str] = []

            size_ops = []
            if row_count is not None:
                size_ops.append(f"set row count to {rows}")
            if column_count is not None:
                size_ops.append(f"set column count to {cols}")
            counts = [
                f"set {prop} to {int(val)}"
                for prop, val in (
                    ("header row count", header_rows),
                    ("header column count", header_columns),
                    ("footer row count", footer_rows),
                )
                if val is not None
            ]
            shrinking = rows < cur_rows or cols < cur_cols
            for kind in ("counts", "size") if shrinking else ("size", "counts"):
                if kind == "size" and size_ops:
                    steps.append(("size", size_ops))
                    done.append(f"size {cur_rows}x{cur_cols} -> {rows}x{cols}")
                elif kind == "counts" and counts:
                    steps.append(("header counts", counts))

            for i, ref in enumerate(clear or []):
                name = in_bounds(ref, f"clear[{i}]")
                steps.append((f"clear {name}", [f'clear range "{name}"']))
                done.append(f"cleared {name}")

            if values is not None:
                if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
                    raise ParameterError("values must be a list of rows (lists).")
                r0, c0 = parse_cell(start_cell or "A1", "start_cell")
                ops, written = [], 0
                for dr, row in enumerate(values):
                    for dc, cell in enumerate(row):
                        if cell is None:
                            continue
                        r, c = r0 + dr, c0 + dc
                        if r > rows or c > cols:
                            raise ParameterError(
                                f"values[{dr}][{dc}] lands on "
                                f"{range_name(r, c, r, c).partition(':')[0]} outside the {rows}x{cols} table; grow it with "
                                "row_count/column_count."
                            )
                        expr = "missing value" if cell == "" else cell_value_expr(argv, cell)
                        ops.append(f"set value of cell {c} of row {r} to {expr}")
                        written += 1
                if ops:
                    steps.append(("values", ops))
                done.append(f"{written} cell(s) written")

            if sort is not None:
                if not isinstance(sort, dict) or "column" not in sort:
                    raise ParameterError("sort needs {column: 'B' or 2, direction?, rows?}.")
                unknown = set(sort) - {"column", "direction", "rows"}
                if unknown:
                    raise ParameterError(f"sort: unknown keys {sorted(unknown)}.")
                col_ref = sort["column"]
                if isinstance(col_ref, str):
                    if not re.fullmatch(r"[A-Za-z]{1,3}", col_ref.strip()):
                        raise ParameterError(
                            f"sort.column must be a column letter or number, got {col_ref!r}."
                        )
                    _, sort_col = parse_cell(f"{col_ref.strip()}1", "sort.column")
                else:
                    validate_index(col_ref, "sort.column")  # type: ignore[arg-type]
                    sort_col = int(col_ref)  # type: ignore[call-overload]
                if sort_col > cols:
                    raise ParameterError(f"sort.column {col_ref!r} is outside the table.")
                direction = str(sort.get("direction", "ascending"))
                if direction not in ("ascending", "descending"):
                    raise ParameterError("sort.direction must be 'ascending' or 'descending'.")
                clause = f"sort by column {sort_col} direction {direction}"
                if sort.get("rows"):
                    clause += f' in rows (range "{in_bounds(sort["rows"], "sort.rows")}")'
                steps.append(("sort", [clause]))
                done.append(f"sorted by column {sort_col} {direction}")

            for label, refs, verb in (("unmerge", unmerge, "unmerge"), ("merge", merge, "merge")):
                for i, ref in enumerate(refs or []):
                    name = in_bounds(ref, f"{label}[{i}]")
                    steps.append((f"{verb} {name}", [f'{verb} range "{name}"']))
                    done.append(f"{verb}d {name}")

            for i, st in enumerate(styles or []):
                where = f"styles[{i}]"
                if not isinstance(st, dict) or "range" not in st:
                    raise ParameterError(f"{where} needs a 'range'.")
                unknown = set(st) - _TABLE_STYLE_KEYS
                if unknown:
                    raise ParameterError(
                        f"{where}: unknown keys {sorted(unknown)}; accepted: "
                        f"{sorted(_TABLE_STYLE_KEYS)}."
                    )
                name = in_bounds(st["range"], f"{where}.range")
                target = f'range "{name}"'
                ops = []
                if st.get("font_name"):
                    ops.append(f"set font name of {target} to {argv.ref(str(st['font_name']))}")
                if st.get("font_size") is not None:
                    size = st["font_size"]
                    validate_number(size, f"{where}.font_size", minimum=1, maximum=200)  # type: ignore[arg-type]
                    ops.append(f"set font size of {target} to {_fmt_num(float(size))}")  # type: ignore[arg-type]
                for key, prop in (
                    ("text_color", "text color"),
                    ("background_color", "background color"),
                ):
                    if st.get(key):
                        rgb = parse_color(str(st[key]))
                        if rgb:
                            ops.append(
                                f"set {prop} of {target} to {{{rgb[0]}, {rgb[1]}, {rgb[2]}}}"
                            )
                for key, prop, mapping in (
                    ("alignment", "alignment", _TABLE_ALIGN_MAP),
                    ("vertical_alignment", "vertical alignment", _TABLE_VALIGN_MAP),
                    ("format", "format", _TABLE_FORMAT_MAP),
                ):
                    if st.get(key) is not None:
                        if st[key] not in mapping:
                            raise ParameterError(
                                f"{where}.{key}: {st[key]!r}; valid: {sorted(mapping)}."
                            )
                        ops.append(f"set {prop} of {target} to {mapping[str(st[key])]}")
                if st.get("wrap") is not None:
                    if not isinstance(st["wrap"], bool):
                        raise ParameterError(f"{where}.wrap must be true or false.")
                    ops.append(f"set text wrap of {target} to {'true' if st['wrap'] else 'false'}")
                if not ops:
                    raise ParameterError(f"{where} sets nothing besides its range.")
                steps.append((f"style {name}", ops))
                done.append(f"styled {name}")

            for label, sizes, limit, element in (
                ("column_widths", column_widths, cols, "column"),
                ("row_heights", row_heights, rows, "row"),
            ):
                if not sizes:
                    continue
                if len(sizes) > limit:
                    raise ParameterError(
                        f"{label} has {len(sizes)} entries for {limit} {element}s."
                    )
                prop = "width" if element == "column" else "height"
                ops = []
                for n, size in enumerate(sizes, start=1):
                    if size is not None:
                        validate_number(size, f"{label}[{n - 1}]", minimum=1)
                        ops.append(f"set {prop} of {element} {n} to {_fmt_num(size)}")
                if ops:
                    steps.append((label, ops))
                    done.append(f"{label} set")

            if not steps:
                raise ParameterError("Nothing to edit: every change passed was empty.")
            body = []
            n_ops = 0
            for label, ops in steps:
                n_ops += len(ops)
                # Labels are built from validated integers and literals only.
                body.append(f'set stepName to "{label}"')
                body += ops
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        set targetTable to table {table_index} of slide {slide_number} of targetDoc
                        set stepName to ""
                        try
                            tell targetTable
                                {chr(10).join(body)}
                            end tell
                        on error errMsg number errNum
                            error "step '" & stepName & "' failed; the steps before it, " & ¬
                                "and any part of it already done, stayed applied: " & ¬
                                errMsg number errNum
                        end try
                        set p to position of targetTable
                        return ((row count of targetTable) as text) & "," & ¬
                            ((column count of targetTable) as text) & "|" & ¬
                            ((item 1 of p) as integer as text) & "," & ¬
                            ((item 2 of p) as integer as text) & "|" & ¬
                            ((width of targetTable) as integer as text) & "x" & ¬
                            ((height of targetTable) as integer as text) & "|" & ¬
                            ((header row count of targetTable) as text) & "," & ¬
                            ((header column count of targetTable) as text) & "," & ¬
                            ((footer row count of targetTable) as text)
                    end tell
                end run
                """,
                *argv.values,
                # One Apple event per op, ~17 ms each on macOS 27; the default
                # 30 s would cut a large values write off part-way.
                timeout=min(_EDIT_TABLE_MAX_TIMEOUT, 30.0 + 0.05 * n_ops),
            )
            dims, pos, size, got_counts = result.split("|")
            if counts:
                got = dict(
                    zip(
                        ("header rows", "header columns", "footer rows"),
                        got_counts.split(","),
                        strict=True,
                    )
                )
                done.append(", ".join(f"{k} {v}" for k, v in got.items()))
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Edited table {table_index} on slide {slide_number}: "
                        f"{'; '.join(done)}. Now {dims.replace(',', 'x')} at "
                        f"({pos.replace(',', ', ')}), size {size}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to edit table: {e}")]

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
            doc_slot = argv.reserve_doc()
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
            # Resolved AFTER the fragment builder has validated its
            # arguments, so invalid input never spends an Apple event and
            # never reports a document-ambiguity error in its place.
            doc_name = self._doc(doc_name)
            argv.fill(doc_slot, doc_name)
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
            doc_slot = argv.reserve_doc()
            lines = line_fragment("LN", x1=x1, y1=y1, x2=x2, y2=y2)
            # Resolved AFTER the fragment builder has validated its
            # arguments, so invalid input never spends an Apple event and
            # never reports a document-ambiguity error in its place.
            doc_name = self._doc(doc_name)
            argv.fill(doc_slot, doc_name)
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
            # The filename carries the panel's parameters, so describe_deck can
            # report `type: panel` with its colour instead of an anonymous
            # image, and build_deck can RE-RENDER it. Keynote keeps only the
            # basename once the bitmap is embedded, which is exactly why the
            # basename is where this has to live.
            png_path = os.path.join(
                tmp_dir,
                panel_filename(rgb65535_to_hex(",".join(str(c) for c in rgb)), corner, opacity),
            )
            render_panel_png(png_path, width, height, rgb, corner, opacity)
            argv = Argv()
            doc_slot = argv.reserve_doc()
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
            # Resolved AFTER the fragment builder has validated its
            # arguments, so invalid input never spends an Apple event and
            # never reports a document-ambiguity error in its place.
            doc_name = self._doc(doc_name)
            argv.fill(doc_slot, doc_name)
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

    async def styled_line(
        self,
        slide_number: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "#000000",
        stroke_width: float = 2.0,
        dash: str = "solid",
        start_arrow: bool = False,
        end_arrow: bool = False,
        opacity: float = 100,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Draw a line whose colour/width/dash/arrowheads carry meaning.

        `add_line` makes a native Keynote line but takes four coordinates and
        nothing else, because a line's ENTIRE property record is start/end
        point, position, width, height, rotation, reflection and locked - there
        is no stroke colour, thickness, dash or arrowhead anywhere in the
        dictionary (probed). In a real architecture diagram the stroke IS the
        semantics, so build_deck could produce correct geometry and then leave a
        human to hand-style every connector.

        This renders the stroke to a transparent PNG and places it, the same
        trick add_colored_panel uses for fills. The result is an image, not an
        editable line - but its parameters live in its filename, so
        describe_deck reports it back as a styled_line rather than losing it.
        """
        try:
            validate_slide_number(slide_number)
            rgb = parse_color(color)
            if rgb is None:
                raise ParameterError("styled_line needs a color.")
            validate_number(stroke_width, "stroke_width", minimum=0.1, maximum=200)
            validate_number(opacity, "opacity", minimum=0, maximum=100)
            hex_color = rgb65535_to_hex(",".join(str(c) for c in rgb))
            tmp_dir = tempfile.mkdtemp(prefix="keynote-mcp-stroke-")
            # Rendered to a scratch name first: the endpoint offsets are only
            # known once the renderer has computed the padded box, and they
            # have to be in the final filename for the round trip.
            scratch_png = os.path.join(tmp_dir, "stroke.png")
            ox, oy, box_w, box_h, _pw, _ph = render_stroke_png(
                scratch_png,
                x1,
                y1,
                x2,
                y2,
                rgb_65535=rgb,
                width_pt=stroke_width,
                dash=dash,
                start_arrow=start_arrow,
                end_arrow=end_arrow,
                opacity=opacity,
            )
            png_path = os.path.join(
                tmp_dir,
                stroke_filename(
                    hex_color,
                    stroke_width,
                    dash,
                    start_arrow,
                    end_arrow,
                    offsets=(x1 - ox, y1 - oy, x2 - ox, y2 - oy),
                ),
            )
            os.rename(scratch_png, png_path)
            argv = Argv()
            doc_slot = argv.reserve_doc()
            lines = image_fragment(
                argv,
                "SL",
                png_path,
                x=ox,
                y=oy,
                width=box_w,
                height=box_h,
                description=f"styled line ({dash}, {hex_color})",
            )
            doc_name = self._doc(doc_name)
            argv.fill(doc_slot, doc_name)
            index, pos, size = run_single_fragment(self.runner, doc_name, slide_number, argv, lines)
            arrows = []
            if start_arrow:
                arrows.append("start")
            if end_arrow:
                arrows.append("end")
            arrow_note = f", arrow at {' and '.join(arrows)}" if arrows else ""
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added styled line to slide {slide_number} (image index "
                        f"{index}) from ({x1:g}, {y1:g}) to ({x2:g}, {y2:g}): "
                        f"{hex_color}, {stroke_width:g}pt, {dash}{arrow_note}. "
                        f"Placed at ({pos.replace(',', ', ')}), size "
                        f"{size.replace(',', 'x')}. Rendered PNG, not a native "
                        "line - Keynote has no stroke API at all. Its parameters "
                        "are in its filename, so describe_deck reports it back as "
                        "a styled_line."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add styled line: {e}")]

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
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        {exists_guard("text item", item_index, slide_number)}
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
            doc_name = self._doc(doc_name)
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
            doc_name = self._doc(doc_name)
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
