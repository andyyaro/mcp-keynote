"""Shared AppleScript fragment builders.

Single source of truth for the element-creation AppleScript used by both the
per-element tools in ``content.py``/``objects.py`` and the batched
``build_deck`` executor. Every fragment:

- routes user strings through the argv allocator (injection safety - user
  text NEVER lands in script source; numbers/enums are interpolated only
  after strict validation against literals or numeric validators);
- assumes ``targetDoc`` and ``targetSlide`` variables are already set;
- applies position AFTER font sizing (Keynote's auto-fit keeps the box's
  vertical center fixed when the font size changes, so earlier positions
  drift - see CLAUDE.md);
- locates the created element's index by object identity, never by count
  (``count of text items`` includes hidden default title/body placeholders);
- appends one result token to the AppleScript variable ``out``:
  ``<tag>|<index>|x,y|w,h`` - the settled geometry read back in-call.
"""

from __future__ import annotations

from ..utils import AppleScriptRunner, ParameterError, validate_number, validate_slide_number

# docName always arrives CONCRETE: callers resolve it in Python via
# DocumentTargetedTools._doc before building a script, so there is deliberately
# no `front document` branch. That branch was the field report's issue #1 - a
# call omitting doc_name silently targeted whichever deck was frontmost.
RESOLVE_DOC = """
        set targetDoc to document docName"""

# --- THE text-item index filter: one definition, every reader -----------------
#
# Keynote's `count of text items` is untruthful. The slide's `default title
# item` / `default body item` objects occupy slots in the text-item space, and
# probing (Phase 9 Task 2, three visibility configurations) pins the exact
# shape:
#
#   both hidden : real-A(1) real-B(2) [hidden title](3) [hidden body](4)
#   title shown : TITLE(1)  real-C(2) TITLE-again(3)    [hidden body](4)
#   both shown  : TITLE(1)  BODY(2)   real-D(3) TITLE-again(4) BODY-again(5)
#
# Two consequences the codebase previously got wrong in two different ways:
#
# 1. A SHOWING placeholder takes a LEADING slot, so real indices shift by the
#    number of showing placeholders. CLAUDE.md's "real items always come first,
#    so real indices are stable" holds only while both placeholders are hidden.
# 2. A showing placeholder appears TWICE - once in z-order, once trailing. The
#    first occurrence is the addressable object; the repeat is a phantom.
#
# The canonical rule, used by EVERY reader so they cannot disagree:
#   first occurrence of a SHOWING placeholder -> REAL, flagged with its role
#   repeat occurrence, or any occurrence while hidden -> PHANTOM, skipped
#   anything else -> REAL, role ""
#
# `get_slide_content` implemented this; `describe_deck` marked every occurrence
# phantom and surfaced the text as slide.title instead. Same slide, two
# numberings, and the offset changed with the layout - so an index taken from
# one tool addressed a different element in the other. See docs/INDEX_CONTRACT.md.
TEXT_ITEM_FILTER = """
                    set defT to missing value
                    set defB to missing value
                    try
                        set defT to default title item
                    end try
                    try
                        set defB to default body item
                    end try
                    set titleShown to title showing
                    set bodyShown to body showing
                    set seenTitle to false
                    set seenBody to false
                    set realIndices to {}
                    set realRoles to {}
                    repeat with i from 1 to (count of text items)
                        set ti to text item i
                        set phantom to false
                        set role to ""
                        if defT is not missing value and ti is defT then
                            if seenTitle or (not titleShown) then
                                set phantom to true
                            else
                                set role to "title"
                            end if
                            set seenTitle to true
                        else if defB is not missing value and ti is defB then
                            if seenBody or (not bodyShown) then
                                set phantom to true
                            else
                                set role to "body"
                            end if
                            set seenBody to true
                        end if
                        if not phantom then
                            set end of realIndices to i
                            set end of realRoles to role
                        end if
                    end repeat"""


