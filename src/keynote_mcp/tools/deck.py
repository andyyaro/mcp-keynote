"""Declarative deck building: build_deck / describe_deck.

``build_deck`` turns a whole-deck spec (JSON object, or a small markdown
dialect that compiles to it) into a presentation using ONE osascript session
per slide (plus one setup and one save session) instead of one round trip per
element. The element AppleScript comes from the same ``fragments`` builders
the per-element tools use, so behavior (identity-located indices,
position-after-sizing, settled-geometry readback) is identical by
construction.

Execution contract:
- The whole spec is validated BEFORE any document is created; layout names
  are validated against the live theme right after document creation, and a
  layout failure deletes the fresh document again - no half-built deck.
- Each element is wrapped in an AppleScript try block: one failing element
  reports an actionable per-element error and the rest of the deck still
  builds.
- Elements are created in spec order, which is also Keynote's z-order
  (AppleScript cannot reorder) - put panels/backgrounds before the text that
  sits on them.
- Re-running with the same save_path replaces the previous file by default
  (``on_exists``: replace | error | unique).

``describe_deck`` reads an open presentation back into the same spec format,
so decks round-trip (charts come back geometry-only: Keynote exposes no
chart data to read).
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from typing import Any

from mcp.types import TextContent, Tool

from ..utils import AppleScriptRunner, ParameterError, parse_color
from ..utils.render import render_panel_png
from ..utils.styles import DeckStyle, resolve_style
from .fragments import (
    CHART_TYPES,
    RESOLVE_DOC,
    TRANSITION_EFFECTS,
    Argv,
    chart_fragment,
    image_fragment,
    line_fragment,
    notes_fragment,
    placeholder_fragment,
    shape_fragment,
    skipped_fragment,
    table_fragment,
    text_item_fragment,
    transition_fragment,
)
from .presentation import _default_save_path, _normalize_key_path

_DOC_ARG = {
    "type": "string",
    "description": "Document name (optional, defaults to front document)",
}

_ELEMENT_TYPES = {
    "title",
    "subtitle",
    "text",
    "bullets",
    "numbered",
    "code",
    "quote",
    "image",
    "shape",
    "panel",
    "table",
    "chart",
    "line",
}

# ASCII unit/record separators for structured readbacks (never appear in
# normal slide text; a deck containing them would corrupt field splits).
# Scripts build them with `character id` so no control bytes land in source.
_FS = "\x1f"
_RS = "\x1e"
_AS_FS = "(character id 31)"
_AS_RS = "(character id 30)"

_SLIDE_SESSION_TIMEOUT = 120.0
_SLIDES_PER_SESSION = 5


def _err(path: str, message: str) -> str:
    return f"{path}: {message}"


def _num(value: Any, path: str, errors: list[str], minimum: float = -1e9) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(_err(path, f"must be a number, got {value!r}"))
        return None
    if value < minimum:
        errors.append(_err(path, f"must be >= {minimum:g}, got {value:g}"))
        return None
    return float(value)


def _validate_element(el: Any, path: str, errors: list[str]) -> None:
    if not isinstance(el, dict):
        errors.append(_err(path, "element must be an object"))
        return
    etype = el.get("type")
    if etype not in _ELEMENT_TYPES:
        errors.append(
            _err(path, f"unknown element type {etype!r}; valid: {sorted(_ELEMENT_TYPES)}")
        )
        return
    for key in ("x", "y", "width", "height", "font_size"):
        _num(el.get(key), f"{path}.{key}", errors, minimum=0)
    if el.get("column") not in (None, "left", "right"):
        errors.append(_err(path, "column must be 'left' or 'right'"))
    color = el.get("color", "")
    if color:
        try:
            parse_color(str(color))
        except ParameterError as e:
            errors.append(_err(f"{path}.color", str(e)))

    if etype in ("title", "subtitle", "text", "code", "quote"):
        if not isinstance(el.get("text"), str) or not el.get("text"):
            errors.append(_err(path, f"{etype} needs a non-empty 'text' string"))
    elif etype in ("bullets", "numbered"):
        items = el.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
            errors.append(_err(path, f"{etype} needs a non-empty string array 'items'"))
    elif etype == "image":
        p = el.get("path")
        if not isinstance(p, str) or not p:
            errors.append(_err(path, "image needs a 'path'"))
        elif not os.path.isfile(os.path.expanduser(p)):
            errors.append(_err(path, f"image file does not exist: {p}"))
    elif etype == "panel":
        for key in ("x", "y", "width", "height"):
            if el.get(key) is None:
                errors.append(_err(path, f"panel needs explicit '{key}'"))
    elif etype == "table":
        data = el.get("data")
        if not isinstance(data, list) or len(data) < 2:
            errors.append(_err(path, "table needs 'data' with at least 2 rows"))
        elif not all(isinstance(r, list) for r in data):
            errors.append(_err(path, "table 'data' must be rows (arrays) of cells"))
        else:
            widths = {len(r) for r in data}
            if len(widths) != 1:
                errors.append(_err(path, "table rows must all have the same length"))
            elif widths.pop() < 2:
                errors.append(_err(path, "table needs at least 2 columns (Keynote 2x2 minimum)"))
    elif etype == "chart":
        if el.get("chart_type") not in CHART_TYPES:
            errors.append(
                _err(
                    path,
                    f"chart_type {el.get('chart_type')!r} invalid; valid: {sorted(CHART_TYPES)}",
                )
            )
        rows = el.get("row_names")
        cols = el.get("column_names")
        data = el.get("data")
        if not isinstance(rows, list) or not rows:
            errors.append(_err(path, "chart needs 'row_names'"))
        if not isinstance(cols, list) or not cols:
            errors.append(_err(path, "chart needs 'column_names'"))
        if not isinstance(data, list) or not data:
            errors.append(_err(path, "chart needs 'data'"))
        elif isinstance(rows, list) and len(data) != len(rows):
            errors.append(_err(path, f"chart data has {len(data)} rows for {len(rows)} row_names"))
        elif isinstance(cols, list) and any(
            not isinstance(r, list) or len(r) != len(cols) for r in data
        ):
            errors.append(_err(path, "each chart data row needs one number per column_name"))
        if el.get("group_by") not in (None, "row", "column"):
            errors.append(_err(path, "chart group_by must be 'row' or 'column'"))
    elif etype == "line":
        for key in ("x1", "y1", "x2", "y2"):
            if _num(el.get(key), f"{path}.{key}", errors, minimum=0) is None:
                errors.append(_err(path, f"line needs numeric '{key}'"))


def validate_spec(spec: Any) -> list[str]:
    """Validate a whole deck spec; returns ALL problems, not just the first."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    slides = spec.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("spec.slides must be a non-empty array")
        slides = []
    for key in ("width", "height"):
        _num(spec.get(key), f"spec.{key}", errors, minimum=200)
    for i, slide in enumerate(slides):
        path = f"slides[{i}]"
        if not isinstance(slide, dict):
            errors.append(_err(path, "slide must be an object"))
            continue
        for key in ("title", "body", "notes", "layout"):
            if slide.get(key) is not None and not isinstance(slide[key], str):
                errors.append(_err(f"{path}.{key}", "must be a string"))
        if slide.get("skipped") is not None and not isinstance(slide["skipped"], bool):
            errors.append(_err(f"{path}.skipped", "must be a boolean"))
        transition = slide.get("transition")
        if transition is not None:
            if not isinstance(transition, dict):
                errors.append(_err(f"{path}.transition", "must be an object"))
            else:
                effect = transition.get("effect")
                if effect not in TRANSITION_EFFECTS:
                    errors.append(
                        _err(
                            f"{path}.transition.effect",
                            f"{effect!r} invalid; e.g. dissolve, push, magic_move "
                            "(underscored Keynote effect names)",
                        )
                    )
                _num(transition.get("duration"), f"{path}.transition.duration", errors, 0)
                _num(transition.get("delay"), f"{path}.transition.delay", errors, 0)
        elements = slide.get("elements", [])
        if not isinstance(elements, list):
            errors.append(_err(f"{path}.elements", "must be an array"))
            continue
        for j, el in enumerate(elements):
            _validate_element(el, f"{path}.elements[{j}]", errors)
    return errors


