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

import difflib
import json
import math
import os
import re
import tempfile
from typing import Any

from mcp.types import TextContent, Tool

from ..utils import (
    SESSION,
    AppleScriptRunner,
    ParameterError,
    explain_unsupported,
    parse_color,
    rgb65535_to_hex,
    split_font_name,
)
from ..utils.render import render_panel_png
from ..utils.rendered_assets import decode_rendered_asset, panel_filename, stroke_filename
from ..utils.stroke import render_stroke_png
from ..utils.styles import DeckStyle, resolve_style
from .base import DocumentTargetedTools
from .fragments import (
    _RUN_SEP,
    CHART_TYPES,
    RESOLVE_DOC,
    TEXT_ITEM_FILTER,
    TEXT_RUNS_FRAGMENT,
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
    "description": "Document name. Optional: defaults to the session document set by the last create_presentation/open_presentation, or to the only open presentation. With several open and no session default, the call fails and names them rather than guessing.",
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
    "styled_line",
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

# describe_deck batches its full reads. Profiled on a 35-slide/735-element
# deck: one osascript call per slide cost 31.2 s, of which ~4.5 s was pure
# process + AppleEvent overhead (0.125 s x 36 calls). Batching removes that;
# the remainder is per-property reads, which only filtering can avoid.
_DESCRIBE_SLIDES_PER_SESSION = 10

# Beyond this, a full description is likely to blow a tool-output limit.
_LARGE_DESCRIPTION_CHARS = 60_000

_DASH_STYLES = frozenset({"solid", "dash", "dashed", "dot", "dotted", "dashdot", "dash-dot"})

_ALL_ELEMENT_CLASSES = frozenset({"text", "image", "shape", "table", "chart", "line"})


# What Keynote's AppleScript dictionary genuinely cannot report. Emitted with
# every full description, because a caller must be able to tell "this shape has
# no fill" from "this server did not look at the fill" - the field report had to
# recover five brand colours by screenshotting and eyeballing pixels, not
# knowing which of the two it was facing.
_UNREADABLE_NOTE: dict[str, str] = {
    "shape.fill_color": (
        "Not readable OR writable. `background fill type` gives the KIND of "
        "fill (color/gradient/image/none) and is reported as fill_type; the "
        "colour itself has no property. Probed across 5 themes and 12 routes."
    ),
    "shape.type": (
        "Not readable. There is no `shape type` term - a rounded rect, arrow, "
        "callout and circle are all just `shape`. AppleScript can only create "
        "rectangles."
    ),
    "shape.corner_radius": "Not readable. No corner-radius property exists.",
    "shape.stroke": "Not readable. No stroke/border term exists on any iWork class.",
    "line.stroke": (
        "Not readable. A line's complete property record is start/end point, "
        "position, width, height, rotation, reflection, locked - no colour, "
        "thickness, dash or arrowheads. Use styled_line to AUTHOR strokes; "
        "they are rendered PNGs and round-trip via their sidecar."
    ),
    "text.alignment": "Not readable. Alignment exists only on table ranges.",
    "text.underline": "Not readable. Rich text exposes only font, size and colour.",
    "chart.data": "Not readable. The chart class exposes only geometry.",
    "slide.background": "Not readable. No background term on `slide`; it lives in the layout.",
    "group.membership": (
        "Not readable. Groups are counted per slide but their members cannot "
        "be enumerated, and groups cannot be created at all."
    ),
    "z_order": (
        "NOT reported and NOT recoverable. Elements are enumerated class by "
        "class (text, then image, then shape, table, chart, line), so array "
        "position is neither an address nor paint order. Keynote's real "
        "z-order is creation order and AppleScript cannot read or change it."
    ),
}


# --------------------------------------------------------------------------
# The spec's key vocabulary
# --------------------------------------------------------------------------
#
# build_deck's `spec` is by far the largest model-authored input this server
# takes, and every unknown key in it was silently ignored at all three levels -
# deck, slide and element. That is the SAME failure 4.0.0 fixed at the
# tool-argument boundary, where a dropped `fill_color` was reported as success
# and read as "the server can set shape fill". Inside a spec it is worse: a
# 35-slide deck builds with zero errors while a mistyped `layuot`, an invented
# `fill_color` and a plausible-but-wrong `font` do nothing, and the render is
# the only place it shows.
#
# Three categories, deliberately distinct:
#
#   APPLIED    - the key does something. Unknown-key errors list these.
#   TOLERATED  - describe_deck EMITS it but build_deck cannot apply it (Keynote
#                has no write route, or it is pure addressing metadata). These
#                must not fail validation or `describe_deck -> build_deck`, the
#                whole point of the format, would break on its own output. They
#                are reported back in the build result instead of vanishing.
#   UNKNOWN    - everything else. Hard error, nothing is created.

_DECK_KEYS = frozenset(
    {"title", "theme", "style", "width", "height", "save_path", "on_exists", "slides"}
)
# describe_deck's own envelope, so its output feeds straight back in.
_DECK_TOLERATED = frozenset(
    {"slide_count", "not_reported", "note", "detail", "slide_range", "element_types"}
)

_SLIDE_KEYS = frozenset({"layout", "title", "body", "notes", "skipped", "transition", "elements"})
_SLIDE_TOLERATED = frozenset({"slide", "groups"})

_TRANSITION_KEYS = frozenset({"effect", "duration", "delay", "automatic"})

# Accepted on an element of ANY type: the flow engine and the named-layout
# vocabulary handle these generically.
_ELEMENT_COMMON = frozenset(
    {"type", "x", "y", "width", "height", "zone", "module", "index", "column"}
)
# Read-back detail describe_deck attaches to every element.
_ELEMENT_TOLERATED = frozenset(
    {
        "element_class",
        "placeholder",
        "rotation",
        "fill_type",
        "color_65535",
        "font_family",
        "font_weight",
        "font_style",
        "note",
        # decode_rendered_asset stamps this on a panel/styled_line it recovered
        # from a PNG filename, so a caller can tell a rendered workaround from
        # an image the user placed. It is a marker, not an input.
        "rendered",
    }
)

_TEXTUAL = ("title", "subtitle", "text", "code", "quote")

# Per type, the keys that DO something. `centered`, `role`, `font_name`,
# `font_size` and `color` are deliberately NOT common: `centered` on an image
# and `role` on a table are silently ignored by the builder, which is exactly
# the class of mistake this table exists to name.
_ELEMENT_KEYS: dict[str, frozenset[str]] = {
    **{
        t: frozenset({"text", "runs", "font_name", "font_size", "color", "role", "centered"})
        for t in _TEXTUAL
    },
    "bullets": frozenset({"items", "font_name", "font_size", "color"}),
    "numbered": frozenset({"items", "font_name", "font_size", "color"}),
    "image": frozenset({"path", "description"}),
    "panel": frozenset({"color", "radius", "opacity"}),
    "shape": frozenset({"text", "opacity"}),
    "table": frozenset(
        {
            "data",
            "header_row",
            "header_column",
            "column_widths",
            "font_name",
            "font_size",
        }
    ),
    "chart": frozenset({"chart_type", "row_names", "column_names", "data", "group_by"}),
    "line": frozenset({"x1", "y1", "x2", "y2"}),
    "styled_line": frozenset(
        {
            "x1",
            "y1",
            "x2",
            "y2",
            "connector",
            "color",
            "stroke_width",
            "dash",
            "start_arrow",
            "end_arrow",
            "opacity",
        }
    ),
}

# Per type, what describe_deck reports that build_deck cannot write back.
_ELEMENT_TYPE_TOLERATED: dict[str, frozenset[str]] = {
    **{t: frozenset({"opacity"}) for t in _TEXTUAL},
    "image": frozenset({"opacity"}),
    # A rendered panel/stroke is an IMAGE underneath, so describe_deck reports
    # the alt text Keynote holds for it. The builder writes its own
    # ("colored panel", "styled line (dotted, #000000)"), so it is not an
    # input - but it must round-trip.
    "panel": frozenset({"description"}),
    "styled_line": frozenset({"description"}),
    "shape": frozenset({"reflection_showing", "locked"}),
    "chart": frozenset({"chart_type"}),  # comes back null; must be re-supplied
}


# Near-misses where difflib either ties or misses outright, and the intent is
# unambiguous. `font` scores identically against `font_name` and `font_size`,
# and the wrong half of that coin flip sends a model to change the size.
_KEY_ALIASES: dict[str, str] = {
    "font": "font_name",
    "typeface": "font_name",
    "font_face": "font_name",
    "size": "font_size",
    "fontsize": "font_size",
    "text_size": "font_size",
    "colour": "color",
    "text_color": "color",
    "font_color": "color",
    "src": "path",
    "file": "path",
    "image": "path",
    "image_path": "path",
    "url": "path",
    "content": "text",
    "label": "text",
    "value": "text",
    "caption": "text",
    "body": "text",
    "bullets": "items",
    "list": "items",
    "rows": "data",
    "cells": "data",
    "speaker_notes": "notes",
    "presenter_notes": "notes",
    "name": "title",
    "slides_": "slides",
}


def _unknown_keys(
    node: dict[str, Any],
    accepted: frozenset[str],
    tolerated: frozenset[str],
    path: str,
    what: str,
    errors: list[str],
) -> None:
    """Reject keys that are neither applied nor a known read-back field.

    The message names what IS accepted here, and suggests a near miss, because
    the two ways a spec key goes wrong are a typo and a plausible invention -
    and a model cannot tell which it made from "ignored".
    """
    unknown = sorted(set(node) - accepted - tolerated)
    if not unknown:
        return
    for key in unknown:
        # An invented name for a capability Keynote does not have gets the real
        # explanation and the right alternative, exactly as at the tool-argument
        # boundary - the two share one table (utils/unsupported.py). Anything
        # else is treated as a typo and matched against the accepted keys.
        explained = explain_unsupported(key, argument_boundary=False)
        if explained:
            reason, alt = explained
            detail = f" Not a capability of Keynote's AppleScript ({reason})."
            if alt:
                detail += f" Use {alt}."
        else:
            alias = _KEY_ALIASES.get(key.lower())
            close = (
                [alias]
                if alias in accepted
                else difflib.get_close_matches(key, sorted(accepted), n=1, cutoff=0.6)
            )
            detail = f" Did you mean {close[0]!r}?" if close else ""
        errors.append(_err(f"{path}.{key}", f"unknown key for {what}.{detail}"))
    errors.append(
        _err(path, f"{what} accepts: {', '.join(sorted(accepted))}. Nothing was created.")
    )


# Tolerated keys that mean the rebuild LOSES something, as opposed to the ones
# that are merely derived or re-derivable. `font_family`/`font_weight`/
# `font_style` come FROM `font_name` and `color_65535` from `color`, both of
# which the builder does apply, so nothing is lost by ignoring them; a marker
# (`rendered`), a description the builder writes itself, and a `placeholder`
# that IS rebuilt (as slide.title/body) are likewise not losses. Listing those
# would bury the four entries below in noise on every single round trip.
_LOSSY_ELEMENT_KEYS = frozenset({"rotation", "opacity", "reflection_showing", "locked"})


def tolerated_keys(spec: dict[str, Any]) -> list[str]:
    """Keys a valid spec carries that the BUILDER genuinely will not apply.

    describe_deck reports rotation, per-element opacity, shape lock/reflection,
    hand-made groups and null chart data that Keynote gives no write route for.
    Accepting them is what keeps `describe_deck -> build_deck` working on its
    own output; REPORTING them is what keeps that from being a silent
    downgrade - which is the same defect this release fixed one level up.
    """
    found: set[str] = set()
    for slide in spec.get("slides", []):
        if not isinstance(slide, dict):
            continue
        if "groups" in slide:
            found.add("groups")
        for el in slide.get("elements", []) or []:
            if not isinstance(el, dict):
                continue
            hits = set(el) & _LOSSY_ELEMENT_KEYS
            if str(el.get("type")) == "panel":
                # A panel's opacity IS applied - it is rendered into the PNG.
                hits.discard("opacity")
            if el.get("type") == "chart" and el.get("chart_type") is None:
                found.add("chart_type")
            found |= hits
    return sorted(found)


def _set_color(node: dict[str, Any], triple: str) -> None:
    """Report colour as hex, keeping Keynote's raw 16-bit triple alongside.

    `color` is hex because that is what humans and CSS use, and because
    build_deck's parse_color accepts it verbatim, so round-trips still work.
    `color_65535` keeps the exact values Keynote gave, since the 16-bit->8-bit
    conversion is only exact for multiples of 257.
    """
    node["color"] = rgb65535_to_hex(triple) or triple
    node["color_65535"] = triple


def _as_bool(value: str) -> bool:
    return value == "true"


def _set_optional(el: dict[str, Any], key: str, fields: list[str], idx: int, cast: Any) -> None:
    """Copy fields[idx] onto the element if the read produced anything.

    An absent value means Keynote refused the property, not that it is zero.
    """
    if len(fields) > idx and fields[idx] != "":
        try:
            el[key] = cast(fields[idx])
        except (ValueError, TypeError):
            el[key] = fields[idx]


def _parse_runs(raw: str) -> list[dict[str, Any]]:
    """Parse the coalesced per-character styling into runs.

    A text box reports one font and colour; a title mixing three colours
    under-reports the palette entirely. `style_text_range` could always write
    runs - this is the missing read path.
    """
    runs: list[dict[str, Any]] = []
    for chunk in raw.split(_RUN_SEP):
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 5:
            continue
        run: dict[str, Any] = {"start": int(parts[0]), "end": int(parts[1])}
        if parts[2]:
            run.update(split_font_name(parts[2]))
        if parts[3]:
            try:
                run["font_size"] = float(parts[3])
            except ValueError:
                pass
        if parts[4]:
            _set_color(run, parts[4])
        runs.append(run)
    return runs


def _chunks(items: list[int], size: int) -> list[list[int]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_element_types(requested: list[str] | None) -> frozenset[str]:
    """Validate an element_types filter, or return every class."""
    if not requested:
        return _ALL_ELEMENT_CLASSES
    if isinstance(requested, str):  # tolerate a bare string
        requested = [requested]
    unknown = sorted(set(requested) - _ALL_ELEMENT_CLASSES)
    if unknown:
        raise ParameterError(
            f"Unknown element_types {unknown}; valid: {sorted(_ALL_ELEMENT_CLASSES)}."
        )
    return frozenset(requested)


def _parse_slide_range(spec: str, total: int) -> list[int]:
    """Parse "5", "1-10", "1-10,20,25-30" into a sorted list of slide numbers.

    Bounds are clamped to the deck and an empty result is an error rather than
    a silently empty description.
    """
    if not spec or not spec.strip():
        return list(range(1, total + 1))
    wanted: set[int] = set()
    for part in spec.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "-" in piece:
            lo_s, _, hi_s = piece.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                raise ParameterError(
                    f"Invalid slide_range segment {piece!r}; use forms like "
                    "'3', '1-10', or '1-10,20,25-30'."
                ) from None
            if lo > hi:
                raise ParameterError(f"slide_range {piece!r} runs backwards.")
            wanted.update(range(max(1, lo), min(total, hi) + 1))
        else:
            try:
                n = int(piece)
            except ValueError:
                raise ParameterError(
                    f"Invalid slide_range segment {piece!r}; use forms like "
                    "'3', '1-10', or '1-10,20,25-30'."
                ) from None
            if 1 <= n <= total:
                wanted.add(n)
    if not wanted:
        raise ParameterError(f"slide_range {spec!r} selects no slides; the deck has {total}.")
    return sorted(wanted)


def _round_slide_numbers(node: Any) -> None:
    """Round whole-valued floats to ints, in place.

    Keynote reports every coordinate as a float, so a real deck's description
    carried thousands of trailing '.0' - 2,415 of them in the 35-slide
    profiling deck - for no information at all.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, float) and value.is_integer():
                node[key] = int(value)
            else:
                _round_slide_numbers(value)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, float) and value.is_integer():
                node[i] = int(value)
            else:
                _round_slide_numbers(value)


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


def _validate_named_refs(el: dict[str, Any], path: str, errors: list[str], style: Any) -> None:
    """Check a spec's names against the style that will resolve them."""
    checks = (
        ("role", style.type, "type role"),
        ("connector", style.connectors, "connector"),
        ("zone", style.zones, "zone"),
        ("module", style.modules, "grid module"),
    )
    for key, table, label in checks:
        name = el.get(key)
        if name is not None and str(name) not in table:
            errors.append(
                _err(
                    f"{path}.{key}",
                    f"unknown {label} {name!r}; style {style.name!r} defines: "
                    f"{sorted(table) or '(none)'}",
                )
            )
    color = el.get("color", "")
    if isinstance(color, str) and color.startswith("@") and color[1:] not in style.palette:
        errors.append(
            _err(
                f"{path}.color",
                f"unknown palette colour {color!r}; style {style.name!r} defines: "
                f"{sorted(style.palette) or '(none)'}",
            )
        )


_RUN_KEYS = frozenset({"start", "end", "font_name", "font_size", "color", "role"})
# describe_deck reports these beside each run; they are derived, not settable.
_RUN_TOLERATED = frozenset({"font_family", "font_weight", "font_style", "color_65535"})


def _validate_runs(el: dict[str, Any], path: str, errors: list[str], style: Any) -> None:
    """Check a text element's ``runs`` against the text they address.

    Bounds are checked HERE rather than in AppleScript because `characters 5
    thru 40` of a 12-character string is a runtime error inside the batched
    session - it would fail one element deep in a built deck, which is exactly
    what validate-all-then-build exists to avoid.
    """
    runs = el.get("runs")
    if runs is None:
        return
    if not isinstance(runs, list) or not runs:
        errors.append(_err(f"{path}.runs", "must be a non-empty array of run objects"))
        return
    length = len(str(el.get("text", "")))
    for k, run in enumerate(runs):
        rpath = f"{path}.runs[{k}]"
        if not isinstance(run, dict):
            errors.append(_err(rpath, "run must be an object"))
            continue
        _unknown_keys(run, _RUN_KEYS, _RUN_TOLERATED, rpath, "a text run", errors)
        start, end = run.get("start"), run.get("end")
        if not isinstance(start, int) or isinstance(start, bool) or start < 1:
            errors.append(_err(f"{rpath}.start", "must be an integer >= 1 (1-based, inclusive)"))
            continue
        if not isinstance(end, int) or isinstance(end, bool) or end < start:
            errors.append(_err(f"{rpath}.end", f"must be an integer >= start ({start}), inclusive"))
            continue
        if end > length:
            errors.append(
                _err(
                    rpath,
                    f"covers characters {start}-{end} but the text is {length} "
                    f"character(s) long. Offsets are 1-based and INCLUSIVE, over "
                    f"the text as you wrote it.",
                )
            )
        _num(run.get("font_size"), f"{rpath}.font_size", errors, minimum=1)
        if not any(run.get(key) for key in ("font_name", "font_size", "color", "role")):
            errors.append(
                _err(
                    rpath,
                    "styles nothing: give a run at least one of color/font_name/font_size/role",
                )
            )
        if style is not None:
            _validate_named_refs(run, rpath, errors, style)
        color = run.get("color", "")
        if color and not str(color).startswith("@"):
            try:
                parse_color(str(color))
            except ParameterError as e:
                errors.append(_err(f"{rpath}.color", str(e)))


def _validate_element(el: Any, path: str, errors: list[str], style: Any = None) -> None:
    if not isinstance(el, dict):
        errors.append(_err(path, "element must be an object"))
        return
    etype = el.get("type")
    if etype not in _ELEMENT_TYPES:
        errors.append(
            _err(path, f"unknown element type {etype!r}; valid: {sorted(_ELEMENT_TYPES)}")
        )
        return
    _unknown_keys(
        el,
        _ELEMENT_COMMON | _ELEMENT_KEYS[str(etype)],
        _ELEMENT_TOLERATED | _ELEMENT_TYPE_TOLERATED.get(str(etype), frozenset()),
        path,
        f"an element of type {etype!r}",
        errors,
    )
    for key in ("x", "y", "width", "height", "font_size"):
        _num(el.get(key), f"{path}.{key}", errors, minimum=0)
    if el.get("index") is not None and (
        not isinstance(el.get("index"), int) or int(el["index"]) < 1
    ):
        errors.append(_err(f"{path}.index", "grid module index must be an integer >= 1"))
    if el.get("column") not in (None, "left", "right"):
        errors.append(_err(path, "column must be 'left' or 'right'"))
    color = el.get("color", "")
    if color and not str(color).startswith("@"):
        # "@name" is a palette reference resolved against the style; its
        # existence is checked by _validate_named_refs, not by parse_color.
        try:
            parse_color(str(color))
        except ParameterError as e:
            errors.append(_err(f"{path}.color", str(e)))
    if style is not None:
        _validate_named_refs(el, path, errors, style)

    if etype in ("title", "subtitle", "text", "code", "quote"):
        if not isinstance(el.get("text"), str) or not el.get("text"):
            errors.append(_err(path, f"{etype} needs a non-empty 'text' string"))
        else:
            _validate_runs(el, path, errors, style)
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
        # A named zone or grid module supplies the geometry at flow time, so
        # only a panel with neither needs all four spelled out.
        if not el.get("zone") and not el.get("module"):
            for key in ("x", "y", "width", "height"):
                if el.get(key) is None:
                    errors.append(
                        _err(
                            path,
                            f"panel needs explicit '{key}' (or a 'zone'/'module' "
                            "naming one of the style's)",
                        )
                    )
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
    elif etype in ("line", "styled_line"):
        for key in ("x1", "y1", "x2", "y2"):
            if _num(el.get(key), f"{path}.{key}", errors, minimum=0) is None:
                errors.append(_err(path, f"{etype} needs numeric '{key}'"))
        if etype == "styled_line":
            dash = el.get("dash", "solid")
            if dash not in _DASH_STYLES:
                errors.append(
                    _err(f"{path}.dash", f"{dash!r} invalid; valid: {sorted(_DASH_STYLES)}")
                )
            _num(el.get("stroke_width"), f"{path}.stroke_width", errors, minimum=0.1)


def validate_spec(spec: Any, style: DeckStyle | None = None) -> list[str]:
    """Validate a whole deck spec; returns ALL problems, not just the first.

    ``style`` is optional so existing callers and tests keep working, but when
    it IS given, every named reference (role, palette colour, connector, zone,
    grid module) is checked here rather than failing mid-build on slide 23.
    """
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    _unknown_keys(spec, _DECK_KEYS, _DECK_TOLERATED, "spec", "the deck", errors)
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
        _unknown_keys(slide, _SLIDE_KEYS, _SLIDE_TOLERATED, path, "a slide", errors)
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
                _unknown_keys(
                    transition,
                    _TRANSITION_KEYS,
                    frozenset(),
                    f"{path}.transition",
                    "a transition",
                    errors,
                )
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
            _validate_element(el, f"{path}.elements[{j}]", errors, style)
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
        # A named ZONE or grid MODULE resolves to coordinates before the flow
        # engine runs, so a spec can say "the 3rd account column" instead of
        # hand-computing x = 429 / 785 / 1141. Explicit x/y still win.
        if el.get("zone"):
            zone = style.zones.get(str(el["zone"]))
            if zone is None:
                raise ParameterError(
                    f"Unknown zone {el['zone']!r}. "
                    f"Style {style.name!r} defines: {sorted(style.zones) or '(none)'}"
                )
            for key in ("x", "y", "width", "height"):
                if key in zone and el.get(key) is None:
                    el[key] = float(zone[key])
        if el.get("module"):
            mx, my, mw, mh = style.module_origin(str(el["module"]), int(el.get("index", 1)))
            for key, value in (("x", mx), ("y", my), ("width", mw), ("height", mh)):
                if el.get(key) is None and value:
                    el[key] = value
        column = el.pop("column", None)
        # Only a FULLY placed element skips the flow. Pinning one coordinate
        # used to opt out of layout entirely, which left the other coordinate
        # unset - so `{"column": "left", "y": 550}` and `{"column": "right",
        # "y": 550}` both drew at x=0, on top of each other, and a plain
        # `{"type": "title", "y": 60}` drew flush against the slide edge while
        # every other element sat at the style margin. Both cases built with
        # zero errors and round-tripped cleanly through describe_deck; the
        # first was caught by a rendered check, the second by watching a model
        # use the tool. Pinned values still win: the setdefault calls below
        # never overwrite one.
        fully_placed = el.get("x") is not None and el.get("y") is not None
        if etype in ("panel", "line", "styled_line", "shape") or fully_placed:
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
        # A pinned y is where the element really goes, so the column cursor
        # has to advance from there, not from where the flow would have put it.
        y = el["y"] if el.get("y") is not None else cursors[cursor_key]

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


def _resolve_runs(raw: Any, style: DeckStyle) -> list[dict[str, Any]] | None:
    """Turn a spec's ``runs`` into what ``text_run_lines`` consumes.

    Resolves each run's colour through the style (so `@brand.maroon` works in a
    run exactly as it does on an element) and drops the read-only companions
    describe_deck reports alongside - `font_family`/`font_weight`/`font_style`
    are DERIVED from `font_name`, and `color_65535` is the same colour `color`
    already carries. A run that names a `role` takes that type style's font,
    size and colour, so a spec can say what a run MEANS.
    """
    if not raw:
        return None
    resolved: list[dict[str, Any]] = []
    for run in raw:
        named: dict[str, Any] = dict(style.type_role(str(run["role"]))) if run.get("role") else {}
        out: dict[str, Any] = {"start": int(run["start"]), "end": int(run["end"])}
        font = run.get("font_name") or named.get("font")
        if font:
            out["font_name"] = str(font)
        raw_size = run.get("font_size")
        size = raw_size if raw_size is not None else named.get("size")
        if size is not None:
            out["font_size"] = float(size)
        color = style.resolve_color(str(run.get("color", ""))) or style.resolve_color(
            str(named.get("color", ""))
        )
        if color:
            out["color_rgb"] = parse_color(color)
        resolved.append(out)
    return resolved


def _element_fragment(
    el: dict[str, Any], tag: str, argv: Argv, style: DeckStyle, panels_dir: str
) -> list[str]:
    etype = el["type"]
    # A "@name" colour is a reference into the style's palette, so a spec can
    # say what a colour MEANS ("@zone.private") instead of repeating a hex.
    color = style.resolve_color(str(el.get("color", "")))
    if etype in ("title", "subtitle", "text", "code", "quote"):
        # `role` names one of the style's own type styles (label.service,
        # chip.badge, ...). 22 named roles against 5 element-keyed slots was
        # the single largest source of duplication in a real spec.
        named: dict[str, Any] = dict(style.type_role(str(el["role"]))) if el.get("role") else {}
        role = {"text": "body"}.get(etype, etype)
        font = str(el.get("font_name") or named.get("font") or getattr(style, f"{role}_font"))
        raw_size = el.get("font_size") or named.get("size") or getattr(style, f"{role}_size")
        size = float(raw_size) if raw_size is not None else None
        rgb = parse_color(
            color
            or style.resolve_color(str(named.get("color", "")))
            or getattr(style, f"{role}_color")
        )
        text = el["text"]
        run_offset = 0
        if etype == "quote":
            text = f"“{text}”"
            # The builder adds the curly quotes, so the caller's character 1 is
            # Keynote's character 2. Runs are written against the text the
            # caller wrote, not against what got stored.
            run_offset = 1
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
            runs=_resolve_runs(el.get("runs"), style),
            run_offset=run_offset,
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
        # Parameters live in the FILENAME so the panel round-trips - see
        # utils/rendered_assets.py. `tag` keeps it unique within the deck.
        png_path = os.path.join(
            panels_dir,
            panel_filename(
                rgb65535_to_hex(",".join(str(c) for c in rgb)),
                radius,
                el.get("opacity", 100),
                tag.lower().replace(".", ""),
            ),
        )
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
    if etype == "styled_line":
        # Keynote has no stroke API at all, so a connector whose colour/dash
        # carries meaning is a rendered PNG. Its parameters go in the filename
        # so describe_deck reports it back as a styled_line, not an anonymous
        # image - see utils/rendered_assets.py.
        # `connector` names one of the style's semantic strokes ("data",
        # "denied", "logStream"), so a diagram declares MEANING and the style
        # owns what that looks like.
        conn = style.connector(str(el["connector"])) if el.get("connector") else {}
        srgb = parse_color(
            color or style.resolve_color(str(conn.get("color", ""))) or "#000000"
        ) or (0, 0, 0)
        hex_color = rgb65535_to_hex(",".join(str(c) for c in srgb))
        stroke_w = float(el.get("stroke_width", conn.get("width", 2.0)))
        dash = str(el.get("dash", conn.get("dash", "solid")))
        start_arrow = bool(el.get("start_arrow", conn.get("start_arrow", False)))
        end_arrow = bool(el.get("end_arrow", conn.get("end_arrow", False)))
        scratch_png = os.path.join(panels_dir, f"{tag}-stroke.png")
        ox, oy, box_w, box_h, _pw, _ph = render_stroke_png(
            scratch_png,
            el["x1"],
            el["y1"],
            el["x2"],
            el["y2"],
            rgb_65535=srgb,
            width_pt=stroke_w,
            dash=dash,
            start_arrow=start_arrow,
            end_arrow=end_arrow,
            opacity=float(el.get("opacity", 100)),
        )
        png_path = os.path.join(
            panels_dir,
            stroke_filename(
                hex_color,
                stroke_w,
                dash,
                start_arrow,
                end_arrow,
                tag.lower().replace(".", ""),
                offsets=(el["x1"] - ox, el["y1"] - oy, el["x2"] - ox, el["y2"] - oy),
            ),
        )
        os.rename(scratch_png, png_path)
        return image_fragment(
            argv,
            tag,
            png_path,
            x=ox,
            y=oy,
            width=box_w,
            height=box_h,
            description=f"styled line ({dash}, {hex_color})",
        )
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


class DeckTools(DocumentTargetedTools):
    """build_deck / describe_deck."""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="build_deck",
                description=(
                    "START HERE to create a presentation, or to rebuild an "
                    "existing one substantially. Builds the WHOLE deck - "
                    "document, slides, text, bullets, tables, charts, panels, "
                    "images, speaker notes, transitions - from one declarative "
                    "spec in ONE call. The alternative is roughly five "
                    "primitive calls per slide (measured on a 20-slide deck: 1 "
                    "call here vs 81 with create_presentation + add_slide + "
                    "add_title + add_bullet_list + ...), and every one of those "
                    "calls is a place to lose a returned index, mis-place an "
                    "element, or half-build a deck. Use the add_* primitives to "
                    "EDIT a deck that already exists; use this to author one. "
                    "To revise a deck you built: describe_deck to get its spec "
                    "back, edit the spec, build_deck again. Pass either "
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
                    "elements?: [{type: <one of the types below>, ...}]}]}. "
                    "Every element object carries `type`. Element types and "
                    "their required fields: title/subtitle/text/code/quote need `text`; "
                    "bullets/numbered need `items` (a list of strings); image "
                    "needs `path`; table needs `data` (2-D array, min 2x2); "
                    "chart needs `chart_type`, `row_names`, `column_names`, "
                    "`data` (rows x columns), optional `group_by`; panel needs "
                    "`x`,`y`,`width`,`height` (or a `zone`/`module` naming the "
                    "style's) plus optional `color`, `radius`; "
                    "line needs `x1`,`y1`,`x2`,`y2`; styled_line needs the same "
                    "plus optional `connector`/`color`/`stroke_width`/`dash`/"
                    "`start_arrow`/`end_arrow`; shape needs nothing. "
                    "Any element also takes x/y/width/height, font_size, "
                    "font_name, and color as `#RRGGBB` or `r,g,b`, plus `role` "
                    "(a named type style), `zone`/`module`+`index` (named "
                    "layout) and `@name` colors from the style's palette. "
                    "MIXED STYLING INSIDE ONE LINE: a text/title/subtitle/code/"
                    "quote element takes `runs`: [{start, end, color?, "
                    "font_name?, font_size?, role?}] - 1-based INCLUSIVE "
                    "character offsets over the text as you wrote it, each run "
                    "overriding the element's own font/size/color. That is how "
                    "you author a heading in three colours in ONE call instead "
                    "of the element plus three style_text_range calls, and "
                    "describe_deck reports runs in the same shape, so they "
                    "survive a rebuild. Offsets past the end of the text are a "
                    "validation error, not a half-styled title. "
                    "UNKNOWN KEYS ARE REJECTED at every level - deck, slide, "
                    "element, run - and the error names what IS accepted there. "
                    "Nothing is created when validation fails, so a typo costs "
                    "one call, not a deck that looks wrong for reasons nothing "
                    "reported. "
                    "`style` is a built-in name (plain, boardroom, midnight, "
                    "editorial, sdh) or a path to a .toml style file; the "
                    "markdown ```chart fence "
                    "takes the same fields as a JSON chart element. "
                    "\n\nLIMITS THAT SHAPE A SPEC - all probed, see "
                    "docs/CEILING.md. Read these BEFORE laying out a deck; "
                    "several cannot be corrected after the fact:\n"
                    "* NO FILL. Keynote's AppleScript cannot set a shape's fill "
                    "color at all. Every colored zone, card or container must be "
                    "type:'panel' (a rendered PNG, exact color, supports "
                    "`radius`). type:'shape' gives you the THEME's fill and only "
                    "`opacity` on top of it.\n"
                    "* NO STROKE. Lines have no color/width/dash/arrowhead "
                    "property. type:'line' is a plain native line; use "
                    "type:'styled_line' when the stroke carries meaning - it "
                    "renders a PNG and round-trips.\n"
                    "* Z-ORDER IS SPEC ORDER, permanently. AppleScript cannot "
                    "reorder. Emit background panels BEFORE the text and icons "
                    "on them. A mis-ordered element means rebuilding the slide.\n"
                    "* NO GROUPING. `make new group` is a silent no-op, so a "
                    "'component' is always several loose elements emitted in "
                    "order.\n"
                    "* THEME PLACEHOLDER GEOMETRY IS FIXED. A slide's `title`/"
                    "`body` fill the theme's placeholders, wherever the layout "
                    "puts them; their position and size cannot be read or set. "
                    "If your design places its heading somewhere specific, author "
                    "it as a text ELEMENT with x/y instead of as `title`.\n"
                    "* ALSO ABSENT: text alignment (use `centered`), underline, "
                    "bold/italic as attributes (pass the bold FACE name as "
                    "font_name), per-slide backgrounds, shadows, gradients, "
                    "non-rectangular shapes, routed connectors, and chart data "
                    "editing after creation.\n"
                    "Elements without x/y auto-flow inside style margins "
                    "(pin one coordinate and the other still comes from the "
                    "flow); "
                    "column:'left'/'right' makes two-column layouts. The whole "
                    "spec is validated before anything is created; per-element "
                    "failures are reported individually with the rest of the "
                    "deck still built. Element order = z-order (panels before "
                    "text). Returns per-slide element indices and settled "
                    "geometry. This CREATES a document at save_path (`~` is "
                    "expanded); it never edits the front document. Re-running "
                    "replaces the same file by default (on_exists: "
                    "replace|error|unique). If a spec will not validate, the "
                    "add_* primitives still work - the guidance above is about "
                    "round trips, not a prohibition."
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
                    "format (JSON). This is the first step for reworking an "
                    "existing deck: describe_deck -> edit the spec -> build_deck, "
                    "instead of a long chain of per-element edits. Decks "
                    "round-trip: feed the result straight back to build_deck, or "
                    "diff two describe_deck outputs in git.\n"
                    "ON A REAL DECK, START WITH detail='summary' (one fast call: "
                    "per-slide element counts and titles), then pull the slides "
                    "you care about with slide_range. A full description of a "
                    "35-slide deck is ~125,000 characters and can exceed a "
                    "tool-output limit; the payload says so when it is large.\n"
                    "\nRETURN SHAPE. Top level: {title, theme, width, height, "
                    "slide_count, slides: [...], not_reported: {...}} plus "
                    "`slide_range`/`element_types` echoed when you filtered, "
                    "`detail:'summary'` on the summary path, and a `note` when "
                    "the payload is large. `not_reported` (full detail only) "
                    "lists what Keynote refuses to expose - read it before "
                    "concluding a deck lacks something; it is how you tell 'no "
                    "fill' from 'fill not readable', and it names Z-ORDER as "
                    "unrecoverable.\n"
                    "Each slide: {slide, layout, skipped?, transition? "
                    "{effect,duration,delay,automatic}, notes?, title?/body? "
                    "(theme placeholder text), elements: [...], groups? "
                    "{count,note} for groups the user made by hand}.\n"
                    "\nEVERY element carries `element_class` (Keynote's class: "
                    "text item / image / shape / table / chart / line) and "
                    "`index` - the 1-based index the other tools consume. ARRAY "
                    "POSITION IS NOT AN ADDRESS and is not z-order; pass "
                    "`index`, never the position in the list (docs/"
                    "INDEX_CONTRACT.md). Per type:\n"
                    "* TEXT (type:'text'): text, x/y/width/height, `font_name` "
                    "(the PostScript face, which is what you pass back) plus the "
                    "decomposed `font_family`/`font_weight`/`font_style` for "
                    "auditing, `font_size`, `color` as #RRGGBB with the exact "
                    "16-bit `color_65535` beside it, and `rotation`/`opacity`/"
                    "`fill_type` when Keynote reports them. `placeholder`: "
                    "'title' or 'body' marks a THEME placeholder - it is emitted "
                    "as an ordinary indexed element AND as the slide's "
                    "title/body, so this listing and get_slide_content agree.\n"
                    "* `runs`: present only when a text item is NOT uniform - a "
                    "list of {start, end, font_name/font_family/font_weight/"
                    "font_style, font_size, color, color_65535} over 1-based "
                    "INCLUSIVE character offsets, covering the whole string. A "
                    "title mixing three colours reports one at the top level and "
                    "all three here. build_deck accepts `runs` verbatim, so "
                    "mixed-colour headings survive the round trip.\n"
                    "* IMAGE: path (a BASENAME once the source file is gone - "
                    "Keynote stores no path; use export_assets), geometry, "
                    "rotation/opacity/description. A panel or connector THIS "
                    "server rendered comes back decoded as type:'panel' "
                    "{color,radius,opacity} or type:'styled_line' {x1,y1,x2,y2,"
                    "color,stroke_width,dash,start_arrow,end_arrow}, not as an "
                    "anonymous image, because the parameters live in the "
                    "filename.\n"
                    "* SHAPE: text?, geometry, opacity, rotation, `fill_type` "
                    "(the KIND of fill; the colour is not readable at all), "
                    "reflection_showing, locked.\n"
                    "* TABLE: data (cell values; formulas come back as '=' "
                    "strings), header_row/header_column, geometry.\n"
                    "* CHART: geometry only, with `chart_type: null` and a note - "
                    "AppleScript exposes no chart data. Rebuilding as-is is "
                    "correctly REJECTED; supply chart_type/row_names/"
                    "column_names/data yourself.\n"
                    "* LINE: x1,y1,x2,y2, rotation."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_range": {
                            "type": "string",
                            "description": (
                                "Slides to describe, e.g. '3', '1-10', or "
                                "'1-10,20,25-30'. Default: every slide."
                            ),
                        },
                        "element_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["text", "image", "shape", "table", "chart", "line"],
                            },
                            "description": (
                                "Only read these element classes. Skipped classes "
                                "are not read at all, so this is a speedup as well "
                                "as a smaller payload. Default: all."
                            ),
                        },
                        "detail": {
                            "type": "string",
                            "enum": ["full", "summary"],
                            "description": (
                                "'full' (default) = geometry and styling for every "
                                "element. 'summary' = per-slide element counts and "
                                "titles only, in ONE osascript call (0.3s vs 31s on "
                                "a 35-slide deck). Start here on an unfamiliar deck."
                            ),
                        },
                        "round_coordinates": {
                            "type": "boolean",
                            "description": (
                                "Round whole-valued coordinates to integers "
                                "(default true). Keynote reports every coordinate "
                                "as a float; the trailing '.0' was ~2% of the "
                                "payload and carried no information."
                            ),
                        },
                        "include_text_runs": {
                            "type": "boolean",
                            "description": (
                                "Read per-run text styling (default true): the "
                                "`runs` array on any text item that is not "
                                "uniform. Costs three Apple events per text item "
                                "and is the largest contributor to the payload on "
                                "a type-heavy deck. Pass false when you only need "
                                "geometry and the box-level font - but a heading "
                                "that mixes colours will then report just one."
                            ),
                        },
                    },
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

            # The style is resolved BEFORE validation so every named reference
            # (role, palette colour, connector, zone, grid module) is checked
            # up front, with the rest of the spec, instead of failing mid-build.
            style_name = style or str(spec.get("style", ""))
            deck_style = resolve_style(style_name, near_path=save_path or spec.get("save_path", ""))

            errors = validate_spec(spec, deck_style)
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
            # The deck a caller just built is what the next call means, exactly
            # as for create_presentation/open_presentation.
            SESSION.set_default(doc_name)

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
            # Keys the spec carries that Keynote gives no way to write. They are
            # ACCEPTED so describe_deck's own output rebuilds, but saying so is
            # the difference between a round trip and a silent downgrade - the
            # same reason unknown keys are now rejected outright.
            not_applied = tolerated_keys(spec)
            if not_applied:
                report["not_applied"] = {
                    "keys": not_applied,
                    "note": (
                        "Present in the spec and accepted, but NOT written: "
                        "Keynote's AppleScript has no write route for these. "
                        "They survive a describe_deck round trip as data only. "
                        "rotation/opacity on an existing element can be set "
                        "afterwards with set_element_style / set_element_opacity; "
                        "a chart's data cannot be set at all after creation."
                    ),
                }
            build_errors = 0

            # Sessions 2..: slides in batches of _SLIDES_PER_SESSION per
            # osascript call. Each slide's whole block sits in its own
            # AppleScript try (a failing slide reports and the batch
            # continues) and each element in a nested try (per-element
            # errors), so batching costs no error isolation.
            slide_reports: list[dict[str, Any]] = []
            for _slide in spec["slides"]:
                slide_reports.append(
                    {"slide": len(slide_reports) + 1, "elements": [], "errors": []}
                )
            sessions = 2
            for batch_start in range(0, len(spec["slides"]), _SLIDES_PER_SESSION):
                batch = list(enumerate(spec["slides"], start=1))[
                    batch_start : batch_start + _SLIDES_PER_SESSION
                ]
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

                        # A THEME placeholder is reported by describe_deck twice
                        # on purpose - as slide.title/body for rebuilding, and as
                        # an indexed element so this listing and
                        # get_slide_content agree on what "text item i" is (see
                        # docs/INDEX_CONTRACT.md). Building both would put the
                        # heading on the slide twice: once in the placeholder,
                        # once as a loose text box on top of it. The placeholder
                        # form wins, because only it carries the theme's styling.
                        authored = dict(slide)
                        authored["elements"] = [
                            el
                            for el in (slide.get("elements") or [])
                            if not (isinstance(el, dict) and el.get("placeholder"))
                        ]
                        placed, est_bottom = _flow_slide(authored, deck_style, width, height)
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

    async def describe_deck(
        self,
        doc_name: str = "",
        slide_range: str = "",
        element_types: list[str] | None = None,
        detail: str = "full",
        round_coordinates: bool = True,
        include_text_runs: bool = True,
    ) -> list[TextContent]:
        try:
            doc_name = self._doc(doc_name)
            if detail not in ("full", "summary"):
                raise ParameterError(f"detail must be 'full' or 'summary', got {detail!r}.")
            want = _parse_element_types(element_types)
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
            total = int(slide_count)
            numbers = _parse_slide_range(slide_range, total)
            spec: dict[str, Any] = {
                "title": name.removesuffix(".key"),
                "theme": theme,
                "width": int(float(width)),
                "height": int(float(height)),
                "slide_count": total,
                "slides": [],
            }
            if numbers != list(range(1, total + 1)):
                spec["slide_range"] = slide_range or f"{numbers[0]}-{numbers[-1]}"
            if want != _ALL_ELEMENT_CLASSES:
                spec["element_types"] = sorted(want)

            if detail == "summary":
                spec["detail"] = "summary"
                spec["slides"] = self._summarize_slides(doc_name, numbers)
                spec["note"] = (
                    "Summary detail: per-slide element counts and titles only. "
                    "Call again with detail='full' (optionally with slide_range) "
                    "for geometry and styling."
                )
            else:
                slides: list[dict[str, Any]] = []
                for chunk in _chunks(numbers, _DESCRIBE_SLIDES_PER_SESSION):
                    slides.extend(self._describe_slides(doc_name, chunk, want, include_text_runs))
                if round_coordinates:
                    for sl in slides:
                        _round_slide_numbers(sl)
                spec["slides"] = slides
                spec["not_reported"] = dict(_UNREADABLE_NOTE)
            payload = json.dumps(spec, indent=1)
            if detail == "full" and len(payload) > _LARGE_DESCRIPTION_CHARS:
                # Say so in the payload rather than letting the caller discover
                # it by blowing a tool-output limit, which is how the field
                # report found out (137,091 characters, hard-failed).
                spec["note"] = (
                    f"This description is {len(payload):,} characters. If that is "
                    "too large for one tool result, call again with "
                    "detail='summary' for the map, then slide_range='1-10' (and "
                    "optionally element_types) for the parts you need."
                )
                payload = json.dumps(spec, indent=1)
            return [TextContent(type="text", text=payload)]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to describe deck: {e}")]

    def _summarize_slides(self, doc_name: str, numbers: list[int]) -> list[dict[str, Any]]:
        """Per-slide counts and titles for the whole deck in ONE call.

        Measured on the 35-slide/735-element profiling deck: 0.3 s, against
        31.2 s for the full read. This is the path that makes describe_deck
        usable on a real deck at all - the field report's deck blew both the
        tool-output limit (137,091 chars) and the 120 s timeout.
        """
        slide_list = ", ".join(str(n) for n in numbers)  # validated ints only
        filter_block = TEXT_ITEM_FILTER
        raw = self.runner.run(
            f"""
            on run argv
                set docName to item 1 of argv
                set fs to character id 31
                set rs to character id 30
                set runsep to character id 29
                set out to ""
                tell application "Keynote"
                    {RESOLVE_DOC}
                    repeat with slideNum in {{{slide_list}}}
                        tell slide slideNum of targetDoc
{filter_block}
                            set titleText to ""
                            try
                                if title showing then ¬
                                    set titleText to (object text of default title item as text)
                            end try
                            if titleText is "" then
                                repeat with n from 1 to (count of realIndices)
                                    set cand to (object text of ¬
                                        text item ((item n of realIndices) as integer) as text)
                                    if cand is not "" then
                                        set titleText to cand
                                        exit repeat
                                    end if
                                end repeat
                            end if
                            set out to out & (slideNum as text) & fs & ¬
                                (count of realIndices as text) & fs & ¬
                                (count of images as text) & fs & ¬
                                (count of shapes as text) & fs & ¬
                                (count of tables as text) & fs & ¬
                                (count of charts as text) & fs & ¬
                                (count of lines as text) & fs & ¬
                                (skipped of slide slideNum of targetDoc as text) & fs & ¬
                                titleText & rs
                        end tell
                    end repeat
                    return out
                end tell
            end run
            """,
            doc_name,
            timeout=_SLIDE_SESSION_TIMEOUT,
        )
        out: list[dict[str, Any]] = []
        for record in raw.split(_RS):
            if not record:
                continue
            f = record.split(_FS)
            counts = {
                "text": int(f[1]),
                "image": int(f[2]),
                "shape": int(f[3]),
                "table": int(f[4]),
                "chart": int(f[5]),
                "line": int(f[6]),
            }
            entry: dict[str, Any] = {
                "slide": int(f[0]),
                "elements": sum(counts.values()),
                "counts": {k: v for k, v in counts.items() if v},
            }
            if f[7] == "true":
                entry["skipped"] = True
            if len(f) > 8 and f[8]:
                entry["title"] = f[8]
            out.append(entry)
        return out

    def _describe_slides(
        self,
        doc_name: str,
        numbers: list[int],
        element_types: frozenset[str] | None = None,
        include_text_runs: bool = True,
    ) -> list[dict[str, Any]]:
        """Describe several slides in ONE osascript session.

        Profiled on a 35-slide/735-element deck: the old one-call-per-slide
        shape spent 31.2 s, of which ~4.5 s was pure process/AppleEvent
        overhead (0.125 s x 36 calls) and the rest per-property reads. Batching
        removes the overhead; `element_types` removes whole read loops, which
        is a real speedup rather than just a smaller payload.
        """
        want = element_types or _ALL_ELEMENT_CLASSES
        filter_block = TEXT_ITEM_FILTER
        # Three extra AppleEvents per text item buys full per-run styling; the
        # naive per-character read would be one event per CHARACTER.
        runs_block = (
            TEXT_RUNS_FRAGMENT
            if include_text_runs
            else '                            set runsOut to ""'
        )
        slide_list = ", ".join(str(n) for n in numbers)  # validated ints only
        raw = self.runner.run(
            f"""
            on run argv
                set docName to item 1 of argv
                set fs to character id 31
                set rs to character id 30
                set runsep to character id 29
                set out to ""
                tell application "Keynote"
                    {RESOLVE_DOC}
                  repeat with slideNum in {{{slide_list}}}
                    set s to slide slideNum of targetDoc
                    set out to out & "D" & fs & (slideNum as text) & rs
                    set out to out & "L" & fs & (name of base layout of s) & rs
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
{filter_block}
                        -- slide.title / slide.body stay for round-trip rebuild,
                        -- but the placeholder is ALSO emitted as a normal
                        -- indexed element below, so describe_deck and
                        -- get_slide_content agree on what "text item i" means.
                        -- See docs/INDEX_CONTRACT.md.
                        if (title showing) and defT is not missing value then
                            set out to out & "PT" & fs & (object text of defT as text) & rs
                        end if
                        if (body showing) and defB is not missing value then
                            set out to out & "PB" & fs & (object text of defB as text) & rs
                        end if
                        repeat with n from 1 to {"(count of realIndices)" if "text" in want else "0"}
                            set i to (item n of realIndices) as integer
                            set role to item n of realRoles
                            set ti to text item i
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
                            set rot to ""
                            set opa to ""
                            set fillT to ""
                            try
                                set rot to rotation of ti as text
                            end try
                            try
                                set opa to opacity of ti as text
                            end try
                            try
                                set fillT to background fill type of ti as text
                            end try
{runs_block}
                            set out to out & "T" & fs & (object text of ti as text) & ¬
                                fs & (item 1 of p as text) & fs & (item 2 of p as text) & ¬
                                fs & (width of ti as text) & fs & (height of ti as text) & ¬
                                fs & f & fs & z & fs & c & fs & (i as text) & fs & role & ¬
                                fs & rot & fs & opa & fs & fillT & fs & runsOut & rs
                        end repeat
                        repeat with i from 1 to {"(count of images)" if "image" in want else "0"}
                            set im to image i
                            set p to position of im
                            set fn to ""
                            try
                                set srcFile to file of im
                                if srcFile is not missing value then
                                    set fn to POSIX path of srcFile
                                end if
                            end try
                            if fn is "" then
                                try
                                    set fn to file name of im as text
                                end try
                            end if
                            set irot to ""
                            set iopa to ""
                            set idesc to ""
                            try
                                set irot to rotation of im as text
                            end try
                            try
                                set iopa to opacity of im as text
                            end try
                            try
                                set idesc to description of im as text
                            end try
                            set out to out & "I" & fs & fn & fs & (item 1 of p as text) & ¬
                                fs & (item 2 of p as text) & fs & (width of im as text) & ¬
                                fs & (height of im as text) & fs & (i as text) & ¬
                                fs & irot & fs & iopa & fs & idesc & rs
                        end repeat
                        repeat with i from 1 to {"(count of shapes)" if "shape" in want else "0"}
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
                                set srot to ""
                                set sfill to ""
                                set srefl to ""
                                set slock to ""
                                try
                                    set srot to rotation of sh as text
                                end try
                                try
                                    set sfill to background fill type of sh as text
                                end try
                                try
                                    set srefl to reflection showing of sh as text
                                end try
                                try
                                    set slock to locked of sh as text
                                end try
                                set out to out & "S" & fs & shTxt & fs & (item 1 of p as text) & ¬
                                    fs & (item 2 of p as text) & fs & (width of sh as text) & ¬
                                    fs & (height of sh as text) & fs & (opacity of sh as text) & ¬
                                    fs & (i as text) & fs & srot & fs & sfill & fs & srefl & ¬
                                    fs & slock & rs
                            end if
                        end repeat
                        repeat with i from 1 to {"(count of tables)" if "table" in want else "0"}
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
                                fs & rowsOut & fs & (i as text) & rs
                        end repeat
                        repeat with i from 1 to {"(count of charts)" if "chart" in want else "0"}
                            set ch to chart i
                            set p to position of ch
                            set out to out & "C" & fs & (item 1 of p as text) & ¬
                                fs & (item 2 of p as text) & fs & (width of ch as text) & ¬
                                fs & (height of ch as text) & fs & (i as text) & rs
                        end repeat
                        repeat with i from 1 to {"(count of lines)" if "line" in want else "0"}
                            set ln to line i
                            set sp to start point of ln
                            set ep to end point of ln
                            set lrot to ""
                            try
                                set lrot to rotation of ln as text
                            end try
                            set out to out & "G" & fs & (item 1 of sp as text) & ¬
                                fs & (item 2 of sp as text) & fs & (item 1 of ep as text) & ¬
                                fs & (item 2 of ep as text) & fs & (i as text) & fs & lrot & rs
                        end repeat
                        -- Groups cannot be CREATED by AppleScript (make new
                        -- group is a silent no-op), but a group the user made
                        -- by hand IS countable, so report it rather than
                        -- silently flattening.
                        set out to out & "GRP" & fs & (count of groups as text) & rs
                    end tell
                  end repeat
                    return out
                end tell
            end run
            """,
            doc_name,
            timeout=_SLIDE_SESSION_TIMEOUT,
        )
        slides: list[dict[str, Any]] = []
        slide: dict[str, Any] = {"elements": []}
        for record in raw.split(_RS):
            if not record:
                continue
            fields = record.split(_FS)
            kind = fields[0]
            if kind == "D":
                # Slide delimiter: one batched session returns every requested
                # slide, in order.
                slide = {"slide": int(fields[1]), "elements": []}
                slides.append(slide)
            elif kind == "L":
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
                    "element_class": "text item",
                    "index": int(fields[9]),
                    "text": fields[1],
                    "x": float(fields[2]),
                    "y": float(fields[3]),
                    "width": float(fields[4]),
                    "height": float(fields[5]),
                }
                if fields[6]:
                    el.update(split_font_name(fields[6]))
                if fields[7]:
                    el["font_size"] = float(fields[7])
                if fields[8]:
                    _set_color(el, fields[8])
                if len(fields) > 10 and fields[10]:
                    # A theme placeholder, emitted as an ordinary indexed
                    # element so this listing and get_slide_content agree on
                    # what "text item i" addresses. slide.title / slide.body
                    # carry the same text for round-trip rebuild.
                    el["placeholder"] = fields[10]
                _set_optional(el, "rotation", fields, 11, float)
                _set_optional(el, "opacity", fields, 12, float)
                _set_optional(el, "fill_type", fields, 13, str)
                if len(fields) > 14 and fields[14]:
                    runs = _parse_runs(fields[14])
                    # Only worth reporting when the box is NOT uniform - a
                    # single run says nothing the top-level font/size/color
                    # does not already say.
                    if len(runs) > 1:
                        el["runs"] = runs
                slide["elements"].append(el)
            elif kind == "I":
                slide["elements"].append(
                    {
                        "type": "image",
                        "element_class": "image",
                        "index": int(fields[6]),
                        "path": fields[1],
                        "x": float(fields[2]),
                        "y": float(fields[3]),
                        "width": float(fields[4]),
                        "height": float(fields[5]),
                    }
                )
                _set_optional(slide["elements"][-1], "rotation", fields, 7, float)
                _set_optional(slide["elements"][-1], "opacity", fields, 8, float)
                _set_optional(slide["elements"][-1], "description", fields, 9, str)
                # A panel or styled stroke this server rendered carries its
                # parameters in its filename, so report it as what it IS rather
                # than as an anonymous image. build_deck re-renders from these,
                # which is also what makes the round trip work at all - the
                # original PNG lived in a temp directory that is long gone.
                decoded = decode_rendered_asset(os.path.basename(fields[1]))
                if decoded:
                    el_img = slide["elements"][-1]
                    offsets = decoded.pop("_endpoint_offsets", None)
                    el_img.update(decoded)
                    el_img.pop("path", None)
                    if offsets and len(offsets) == 4:
                        # The rendered box is padded by half a stroke width plus
                        # the arrowhead, so the image's x/y is NOT the line's
                        # start point. Recover the real endpoints from the box.
                        ox_, oy_ = el_img["x"], el_img["y"]
                        el_img["x1"] = ox_ + offsets[0]
                        el_img["y1"] = oy_ + offsets[1]
                        el_img["x2"] = ox_ + offsets[2]
                        el_img["y2"] = oy_ + offsets[3]
                        for key in ("x", "y", "width", "height"):
                            el_img.pop(key, None)
            elif kind == "S":
                el = {
                    "type": "shape",
                    "element_class": "shape",
                    "index": int(fields[7]),
                    "x": float(fields[2]),
                    "y": float(fields[3]),
                    "width": float(fields[4]),
                    "height": float(fields[5]),
                    "opacity": float(fields[6]),
                }
                if fields[1]:
                    el["text"] = fields[1]
                _set_optional(el, "rotation", fields, 8, float)
                # Keynote reports the KIND of fill but never its colour, so a
                # caller can tell "no fill" from "fill not reported".
                _set_optional(el, "fill_type", fields, 9, str)
                _set_optional(el, "reflection_showing", fields, 10, _as_bool)
                _set_optional(el, "locked", fields, 11, _as_bool)
                slide["elements"].append(el)
            elif kind == "B":
                data = (
                    [[_parse_cell(c) for c in row.split("\t")] for row in fields[7].split("\n")]
                    if fields[7]
                    else []
                )
                slide["elements"].append(
                    {
                        "type": "table",
                        "element_class": "table",
                        "index": int(fields[8]),
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
                        "element_class": "chart",
                        "index": int(fields[5]),
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
                        "element_class": "line",
                        "index": int(fields[5]),
                        "x1": float(fields[1]),
                        "y1": float(fields[2]),
                        "x2": float(fields[3]),
                        "y2": float(fields[4]),
                    }
                )
                _set_optional(slide["elements"][-1], "rotation", fields, 6, float)
            elif kind == "GRP":
                count = int(fields[1])
                if count:
                    slide["groups"] = {
                        "count": count,
                        "note": (
                            "This slide contains groups the user made by hand. "
                            "AppleScript cannot report which elements belong to "
                            "which group, and cannot create groups at all, so "
                            "the elements above are listed flat."
                        ),
                    }
        return slides