def exists_guard(as_type: str, index: int, slide_number: int) -> str:
    """AppleScript that fails loudly if ``as_type index`` is not on the slide.

    Keynote silently no-ops several operations against a nonexistent element,
    and an index that is merely STALE addresses a different object rather than
    none - so a caller working from an out-of-date listing edits the wrong
    element and is told it succeeded. delete_element, replace_image and
    set_element_style always guarded; edit_text_item, move_element,
    resize_element, set_element_opacity and style_text_range did not.

    ``as_type`` comes from a trusted map, ``index``/``slide_number`` from
    validators, so interpolation here is safe.
    """
    return (
        f"if not (exists {as_type} {index} of slide {slide_number} of targetDoc) then\n"
        f'    error "No {as_type} {index} on slide {slide_number}. Invalid index." number -1719\n'
        f"end if"
    )


# Trusted literal maps - ONLY values from these dicts may reach script source.
CHART_TYPES: dict[str, str] = {
    "bar": "vertical_bar_2d",
    "stacked_bar": "stacked_vertical_bar_2d",
    "horizontal_bar": "horizontal_bar_2d",
    "stacked_horizontal_bar": "stacked_horizontal_bar_2d",
    "line": "line_2d",
    "area": "area_2d",
    "stacked_area": "stacked_area_2d",
    "pie": "pie_2d",
    "scatter": "scatterplot_2d",
    "bar_3d": "vertical_bar_3d",
    "stacked_bar_3d": "stacked_vertical_bar_3d",
    "horizontal_bar_3d": "horizontal_bar_3d",
    "stacked_horizontal_bar_3d": "stacked_horizontal_bar_3d",
    "line_3d": "line_3d",
    "area_3d": "area_3d",
    "stacked_area_3d": "stacked_area_3d",
    "pie_3d": "pie_3d",
}

TRANSITION_EFFECTS: dict[str, str] = {
    name.replace(" ", "_"): name
    for name in (
        "no transition effect",
        "magic move",
        "shimmer",
        "sparkle",
        "swing",
        "object cube",
        "object flip",
        "object pop",
        "object push",
        "object revolve",
        "object zoom",
        "perspective",
        "clothesline",
        "confetti",
        "dissolve",
        "drop",
        "droplet",
        "fade through color",
        "grid",
        "iris",
        "move in",
        "push",
        "reveal",
        "switch",
        "wipe",
        "blinds",
        "color planes",
        "cube",
        "doorway",
        "fall",
        "flip",
        "flop",
        "mosaic",
        "page flip",
        "pivot",
        "reflection",
        "revolving door",
        "scale",
        "swap",
        "swoosh",
        "twirl",
        "twist",
        "fade and move",
    )
}


class Argv:
    """Allocates osascript argv slots for user strings.

    ``ref("some user text")`` records the string and returns the AppleScript
    expression that reads it back (``(item N of argv)``), so scripts stay
    injection-safe regardless of content.
    """

    def __init__(self) -> None:
        self.values: list[str] = []

    def ref(self, value: str) -> str:
        self.values.append(value)
        return f"(item {len(self.values)} of argv)"

    def reserve_doc(self) -> int:
        """Claim argv slot 1 for the document name, to be filled later.

        ``run_single_fragment`` reads the document name from item 1, so the slot
        must be allocated before the fragment builders add anything. But the
        NAME must not be resolved that early: resolving is an Apple event, and
        resolving before the fragment builders have validated their arguments
        means invalid input either wastes a round trip or - worse - reports
        "3 presentations are open" instead of "Invalid coordinate". So the slot
        is reserved here and filled by ``fill`` after validation.
        """
        self.values.append("")
        return 0

    def fill(self, slot: int, value: str) -> None:
        self.values[slot] = value