# --------------------------------------------------------------------------
# Markdown dialect -> spec
# --------------------------------------------------------------------------

_ATTR_COMMENT_RE = re.compile(r"<!--\s*([^>]*?)\s*-->\s*$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*(?:<!--.*-->)?\s*$")


def _parse_attrs(line: str) -> tuple[str, dict[str, Any]]:
    """Split a trailing ``<!-- key=value ... -->`` attribute comment off a line."""
    match = _ATTR_COMMENT_RE.search(line)
    if not match:
        return line.rstrip(), {}
    body = match.group(1)
    attrs: dict[str, Any] = {}
    for part in body.split():
        if "=" not in part:
            attrs[part] = True
            continue
        key, _, raw = part.partition("=")
        value: Any = raw
        try:
            value = int(raw)
        except ValueError:
            try:
                value = float(raw)
            except ValueError:
                if raw in ("true", "false"):
                    value = raw == "true"
        attrs[key] = value
    return line[: match.start()].rstrip(), attrs


def markdown_to_spec(markdown: str) -> dict[str, Any]:
    """Compile the markdown dialect into a deck spec.

    Dialect: optional ``---`` frontmatter (title/theme/style/width/height/
    save_path); ``#`` = title slide; ``##`` = new slide; ``-``/``*`` bullets;
    ``1.`` numbered; ``>`` quote; fenced code (``` ```chart``` fences take a
    JSON chart object); ``![alt](path)`` images; GitHub tables; a paragraph
    starting ``Notes:`` becomes speaker notes; ``<!-- transition: push 1.0 -->``
    and ``<!-- skip -->`` set slide properties; any block may end with an
    ``<!-- x=.. y=.. width=.. font_size=.. column=left -->`` attribute comment.
    """
    spec: dict[str, Any] = {"slides": []}
    lines = markdown.splitlines()
    pos = 0

    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() == "---":
                for raw in lines[1:end]:
                    if ":" in raw:
                        key, _, value = raw.partition(":")
                        key, value = key.strip(), value.strip()
                        if key in ("width", "height"):
                            try:
                                spec[key] = int(value)
                            except ValueError:
                                pass
                        elif key in ("title", "theme", "style", "save_path"):
                            spec[key] = value
                pos = end + 1
                break

    slide: dict[str, Any] | None = None

    def ensure_slide() -> dict[str, Any]:
        nonlocal slide
        if slide is None:
            slide = {"elements": []}
            spec["slides"].append(slide)
        return slide

    def flush_paragraph(buf: list[str]) -> None:
        if not buf:
            return
        text, attrs = _parse_attrs("\n".join(buf))
        buf.clear()
        if not text.strip():
            return
        current = ensure_slide()
        if text.startswith("Notes:"):
            current["notes"] = text[len("Notes:") :].strip()
            return
        current["elements"].append({"type": "text", "text": text.strip(), **attrs})

    paragraph: list[str] = []
    while pos < len(lines):
        raw = lines[pos]
        stripped = raw.strip()

        directive = re.fullmatch(r"<!--\s*(.+?)\s*-->", stripped)
        if directive and paragraph == []:
            body = directive.group(1)
            if body == "skip":
                ensure_slide()["skipped"] = True
                pos += 1
                continue
            trans = re.fullmatch(r"transition:\s*(\w+)(?:\s+([\d.]+))?(?:\s+auto)?", body)
            if trans:
                ensure_slide()["transition"] = {
                    "effect": trans.group(1),
                    "duration": float(trans.group(2) or 1.0),
                    "automatic": body.rstrip().endswith("auto"),
                }
                pos += 1
                continue

        if stripped.startswith("```"):
            flush_paragraph(paragraph)
            fence_info, attrs = _parse_attrs(stripped[3:].strip())
            block: list[str] = []
            pos += 1
            while pos < len(lines) and not lines[pos].strip().startswith("```"):
                block.append(lines[pos])
                pos += 1
            pos += 1  # closing fence
            current = ensure_slide()
            if fence_info == "chart":
                try:
                    chart = json.loads("\n".join(block))
                    chart["type"] = "chart"
                    chart.update(attrs)
                    current["elements"].append(chart)
                except json.JSONDecodeError as e:
                    current["elements"].append(
                        {"type": "text", "text": f"[invalid chart JSON: {e}]"}
                    )
            else:
                current["elements"].append({"type": "code", "text": "\n".join(block), **attrs})
            continue

        if stripped.startswith("# ") and not stripped.startswith("## "):
            flush_paragraph(paragraph)
            text, attrs = _parse_attrs(stripped[2:])
            spec.setdefault("title", text)
            slide = {"elements": [{"type": "title", "text": text, "centered": True, **attrs}]}
            spec["slides"].append(slide)
            pos += 1
            continue

        if stripped.startswith("## "):
            flush_paragraph(paragraph)
            text, attrs = _parse_attrs(stripped[3:])
            slide = {"elements": [{"type": "title", "text": text, **attrs}]}
            spec["slides"].append(slide)
            pos += 1
            continue

        image = _IMAGE_RE.match(stripped)
        if image:
            flush_paragraph(paragraph)
            _, attrs = _parse_attrs(stripped)
            ensure_slide()["elements"].append(
                {
                    "type": "image",
                    "path": image.group(2),
                    "description": image.group(1),
                    **attrs,
                }
            )
            pos += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph(paragraph)
            items = []
            attrs = {}
            while pos < len(lines):
                m = re.match(r"^[-*]\s+(.*)$", lines[pos].strip())
                if not m:
                    break
                text, item_attrs = _parse_attrs(m.group(1))
                attrs.update(item_attrs)
                items.append(text)
                pos += 1
            ensure_slide()["elements"].append({"type": "bullets", "items": items, **attrs})
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph(paragraph)
            items = []
            attrs = {}
            while pos < len(lines):
                m = re.match(r"^\d+\.\s+(.*)$", lines[pos].strip())
                if not m:
                    break
                text, item_attrs = _parse_attrs(m.group(1))
                attrs.update(item_attrs)
                items.append(text)
                pos += 1
            ensure_slide()["elements"].append({"type": "numbered", "items": items, **attrs})
            continue

        if stripped.startswith("> "):
            flush_paragraph(paragraph)
            quote_lines = []
            attrs = {}
            while pos < len(lines) and lines[pos].strip().startswith(">"):
                text, line_attrs = _parse_attrs(lines[pos].strip().lstrip("> "))
                attrs.update(line_attrs)
                quote_lines.append(text)
                pos += 1
            ensure_slide()["elements"].append(
                {"type": "quote", "text": " ".join(quote_lines), **attrs}
            )
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph(paragraph)
            rows = []
            attrs = {}
            while pos < len(lines):
                line = lines[pos].strip()
                if not (line.startswith("|") and line.endswith("|")):
                    break
                line, line_attrs = _parse_attrs(line)
                attrs.update(line_attrs)
                cells = [c.strip() for c in line.strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    typed: list[object] = []
                    for cell in cells:
                        try:
                            typed.append(int(cell))
                        except ValueError:
                            try:
                                typed.append(float(cell))
                            except ValueError:
                                typed.append(cell)
                    rows.append(typed)
                pos += 1
            if rows:
                ensure_slide()["elements"].append({"type": "table", "data": rows, **attrs})
            continue

        if not stripped:
            flush_paragraph(paragraph)
            pos += 1
            continue

        paragraph.append(raw)
        pos += 1

    flush_paragraph(paragraph)
    return spec


# --------------------------------------------------------------------------
# Auto-layout (flow) for elements without explicit positions
# --------------------------------------------------------------------------


def _estimate_text_height(text: str, size: float, width: float) -> float:
    lines = 0
    for line in text.split("\n"):
        chars_per_line = max(8, int(width / (0.52 * size)))
        lines += max(1, math.ceil(max(1, len(line)) / chars_per_line))
    return lines * size * 1.45


def _flow_slide(
    slide: dict[str, Any], style: DeckStyle, width: float, height: float
) -> tuple[list[dict[str, Any]], float]:
    """Assign positions/sizes to elements lacking them; returns element params.

    Full-width elements stack from the top margin; ``column: left/right``
    elements flow in independent half-width columns (a later full-width
    element resumes below the taller column).
    """
    margin_x = style.margin_x(width)
    content_w = style.content_width(width)
    gutter = style.gap(height)
    col_w = (content_w - gutter) / 2
    cursors = {"full": float(style.margin_top(height))}
    cursors["left"] = cursors["right"] = cursors["full"]
    gap = style.gap(height)

    placed = []
    for el in slide.get("elements", []):
        el = dict(el)
        etype = el["type"]
        column = el.pop("column", None)
        explicit = el.get("x") is not None or el.get("y") is not None
        if etype in ("panel", "line", "shape") or explicit:
            placed.append(el)
            continue

        if column in ("left", "right"):
            x = margin_x if column == "left" else margin_x + col_w + gutter
            avail_w = col_w
            cursor_key = column
            # A column starts below whatever full-width content came first.
            cursors[column] = max(cursors[column], cursors["full"])
        else:
            x = margin_x
            avail_w = content_w
            cursor_key = "full"
            cursors["full"] = max(cursors.values())
        y = cursors[cursor_key]

        if etype == "title":
            size = el.get("font_size") or style.title_size
            el.setdefault("y", y)
            if not el.get("centered"):
                el.setdefault("x", x)
            est = size * 1.5
        elif etype == "subtitle":
            size = el.get("font_size") or style.subtitle_size
            el.setdefault("y", y)
            if not el.get("centered"):
                el.setdefault("x", x)
            est = size * 1.6
        elif etype in ("text", "bullets", "numbered", "code", "quote"):
            if etype == "bullets":
                text = "\n".join(f"• {i}" for i in el.get("items", []))
                size = el.get("font_size") or style.body_size
            elif etype == "numbered":
                text = "\n".join(f"{n}. {i}" for n, i in enumerate(el.get("items", []), 1))
                size = el.get("font_size") or style.body_size
            elif etype == "code":
                text = el.get("text", "")
                size = el.get("font_size") or style.code_size
            elif etype == "quote":
                text = el.get("text", "")
                size = el.get("font_size") or style.quote_size
            else:
                text = el.get("text", "")
                size = el.get("font_size") or style.body_size
            el.setdefault("x", x)
            el.setdefault("y", y)
            el.setdefault("width", avail_w)
            est = el.get("height") or _estimate_text_height(text, size, avail_w)
        elif etype == "image":
            el.setdefault("x", x)
            el.setdefault("y", y)
            if el.get("width") is None and el.get("height") is None:
                el["width"] = avail_w * 0.6
            est = el.get("height") or (el.get("width", avail_w * 0.6) * 0.66)
        elif etype == "table":
            el.setdefault("x", x)
            el.setdefault("y", y)
            el.setdefault("width", avail_w)
            rows = len(el.get("data", []))
            est = el.get("height") or max(80, rows * (style.table_font_size * 2.4))
            el.setdefault("height", est)
        elif etype == "chart":
            el.setdefault("x", x)
            el.setdefault("y", y)
            el.setdefault("width", avail_w)
            el.setdefault("height", min(height * 0.5, avail_w * 0.55))
            est = el["height"]
        else:  # pragma: no cover - all types handled above
            est = 0
        cursors[cursor_key] = y + est + gap
        placed.append(el)

    est_bottom = max(cursors.values()) - gap if placed else 0
    return placed, est_bottom


# --------------------------------------------------------------------------
# Script assembly
# --------------------------------------------------------------------------


def _element_fragment(
    el: dict[str, Any], tag: str, argv: Argv, style: DeckStyle, panels_dir: str
) -> list[str]:
    etype = el["type"]
    color = str(el.get("color", ""))
    if etype in ("title", "subtitle", "text", "code", "quote"):
        role = {"text": "body"}.get(etype, etype)
        font = el.get("font_name") or getattr(style, f"{role}_font")
        size = el.get("font_size") or getattr(style, f"{role}_size")
        rgb = parse_color(color or getattr(style, f"{role}_color"))
        text = el["text"]
        if etype == "quote":
            text = f"“{text}”"
        return text_item_fragment(
            argv,
            tag,
            text,
            x=el.get("x"),
            y=el.get("y"),
            font_size=size,
            font_name=font,
            color_rgb=rgb,
            width=el.get("width"),
            height=el.get("height"),
            centered=bool(el.get("centered")),
        )
    if etype in ("bullets", "numbered"):
        if etype == "bullets":
            text = "\n".join(f"• {i}" for i in el["items"])
        else:
            text = "\n".join(f"{n}. {i}" for n, i in enumerate(el["items"], 1))
        font = el.get("font_name") or style.body_font
        size = el.get("font_size") or style.body_size
        rgb = parse_color(color or style.body_color)
        return text_item_fragment(
            argv,
            tag,
            text,
            x=el.get("x"),
            y=el.get("y"),
            font_size=size,
            font_name=font,
            color_rgb=rgb,
            width=el.get("width"),
            height=el.get("height"),
        )
    if etype == "image":
        return image_fragment(
            argv,
            tag,
            os.path.realpath(os.path.expanduser(el["path"])),
            x=el.get("x"),
            y=el.get("y"),
            width=el.get("width"),
            height=el.get("height"),
            description=str(el.get("description", "")),
        )
    if etype == "panel":
        rgb = parse_color(color or style.panel_color) or (60000, 60000, 60000)
        radius = el.get("radius", style.panel_radius)
        png_path = os.path.join(panels_dir, f"{tag}.png")
        render_panel_png(
            png_path,
            el["width"],
            el["height"],
            rgb,
            radius,
            el.get("opacity", 100),
        )
        return image_fragment(
            argv,
            tag,
            png_path,
            x=el["x"],
            y=el["y"],
            width=el["width"],
            height=el["height"],
            description="colored panel",
        )
    if etype == "shape":
        return shape_fragment(
            argv,
            tag,
            x=el.get("x", 0),
            y=el.get("y", 0),
            width=el.get("width", 200),
            height=el.get("height", 100),
            opacity=el.get("opacity"),
            text=str(el.get("text", "")),
        )
    if etype == "table":
        return table_fragment(
            argv,
            tag,
            el["data"],
            x=el.get("x", 0),
            y=el.get("y", 0),
            width=el.get("width"),
            height=el.get("height"),
            header_row=el.get("header_row", True),
            header_column=el.get("header_column", False),
            font_name=el.get("font_name") or style.table_font,
            font_size=el.get("font_size") or style.table_font_size,
            header_font_size=style.table_header_font_size,
            header_bg=parse_color(style.table_header_bg),
            header_color=parse_color(style.table_header_color),
            column_widths=el.get("column_widths"),
        )
    if etype == "chart":
        return chart_fragment(
            argv,
            tag,
            chart_type=el["chart_type"],
            row_names=[str(n) for n in el["row_names"]],
            column_names=[str(n) for n in el["column_names"]],
            data=el["data"],
            group_by=el.get("group_by", "row"),
            x=el.get("x"),
            y=el.get("y"),
            width=el.get("width"),
            height=el.get("height"),
        )
    if etype == "line":
        return line_fragment(tag, x1=el["x1"], y1=el["y1"], x2=el["x2"], y2=el["y2"])
    raise ParameterError(f"Unhandled element type {etype!r}")  # pragma: no cover


def _parse_cell(raw: str) -> object:
    """Reverse the table readback: formulas stay strings, numbers come back
    as numbers (integers when whole) so describe->build round-trips."""
    if raw.startswith("="):
        return raw
    try:
        value = float(raw)
    except ValueError:
        return raw
    return int(value) if value.is_integer() else value


def _wrap_try(fragment: list[str], tag: str) -> list[str]:
    return [
        "try",
        *fragment,
        "on error errMsg number errNum",
        f'set out to out & "ERR|{tag}|" & errNum & "|" & errMsg & linefeed',
        "end try",
    ]


class DeckTools:
    """build_deck / describe_deck."""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="build_deck",
                description=(
                    "Build an ENTIRE deck from one declarative spec in one call "
                    "- the fast path for multi-slide decks (one AppleScript "
                    "session per slide instead of one per element). Pass either "
                    "`spec` (JSON) or `markdown` (dialect: --- frontmatter with "
                    "title/theme/style/width/height/save_path; # title slide; "
                    "## new slide; bullets/numbered/quotes/code fences/images/"
                    "GitHub tables; ```chart fences with a JSON chart object; "
                    "'Notes:' paragraphs become speaker notes; "
                    "<!-- transition: push 1.0 --> and <!-- skip --> per slide; "
                    "any block may end with <!-- x=.. y=.. width=.. "
                    "font_size=.. column=left/right --> for explicit placement "
                    "or two-column flow). Spec shape: {title?, theme?, style?, "
                    "width?, height?, save_path?, on_exists?, slides: [{layout?, "
                    "title?/body? (theme placeholders), notes?, skipped?, "
                    "transition? {effect, duration?, delay?, automatic?}, "
                    "elements?: [{type: title|subtitle|text|bullets|numbered|"
                    "code|quote|image|shape|panel|table|chart|line, ...}]}]}. "
                    "Elements without x/y auto-flow inside style margins; "
                    "column:'left'/'right' makes two-column layouts. The whole "
                    "spec is validated before anything is created; per-element "
                    "failures are reported individually with the rest of the "
                    "deck still built. Element order = z-order (panels before "
                    "text). Returns per-slide element indices and settled "
                    "geometry. Re-running replaces the same file by default "
                    "(on_exists: replace|error|unique)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spec": {
                            "type": "object",
                            "description": "Deck spec (see tool description)",
                        },
                        "markdown": {
                            "type": "string",
                            "description": "Markdown-dialect deck source (alternative to spec)",
                        },
                        "save_path": {
                            "type": "string",
                            "description": "Where to save the .key (overrides spec.save_path)",
                        },
                        "style": {
                            "type": "string",
                            "description": (
                                "Style: built-in name (plain/boardroom/midnight/"
                                "editorial) or .toml path (overrides spec.style)"
                            ),
                        },
                    },
                },
            ),
            Tool(
                name="describe_deck",
                description=(
                    "Read an open presentation back into the build_deck spec "
                    "format (JSON): slides with layout, skipped, transition, "
                    "speaker notes, theme placeholders, and elements with "
                    "settled geometry (text items with font/size/color, images "
                    "with file names, shapes, tables with cell values, charts "
                    "geometry-only - Keynote exposes no chart data, lines). "
                    "Decks round-trip: feed the result back to build_deck, or "
                    "diff two describe_deck outputs in git."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
        ]

    # ---------------------------------------------------------------- build

    async def build_deck(
        self,
        spec: dict[str, Any] | None = None,
        markdown: str = "",
        save_path: str = "",
        style: str = "",
    ) -> list[TextContent]:
        try:
            if spec is None and not markdown:
                raise ParameterError("Pass either 'spec' (object) or 'markdown' (string).")
            if spec is not None and markdown:
                raise ParameterError("Pass only one of 'spec' or 'markdown', not both.")
            if markdown:
                spec = markdown_to_spec(markdown)
            if spec is None:  # pragma: no cover - guarded above
                raise ParameterError("No spec resolved.")

            errors = validate_spec(spec)
            if errors:
                listing = "\n".join(f"- {e}" for e in errors)
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Spec validation failed ({len(errors)} problem(s)); "
                            f"nothing was created:\n{listing}"
                        ),
                    )
                ]

            style_name = style or str(spec.get("style", ""))
            deck_style = resolve_style(style_name, near_path=save_path or spec.get("save_path", ""))
            theme = str(spec.get("theme", "") or deck_style.keynote_theme)
            width = int(spec.get("width") or deck_style.width)
            height = int(spec.get("height") or deck_style.height)
            title = str(spec.get("title", "") or "deck")
            on_exists = str(spec.get("on_exists", "replace"))
            if on_exists not in ("replace", "error", "unique"):
                raise ParameterError("on_exists must be replace, error, or unique.")

            raw_path = save_path or str(spec.get("save_path", "")) or _default_save_path(title)
            resolved_path = _normalize_key_path(raw_path)
            if os.path.exists(resolved_path):
                if on_exists == "error":
                    return [
                        TextContent(
                            type="text",
                            text=(
                                f"Failed to build deck: {resolved_path} already exists "
                                "and on_exists='error'. Use 'replace' or 'unique'."
                            ),
                        )
                    ]
                if on_exists == "unique":
                    stem, ext = os.path.splitext(resolved_path)
                    n = 2
                    while os.path.exists(f"{stem}-{n}{ext}"):
                        n += 1
                    resolved_path = f"{stem}-{n}{ext}"
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

            if not self.runner.check_keynote_running():
                self.runner.launch_keynote()

            # Session 1: replace any open doc at this path, create + save the
            # new document, and fetch the theme's layout names for validation.
            setup = self.runner.run(
                f"""
                on run argv
                    set themeName to item 1 of argv
                    set savePath to item 2 of argv
                    tell application "Keynote"
                        activate
                        repeat with d in documents
                            try
                                set f to file of d
                                if f is not missing value then
                                    if POSIX path of f is savePath then
                                        close d saving no
                                        exit repeat
                                    end if
                                end if
                            end try
                        end repeat
                        set themeNote to "theme: " & themeName
                        try
                            set newDoc to make new document with properties ¬
                                {{document theme:theme themeName, ¬
                                width:{width}, height:{height}}}
                        on error
                            set newDoc to make new document with properties ¬
                                {{width:{width}, height:{height}}}
                            set themeNote to "theme '" & themeName & "' not found, used default"
                        end try
                        save newDoc in POSIX file savePath
                        set layoutNames to name of every slide layout of newDoc
                        set AppleScript's text item delimiters to "|||"
                        set joined to layoutNames as text
                        set AppleScript's text item delimiters to ""
                        return (name of newDoc) & {_AS_FS} & themeNote & {_AS_FS} & joined
                    end tell
                end run
                """,
                theme,
                resolved_path,
            )
            doc_name, theme_note, layouts_joined = setup.split(_FS)
            layouts = {name.strip() for name in layouts_joined.split("|||")}

            # Validate every slide's layout against the live theme; a miss
            # deletes the fresh document so nothing half-built remains.
            layout_errors = []
            for i, slide in enumerate(spec["slides"]):
                wanted = slide.get("layout")
                if wanted and wanted not in layouts:
                    layout_errors.append(
                        f"slides[{i}].layout: {wanted!r} not in theme '{theme}' "
                        f"(available: {sorted(layouts)})"
                    )
            if layout_errors:
                self.runner.run(
                    'on run argv\ntell application "Keynote" to close document '
                    "(item 1 of argv) saving no\nend run",
                    doc_name,
                )
                if os.path.exists(resolved_path):
                    os.remove(resolved_path)
                listing = "\n".join(f"- {e}" for e in layout_errors)
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Layout validation failed; the fresh document was "
                            f"discarded:\n{listing}"
                        ),
                    )
                ]

            panels_dir = tempfile.mkdtemp(prefix="keynote-mcp-deck-")
            report: dict[str, Any] = {
                "document": doc_name,
                "path": resolved_path,
                "theme": theme_note,
                "style": deck_style.name,
                "size": f"{width}x{height}",
                "slides": [],
            }
            build_errors = 0

            # Sessions 2..: slides in batches of _SLIDES_PER_SESSION per
            # osascript call. Each slide's whole block sits in its own
            # AppleScript try (a failing slide reports and the batch
            # continues) and each element in a nested try (per-element
            # errors), so batching costs no error isolation.
            slide_reports: list[dict[str, Any]] = []
            for _slide in spec["slides"]:
                slide_reports.append({"slide": len(slide_reports) + 1, "elements": [], "errors": []})
            sessions = 2
            for batch_start in range(0, len(spec["slides"]), _SLIDES_PER_SESSION):
                batch = list(
                    enumerate(spec["slides"], start=1)
                )[batch_start : batch_start + _SLIDES_PER_SESSION]
                sessions += 1
                argv = Argv()
                argv.ref(doc_name)
                body: list[str] = []
                tags: dict[str, dict[str, Any]] = {}
                try:
                    for slide_no, slide in batch:
                        slide_report = slide_reports[slide_no - 1]
                        layout = slide.get("layout") or "Blank"
                        layout_ref = argv.ref(layout)
                        if slide_no == 1:
                            slide_setup = ["set targetSlide to slide 1 of targetDoc"]
                        else:
                            slide_setup = [
                                "set targetSlide to make new slide at end of slides of targetDoc"
                            ]
                        slide_setup.append(
                            f"set base layout of targetSlide to slide layout {layout_ref} of targetDoc"
                        )

                        placed, est_bottom = _flow_slide(dict(slide), deck_style, width, height)
                        limit = height - deck_style.margin_bottom(height)
                        if est_bottom > limit:
                            slide_report["warning"] = (
                                f"estimated content bottom ~{est_bottom:.0f}pt exceeds "
                                f"the {limit:.0f}pt bottom margin - check the settled "
                                "geometry below and consider splitting the slide"
                            )
                        inner: list[str] = []
                        prefix = f"s{slide_no}."
                        if slide.get("title") is not None or slide.get("body") is not None:
                            frag = placeholder_fragment(
                                argv,
                                f"{prefix}ph",
                                title=slide.get("title"),
                                body=slide.get("body"),
                            )
                            inner += _wrap_try(frag, f"{prefix}ph")
                        for j, el in enumerate(placed):
                            tag = f"{prefix}e{j}"
                            tags[tag] = el
                            inner += _wrap_try(
                                _element_fragment(el, tag, argv, deck_style, panels_dir), tag
                            )
                        if slide.get("notes"):
                            inner += _wrap_try(
                                notes_fragment(argv, str(slide["notes"])), f"{prefix}notes"
                            )
                        transition = slide.get("transition")
                        if transition:
                            inner += _wrap_try(
                                transition_fragment(
                                    effect=transition["effect"],
                                    duration=float(transition.get("duration", 1.0)),
                                    delay=float(transition.get("delay", 0.0)),
                                    automatic=bool(transition.get("automatic", False)),
                                ),
                                f"{prefix}transition",
                            )
                        if slide.get("skipped"):
                            inner += _wrap_try(skipped_fragment(True), f"{prefix}skipped")

                        body += [
                            "try",
                            *slide_setup,
                            "tell targetSlide",
                            *inner,
                            "end tell",
                            "on error errMsg number errNum",
                            f'set out to out & "ERR|{prefix}slide|" & errNum & "|" & '
                            "errMsg & linefeed",
                            "end try",
                        ]

                    script_body = "\n".join(body)
                    out = self.runner.run(
                        f"""
                        on run argv
                            set docName to item 1 of argv
                            tell application "Keynote"
                                {RESOLVE_DOC}
                                set out to ""
                                {script_body}
                                return out
                            end tell
                        end run
                        """,
                        *argv.values,
                        timeout=_SLIDE_SESSION_TIMEOUT,
                    )
                    for token in out.splitlines():
                        if not token.strip():
                            continue
                        parts = token.split("|")
                        if parts[0] == "ERR":
                            tag, err_num = parts[1], parts[2]
                            err_msg = "|".join(parts[3:])
                            slide_no_s, _, what = tag.removeprefix("s").partition(".")
                            slide_report = slide_reports[int(slide_no_s) - 1]
                            el = tags.get(tag, {})
                            slide_report["errors"].append(
                                {
                                    "element": el.get("type", what),
                                    "error": f"{err_msg} ({err_num})",
                                }
                            )
                            build_errors += 1
                        elif len(parts) > 1 and parts[1] == "placeholders-set":
                            slide_no_s = parts[0].removeprefix("s").partition(".")[0]
                            slide_reports[int(slide_no_s) - 1]["placeholders"] = "set"
                        else:
                            tag, index, pos, size = parts[0], parts[1], parts[2], parts[3]
                            slide_no_s = tag.removeprefix("s").partition(".")[0]
                            el = tags.get(tag, {})
                            slide_reports[int(slide_no_s) - 1]["elements"].append(
                                {
                                    "type": el.get("type", tag),
                                    "index": int(index),
                                    "position": pos,
                                    "size": size,
                                }
                            )
                except Exception as e:  # batch isolation: keep building later batches
                    for slide_no, _slide in batch:
                        slide_reports[slide_no - 1]["errors"].append(
                            {"element": "slide", "error": str(e)}
                        )
                        build_errors += 1
            report["slides"] = slide_reports

            # Final session: save.
            self.runner.run(
                """
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        save document docName
                        return count of slides of document docName
                    end tell
                end run
                """,
                doc_name,
            )

            summary = (
                f"Built {len(spec['slides'])}-slide deck '{doc_name}' at "
                f"{resolved_path} in {sessions} AppleScript sessions "
                f"({build_errors} element error(s))."
            )
            return [
                TextContent(
                    type="text",
                    text=summary + "\n" + json.dumps(report, indent=1),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to build deck: {e}")]

    # ------------------------------------------------------------- describe

    async def describe_deck(self, doc_name: str = "") -> list[TextContent]:
        try:
            head = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {RESOLVE_DOC}
                        return (name of targetDoc) & {_AS_FS} & ¬
                            (name of document theme of targetDoc) & {_AS_FS} & ¬
                            (width of targetDoc as text) & {_AS_FS} & ¬
                            (height of targetDoc as text) & {_AS_FS} & ¬
                            (count of slides of targetDoc as text)
                    end tell
                end run
                """,
                doc_name,
            )
            name, theme, width, height, slide_count = head.split(_FS)
            spec: dict[str, Any] = {
                "title": name.removesuffix(".key"),
                "theme": theme,
                "width": int(float(width)),
                "height": int(float(height)),
                "slides": [],
            }
            for n in range(1, int(slide_count) + 1):
                spec["slides"].append(self._describe_slide(doc_name, n))
            return [TextContent(type="text", text=json.dumps(spec, indent=1))]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to describe deck: {e}")]

    def _describe_slide(self, doc_name: str, slide_number: int) -> dict[str, Any]:
        raw = self.runner.run(
            f"""
            on run argv
                set docName to item 1 of argv
                set fs to character id 31
                set rs to character id 30
                tell application "Keynote"
                    {RESOLVE_DOC}
                    set s to slide {slide_number} of targetDoc
                    set out to "L" & fs & (name of base layout of s) & rs
                    set out to out & "K" & fs & (skipped of s as text) & rs
                    try
                        set tp to transition properties of s
                        set out to out & "X" & fs & (transition effect of tp as text) & ¬
                            fs & (transition duration of tp as text) & ¬
                            fs & (transition delay of tp as text) & ¬
                            fs & (automatic transition of tp as text) & rs
                    end try
                    set noteText to ""
                    try
                        set noteText to presenter notes of s as text
                    end try
                    if noteText is not "" then
                        set out to out & "N" & fs & noteText & rs
                    end if
                    tell s
                        set defT to missing value
                        set defB to missing value
                        try
                            set defT to default title item
                        end try
                        try
                            set defB to default body item
                        end try
                        if (title showing) and defT is not missing value then
                            set out to out & "PT" & fs & (object text of defT as text) & rs
                        end if
                        if (body showing) and defB is not missing value then
                            set out to out & "PB" & fs & (object text of defB as text) & rs
                        end if
                        set seenT to false
                        set seenB to false
                        repeat with i from 1 to (count of text items)
                            set ti to text item i
                            set phantom to false
                            if defT is not missing value and ti is defT then
                                set phantom to true
                                set seenT to true
                            else if defB is not missing value and ti is defB then
                                set phantom to true
                                set seenB to true
                            end if
                            if not phantom then
                                set p to position of ti
                                set f to ""
                                set z to ""
                                set c to ""
                                try
                                    set f to font of object text of ti as text
                                end try
                                try
                                    set z to size of object text of ti as text
                                end try
                                try
                                    set rgb to color of object text of ti
                                    set c to (item 1 of rgb as text) & "," & ¬
                                        (item 2 of rgb as text) & "," & (item 3 of rgb as text)
                                end try
                                set out to out & "T" & fs & (object text of ti as text) & ¬
                                    fs & (item 1 of p as text) & fs & (item 2 of p as text) & ¬
                                    fs & (width of ti as text) & fs & (height of ti as text) & ¬
                                    fs & f & fs & z & fs & c & rs
                            end if
                        end repeat
                        repeat with i from 1 to (count of images)
                            set im to image i
                            set p to position of im
                            set fn to ""
                            try
                                set fn to file name of im as text
                            end try
                            set out to out & "I" & fs & fn & fs & (item 1 of p as text) & ¬
                                fs & (item 2 of p as text) & fs & (width of im as text) & ¬
                                fs & (height of im as text) & rs
                        end repeat
                        repeat with i from 1 to (count of shapes)
                            set sh to shape i
                            set isPh to false
                            if defT is not missing value and sh is defT then set isPh to true
                            if defB is not missing value and sh is defB then set isPh to true
                            if not isPh then
                                set p to position of sh
                                set shTxt to ""
                                try
                                    set shTxt to object text of sh as text
                                end try
                                set out to out & "S" & fs & shTxt & fs & (item 1 of p as text) & ¬
                                    fs & (item 2 of p as text) & fs & (width of sh as text) & ¬
                                    fs & (height of sh as text) & fs & (opacity of sh as text) & rs
                            end if
                        end repeat
                        repeat with i from 1 to (count of tables)
                            set tb to table i
                            set p to position of tb
                            set rowsOut to ""
                            repeat with r from 1 to (row count of tb)
                                set rowTxt to ""
                                repeat with c from 1 to (column count of tb)
                                    if c > 1 then set rowTxt to rowTxt & tab
                                    set theCell to cell c of row r of tb
                                    set cellOut to ""
                                    try
                                        set fml to formula of theCell
                                        if fml is not missing value then set cellOut to fml
                                    end try
                                    if cellOut is "" then
                                        set v to value of theCell
                                        if v is not missing value then set cellOut to (v as text)
                                    end if
                                    set rowTxt to rowTxt & cellOut
                                end repeat
                                if rowsOut is not "" then set rowsOut to rowsOut & linefeed
                                set rowsOut to rowsOut & rowTxt
                            end repeat
                            set out to out & "B" & fs & (header row count of tb as text) & ¬
                                fs & (header column count of tb as text) & ¬
                                fs & (item 1 of p as text) & fs & (item 2 of p as text) & ¬
                                fs & (width of tb as text) & fs & (height of tb as text) & ¬
                                fs & rowsOut & rs
                        end repeat
                        repeat with i from 1 to (count of charts)
                            set ch to chart i
                            set p to position of ch
                            set out to out & "C" & fs & (item 1 of p as text) & ¬
                                fs & (item 2 of p as text) & fs & (width of ch as text) & ¬
                                fs & (height of ch as text) & rs
                        end repeat
                        repeat with i from 1 to (count of lines)
                            set ln to line i
                            set sp to start point of ln
                            set ep to end point of ln
                            set out to out & "G" & fs & (item 1 of sp as text) & ¬
                                fs & (item 2 of sp as text) & fs & (item 1 of ep as text) & ¬
                                fs & (item 2 of ep as text) & rs
                        end repeat
                    end tell
                    return out
                end tell
            end run
            """,
            doc_name,
            timeout=_SLIDE_SESSION_TIMEOUT,
        )
        slide: dict[str, Any] = {"elements": []}
        for record in raw.split(_RS):
            if not record:
                continue
            fields = record.split(_FS)
            kind = fields[0]
            if kind == "L":
                slide["layout"] = fields[1]
            elif kind == "K":
                if fields[1] == "true":
                    slide["skipped"] = True
            elif kind == "X":
                effect = fields[1].replace(" ", "_")
                if effect != "no_transition_effect":
                    slide["transition"] = {
                        "effect": effect,
                        "duration": float(fields[2]),
                        "delay": float(fields[3]),
                        "automatic": fields[4] == "true",
                    }
            elif kind == "N":
                slide["notes"] = fields[1]
            elif kind == "PT":
                slide["title"] = fields[1]
            elif kind == "PB":
                slide["body"] = fields[1]
            elif kind == "T":
                el: dict[str, Any] = {
                    "type": "text",
                    "text": fields[1],
                    "x": float(fields[2]),
                    "y": float(fields[3]),
                    "width": float(fields[4]),
                    "height": float(fields[5]),
                }
                if fields[6]:
                    el["font_name"] = fields[6]
                if fields[7]:
                    el["font_size"] = float(fields[7])
                if fields[8]:
                    el["color"] = fields[8]
                slide["elements"].append(el)
            elif kind == "I":
                slide["elements"].append(
                    {
                        "type": "image",
                        "path": fields[1],
                        "x": float(fields[2]),
                        "y": float(fields[3]),
                        "width": float(fields[4]),
                        "height": float(fields[5]),
                    }
                )
            elif kind == "S":
                el = {
                    "type": "shape",
                    "x": float(fields[2]),
                    "y": float(fields[3]),
                    "width": float(fields[4]),
                    "height": float(fields[5]),
                    "opacity": float(fields[6]),
                }
                if fields[1]:
                    el["text"] = fields[1]
                slide["elements"].append(el)
            elif kind == "B":
                data = (
                    [
                        [_parse_cell(c) for c in row.split("\t")]
                        for row in fields[7].split("\n")
                    ]
                    if fields[7]
                    else []
                )
                slide["elements"].append(
                    {
                        "type": "table",
                        "header_row": int(fields[1]) > 0,
                        "header_column": int(fields[2]) > 0,
                        "x": float(fields[3]),
                        "y": float(fields[4]),
                        "width": float(fields[5]),
                        "height": float(fields[6]),
                        "data": data,
                    }
                )
            elif kind == "C":
                slide["elements"].append(
                    {
                        "type": "chart",
                        "chart_type": None,
                        "note": ("chart data is not readable via AppleScript; geometry only"),
                        "x": float(fields[1]),
                        "y": float(fields[2]),
                        "width": float(fields[3]),
                        "height": float(fields[4]),
                    }
                )
            elif kind == "G":
                slide["elements"].append(
                    {
                        "type": "line",
                        "x1": float(fields[1]),
                        "y1": float(fields[2]),
                        "x2": float(fields[3]),
                        "y2": float(fields[4]),
                    }
                )
        return slide
