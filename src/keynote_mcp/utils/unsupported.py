"""Names callers invent for capabilities Keynote's AppleScript does not have.

Silently dropping one of these is how a caller concludes the server can do
something it cannot: PHASE 9 Task 0 traced the field report's "set_element_style
CAN write shape fill" to exactly that — an unknown argument accepted, ignored,
and reported as success.

There are TWO boundaries where an invented name arrives, and they used to be
told apart only by luck: a tool ARGUMENT (``server._reject_unknown_arguments``)
and a key inside ``build_deck``'s spec (``deck._unknown_keys``). The same
invention shows up at both — a model that reaches for ``fill_color`` on
``set_element_style`` writes ``fill_color`` on a spec element too — so the
explanation and the alternative live here once and both boundaries use them.
"""

from __future__ import annotations

# What the dictionary actually says about the invented name.
UNSUPPORTED_HINTS: dict[str, str] = {
    "fill": "shape/text fill color is not writable by AppleScript",
    "fill_color": "shape/text fill color is not writable by AppleScript",
    "fill_colour": "shape/text fill color is not writable by AppleScript",
    "background_color": "shape/text fill color is not writable by AppleScript",
    "background_fill": "shape/text fill color is not writable by AppleScript",
    "color_fill": "shape/text fill color is not writable by AppleScript",
    "shape_type": "only rectangles exist; there is no `shape type` term",
    "corner_radius": "shapes have no corner-radius property",
    "stroke": "lines and shapes have no stroke properties at all",
    "stroke_color": "lines and shapes have no stroke properties at all",
    "line_color": "lines and shapes have no stroke properties at all",
    "line_width": "lines and shapes have no stroke properties at all",
    "dash_pattern": "lines and shapes have no stroke properties at all",
    "arrowhead": "lines and shapes have no stroke properties at all",
    "shadow": "there is no shadow term on any iWork class",
    "border": "there is no border term on any iWork class",
    "z_order": "z-order is creation order and cannot be changed",
    "z_index": "z-order is creation order and cannot be changed",
    "group": "grouping is a silent no-op in AppleScript",
    "alignment": "text alignment exists only on table ranges",
    "text_align": "text alignment exists only on table ranges",
    "underline": "rich text exposes only font, size and colour",
    "bold": "there is no bold attribute; pass the bold face name as font_name",
    "italic": "there is no italic attribute; pass the italic face name as font_name",
    "background": "slides have no background term; it lives in the layout",
    "background_image": "slides have no background term; it lives in the layout",
    "gradient": "there is no gradient term on any iWork class",
}

# Where to send a caller whose invented name states a real design need.
UNSUPPORTED_ALTERNATIVES: dict[str, str] = {
    "fill": "add_colored_panel (rendered PNG, exact color) or set_element_opacity",
    "fill_color": "add_colored_panel (rendered PNG, exact color) or set_element_opacity",
    "fill_colour": "add_colored_panel (rendered PNG, exact color) or set_element_opacity",
    "background_color": "add_colored_panel, or add_table range styling for cell fills",
    "background_fill": "add_colored_panel (rendered PNG, exact color)",
    "color_fill": "add_colored_panel (rendered PNG, exact color)",
    "shape_type": "add_colored_panel for rectangles/rounded rectangles, or add_image",
    "corner_radius": "add_colored_panel, which takes a `radius`",
    "stroke": "styled_line, which renders the stroke to a transparent PNG",
    "stroke_color": "styled_line, which renders the stroke to a transparent PNG",
    "line_color": "styled_line, which renders the stroke to a transparent PNG",
    "line_width": "styled_line, which renders the stroke to a transparent PNG",
    "dash_pattern": "styled_line, which takes a `dash` pattern",
    "arrowhead": "styled_line, which takes `start_arrow`/`end_arrow`",
    "z_order": "build_deck, where spec order IS paint order",
    "z_index": "build_deck, where spec order IS paint order",
    "group": "build_deck, composing elements in paint order",
    "alignment": "add_title/add_subtitle `centered`, or add_table range styling",
    "text_align": "add_title/add_subtitle `centered`, or add_table range styling",
    "bold": "style_text_range with the bold PostScript face name",
    "italic": "style_text_range with the italic PostScript face name",
    "background": "a full-slide type:'panel' as the first element on the slide",
    "background_image": "a full-slide type:'image' as the first element on the slide",
}

# Argument-boundary-only entries: these ARE real build_deck spec keys on
# `styled_line`, so the spec boundary must not call them impossible.
ARGUMENT_ONLY_HINTS: dict[str, str] = {
    "stroke_width": "lines and shapes have no stroke properties at all",
    "dash": "lines and shapes have no stroke properties at all",
    "start_arrow": "lines and shapes have no stroke properties at all",
    "end_arrow": "lines and shapes have no stroke properties at all",
}

ARGUMENT_ONLY_ALTERNATIVES: dict[str, str] = {
    "stroke_width": "styled_line, which renders the stroke to a transparent PNG",
    "dash": "styled_line, which takes a `dash` pattern",
    "start_arrow": "styled_line, which takes `start_arrow`/`end_arrow`",
    "end_arrow": "styled_line, which takes `start_arrow`/`end_arrow`",
}


def explain_unsupported(name: str, *, argument_boundary: bool) -> tuple[str, str] | None:
    """``(hint, alternative)`` for an invented name, or None if it is just a typo.

    ``argument_boundary`` widens the table with names that are impossible as a
    TOOL ARGUMENT but legitimate as a ``styled_line`` spec key — ``dash`` on
    ``add_line`` is a category error, ``dash`` on a spec ``styled_line`` is the
    documented field.
    """
    hints = dict(UNSUPPORTED_HINTS)
    alternatives = dict(UNSUPPORTED_ALTERNATIVES)
    if argument_boundary:
        hints.update(ARGUMENT_ONLY_HINTS)
        alternatives.update(ARGUMENT_ONLY_ALTERNATIVES)
    hint = hints.get(name)
    if hint is None:
        return None
    return hint, alternatives.get(name, "")