def _fmt_num(value: float) -> str:
    """Format a validated number for AppleScript source (int when whole)."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _identity_index_lines(element_class: str, var: str) -> list[str]:
    """Locate ``var``'s 1-based index among targetSlide's elements by identity."""
    return [
        "set newIndex to 0",
        f"repeat with i from 1 to (count of {element_class}s of targetSlide)",
        f"if {element_class} i of targetSlide is {var} then",
        "set newIndex to i",
        "exit repeat",
        "end if",
        "end repeat",
        "if newIndex is 0 then",
        f'error "Created {element_class} could not be located on the slide" number -1728',
        "end if",
    ]


def _emit_result(tag: str, var: str) -> list[str]:
    """Append '<tag>|index|x,y|w,h' for ``var`` to the ``out`` variable."""
    return [
        f"set finalPos to position of {var}",
        f'set out to out & "{tag}|" & (newIndex as text) & "|" & '
        '(item 1 of finalPos) & "," & (item 2 of finalPos) & "|" & '
        f'(width of {var}) & "," & (height of {var}) & linefeed',
    ]


def text_item_fragment(
    argv: Argv,
    tag: str,
    text: str,
    *,
    x: float | None = None,
    y: float | None = None,
    font_size: float | None = None,
    font_name: str = "",
    color_rgb: tuple[int, int, int] | None = None,
    width: float | None = None,
    height: float | None = None,
    centered: bool = False,
) -> list[str]:
    """Create a text item. Mirrors the verified single-call flow: natural
    auto-fit box (never pre-widened - load-bearing for ``centered``), text
    re-set after sizing as truncation insurance, position last."""
    text_ref = argv.ref(text)
    lines = [f"set newItem to make new text item with properties {{object text:{text_ref}}}"]
    if width is not None:
        lines.append(f"set width of newItem to {_fmt_num(width)}")
    if height is not None:
        lines.append(f"set height of newItem to {_fmt_num(height)}")
    if font_name:
        lines.append(f"set font of object text of newItem to {argv.ref(font_name)}")
    if font_size is not None:
        validate_number(font_size, "font_size", minimum=1, maximum=500)
        lines.append(f"set size of object text of newItem to {_fmt_num(font_size)}")
        lines.append(f"set object text of newItem to {text_ref}")
    if color_rgb:
        r, g, b = color_rgb
        lines.append(f"set color of object text of newItem to {{{r}, {g}, {b}}}")
    if x is not None or y is not None:
        lines.append(f"set position of newItem to {{{_fmt_num(x or 0)}, {_fmt_num(y or 0)}}}")
    if centered:
        lines += [
            "set curPos to position of newItem",
            "set position of newItem to "
            "{((width of targetDoc) - (width of newItem)) div 2, item 2 of curPos}",
        ]
    lines += _identity_index_lines("text item", "newItem")
    lines += _emit_result(tag, "newItem")
    return lines


def image_fragment(
    argv: Argv,
    tag: str,
    image_path: str,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    description: str = "",
) -> list[str]:
    path_ref = argv.ref(image_path)
    lines = [f"set newImage to make new image with properties {{file:(POSIX file {path_ref})}}"]
    if description:
        lines.append(f"set description of newImage to {argv.ref(description)}")
    if width is not None:
        lines.append(f"set width of newImage to {_fmt_num(width)}")
    if height is not None:
        lines.append(f"set height of newImage to {_fmt_num(height)}")
    if x is not None or y is not None:
        lines.append(f"set position of newImage to {{{_fmt_num(x or 0)}, {_fmt_num(y or 0)}}}")
    lines += _identity_index_lines("image", "newImage")
    lines += _emit_result(tag, "newImage")
    return lines


def shape_fragment(
    argv: Argv,
    tag: str,
    *,
    x: float = 0,
    y: float = 0,
    width: float = 200,
    height: float = 100,
    opacity: float | None = None,
    text: str = "",
) -> list[str]:
    lines = [
        "set newShape to make new shape with properties "
        f"{{position:{{{_fmt_num(x)}, {_fmt_num(y)}}}, "
        f"width:{_fmt_num(width)}, height:{_fmt_num(height)}}}"
    ]
    if opacity is not None:
        validate_number(opacity, "opacity", minimum=0, maximum=100)
        lines.append(f"set opacity of newShape to {int(opacity)}")
    if text:
        lines.append(f"set object text of newShape to {argv.ref(text)}")
    lines += _identity_index_lines("shape", "newShape")
    lines += _emit_result(tag, "newShape")
    return lines


def line_fragment(
    tag: str,
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> list[str]:
    for name, v in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
        validate_number(v, name, minimum=0)
    make_line = (
        "set newLine to make new line with properties "
        f"{{start point:{{{_fmt_num(x1)}, {_fmt_num(y1)}}}, "
        f"end point:{{{_fmt_num(x2)}, {_fmt_num(y2)}}}}}"
    )
    # `make new line` fails with -10000 "AppleEvent handler failed" while
    # Keynote's Animate inspector is open (root-caused live; the build tools
    # now restore the Format pane). Kept as defense in depth: one in-script
    # retry, guarded by the line count so it can never duplicate a
    # half-created line (lines have no phantom-count problem).
    lines = [
        "set lineCountBefore to count of lines of targetSlide",
        "try",
        make_line,
        "on error errMsg number errNum",
        "if errNum is -10000 and (count of lines of targetSlide) is lineCountBefore then",
        "delay 0.4",
        make_line,
        "else",
        "error errMsg number errNum",
        "end if",
        "end try",
    ]
    lines += _identity_index_lines("line", "newLine")
    lines += _emit_result(tag, "newLine")
    return lines


def _column_letter(index: int) -> str:
    """1-based column index -> A1-notation letters (1->A, 27->AA)."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def range_name(row1: int, col1: int, row2: int, col2: int) -> str:
    return f"{_column_letter(col1)}{row1}:{_column_letter(col2)}{row2}"


def table_fragment(
    argv: Argv,
    tag: str,
    data: list[list[object]],
    *,
    x: float = 0,
    y: float = 0,
    width: float | None = None,
    height: float | None = None,
    header_row: bool = True,
    header_column: bool = False,
    font_name: str = "",
    font_size: float | None = None,
    header_font_size: float | None = None,
    header_bg: tuple[int, int, int] | None = None,
    header_color: tuple[int, int, int] | None = None,
    column_widths: list[float] | None = None,
) -> list[str]:
    """Create a native table and fill it from ``data`` (rows of cells).

    Keynote refuses tables smaller than 2x2 (probed: 'Invalid row/column
    count' -10000) - the caller validates. Numeric cells are interpolated as
    numbers (so they stay numeric in Keynote); strings go through argv (a
    leading '=' becomes a live formula, per the probed value-setting path).
    """
    rows = len(data)
    cols = len(data[0]) if rows else 0
    if rows < 2 or cols < 2:
        raise ParameterError(
            f"Table needs at least 2 rows and 2 columns (got {rows}x{cols}): "
            "Keynote rejects smaller tables (error -10000)."
        )
    if any(len(r) != cols for r in data):
        raise ParameterError("All table rows must have the same number of columns.")

    props = [
        f"position:{{{_fmt_num(x)}, {_fmt_num(y)}}}",
        f"row count:{rows}",
        f"column count:{cols}",
        f"header row count:{1 if header_row else 0}",
        f"header column count:{1 if header_column else 0}",
    ]
    if width is not None:
        props.append(f"width:{_fmt_num(width)}")
    if height is not None:
        props.append(f"height:{_fmt_num(height)}")
    lines = [f"set newTable to make new table with properties {{{', '.join(props)}}}"]

    cell_sets = []
    for r, row in enumerate(data, start=1):
        for c, cell in enumerate(row, start=1):
            if cell is None or cell == "":
                continue
            if isinstance(cell, bool):
                value_expr = "true" if cell else "false"
            elif isinstance(cell, (int, float)):
                value_expr = _fmt_num(cell)
            else:
                value_expr = argv.ref(str(cell))
            cell_sets.append(f"set value of cell {c} of row {r} to {value_expr}")
    if cell_sets:
        lines.append("tell newTable")
        lines += cell_sets
        lines.append("end tell")

    full = range_name(1, 1, rows, cols)
    styling = []
    if font_name:
        styling.append(f'set font name of range "{full}" to {argv.ref(font_name)}')
    if font_size is not None:
        validate_number(font_size, "font_size", minimum=1, maximum=200)
        styling.append(f'set font size of range "{full}" to {_fmt_num(font_size)}')
    if header_row:
        hdr = range_name(1, 1, 1, cols)
        if header_font_size is not None:
            validate_number(header_font_size, "header_font_size", minimum=1, maximum=200)
            styling.append(f'set font size of range "{hdr}" to {_fmt_num(header_font_size)}')
        if header_bg:
            r_, g_, b_ = header_bg
            styling.append(f'set background color of range "{hdr}" to {{{r_}, {g_}, {b_}}}')
        if header_color:
            r_, g_, b_ = header_color
            styling.append(f'set text color of range "{hdr}" to {{{r_}, {g_}, {b_}}}')
    if column_widths:
        if len(column_widths) > cols:
            raise ParameterError(
                f"column_widths has {len(column_widths)} entries for {cols} columns."
            )
        for c, w in enumerate(column_widths, start=1):
            if w is not None:
                validate_number(w, f"column_widths[{c - 1}]", minimum=1)
                styling.append(f"set width of column {c} to {_fmt_num(w)}")
    if styling:
        lines.append("tell newTable")
        lines += styling
        lines.append("end tell")

    lines += _identity_index_lines("table", "newTable")
    lines += _emit_result(tag, "newTable")
    return lines


def chart_fragment(
    argv: Argv,
    tag: str,
    *,
    chart_type: str,
    row_names: list[str],
    column_names: list[str],
    data: list[list[float]],
    group_by: str = "row",
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
) -> list[str]:
    """Create a native chart via the Compatibility Suite ``add chart``.

    The command silently creates NOTHING unless the target slide is the
    document's current slide (probed live), so the fragment sets it first.
    The chart cannot be identity-located (``add chart`` returns nothing);
    charts have no phantom-count problem, so the new chart is
    ``chart (count of charts)``.
    """
    if chart_type not in CHART_TYPES:
        raise ParameterError(f"Unknown chart_type {chart_type!r}. Valid: {sorted(CHART_TYPES)}")
    if group_by not in ("row", "column"):
        raise ParameterError("group_by must be 'row' or 'column'.")
    # Pie slices come from the axis you group by (verified visually: grouping
    # by a single-entry axis renders one 100% slice). When exactly one axis
    # has multiple entries, group by that axis so the categories become the
    # slices regardless of what the caller passed.
    if chart_type.startswith("pie"):
        if len(row_names) > 1 and len(column_names) == 1:
            group_by = "row"
        elif len(column_names) > 1 and len(row_names) == 1:
            group_by = "column"
    if not data or not row_names or not column_names:
        raise ParameterError("Chart needs row_names, column_names, and data.")
    if len(data) != len(row_names):
        raise ParameterError(f"Chart data has {len(data)} rows but {len(row_names)} row_names.")
    for r, row in enumerate(data):
        if len(row) != len(column_names):
            raise ParameterError(
                f"Chart data row {r} has {len(row)} values but {len(column_names)} column_names."
            )
        for v in row:
            validate_number(v, f"data[{r}]", minimum=-1e12, maximum=1e12)

    row_list = "{" + ", ".join(argv.ref(str(n)) for n in row_names) + "}"
    col_list = "{" + ", ".join(argv.ref(str(n)) for n in column_names) + "}"
    data_list = (
        "{" + ", ".join("{" + ", ".join(_fmt_num(v) for v in row) + "}" for row in data) + "}"
    )
    lines = [
        "set current slide of targetDoc to targetSlide",
        "set chartCountBefore to count of charts of targetSlide",
        "tell targetSlide",
        f"add chart row names {row_list} column names {col_list} "
        f"data {data_list} type {CHART_TYPES[chart_type]} group by chart {group_by}",
        "end tell",
        "set newIndex to count of charts of targetSlide",
        "if newIndex is chartCountBefore then",
        'error "add chart created no chart (is the slide the current slide?)" number -10000',
        "end if",
        "set newChart to chart newIndex of targetSlide",
    ]
    if width is not None:
        lines.append(f"set width of newChart to {_fmt_num(width)}")
    if height is not None:
        lines.append(f"set height of newChart to {_fmt_num(height)}")
    if x is not None or y is not None:
        lines.append(f"set position of newChart to {{{_fmt_num(x or 0)}, {_fmt_num(y or 0)}}}")
    lines += _emit_result(tag, "newChart")
    return lines


def notes_fragment(argv: Argv, notes: str) -> list[str]:
    return [f"set presenter notes of targetSlide to {argv.ref(notes)}"]


def placeholder_fragment(
    argv: Argv,
    tag: str,
    *,
    title: str | None = None,
    body: str | None = None,
) -> list[str]:
    """Fill the slide's theme title/body placeholders (set_slide_content path)."""
    lines = []
    if title is not None:
        lines += [
            "tell targetSlide",
            "set title showing to true",
            f"set object text of default title item to {argv.ref(title)}",
            "end tell",
        ]
    if body is not None:
        lines += [
            "tell targetSlide",
            "set body showing to true",
            f"set object text of default body item to {argv.ref(body)}",
            "end tell",
        ]
    if lines:
        lines.append(f'set out to out & "{tag}|placeholders-set||" & linefeed')
    return lines


def transition_fragment(
    *,
    effect: str,
    duration: float = 1.0,
    delay: float = 0.0,
    automatic: bool = False,
) -> list[str]:
    if effect not in TRANSITION_EFFECTS:
        raise ParameterError(
            f"Unknown transition effect {effect!r}. Valid: {sorted(TRANSITION_EFFECTS)}"
        )
    validate_number(duration, "duration", minimum=0, maximum=60)
    validate_number(delay, "delay", minimum=0, maximum=600)
    auto = "true" if automatic else "false"
    return [
        "set transition properties of targetSlide to "
        f"{{transition effect:{TRANSITION_EFFECTS[effect]}, "
        f"transition duration:{_fmt_num(duration)}, "
        f"transition delay:{_fmt_num(delay)}, "
        f"automatic transition:{auto}}}"
    ]


def skipped_fragment(skipped: bool) -> list[str]:
    # Note: 'skipped:true' inside make-new-slide properties is silently
    # ignored (probed) - it must be its own statement.
    return [f"set skipped of targetSlide to {'true' if skipped else 'false'}"]


def run_single_fragment(
    runner: AppleScriptRunner,
    doc_name: str,
    slide_number: int,
    argv: Argv,
    lines: list[str],
    timeout: float | None = None,
) -> tuple[str, str, str]:
    """Execute one element fragment against one slide; return (index, "x,y", "w,h").

    ``argv`` must have been created with ``argv.ref(doc_name)`` as its FIRST
    allocation (the wrapper reads item 1 as the document name), with the
    fragment built on the same allocator afterwards.
    """
    validate_slide_number(slide_number)
    body = "\n".join(lines)
    script = f"""
    on run argv
        set docName to item 1 of argv
        tell application "Keynote"
            {RESOLVE_DOC}
            set targetSlide to slide {slide_number} of targetDoc
            set out to ""
            tell targetSlide
                {body}
            end tell
            return out
        end tell
    end run
    """
    raw = runner.run(script, *argv.values, timeout=timeout).strip()
    _tag, index, pos, size = raw.split("|")
    return index, pos, size
