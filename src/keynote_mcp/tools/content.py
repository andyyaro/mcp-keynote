"""Content management tools."""

import logging
import os

from mcp.types import TextContent, Tool

from ..utils import (
    ELEMENT_TYPE_MAP,
    AppleScriptRunner,
    ParameterError,
    parse_color,
    validate_coordinates,
    validate_dimensions,
    validate_element_type,
    validate_file_path,
    validate_index,
    validate_number,
    validate_slide_number,
)
from .base import DocumentTargetedTools
from .fragments import (
    TEXT_ITEM_FILTER,
    Argv,
    exists_guard,
    image_fragment,
    run_single_fragment,
    shape_fragment,
    text_item_fragment,
)

logger = logging.getLogger(__name__)

_DOC_ARG = {
    "type": "string",
    "description": "Document name. Optional: defaults to the session document set by the last create_presentation/open_presentation, or to the only open presentation. With several open and no session default, the call fails and names them rather than guessing.",
}

# docName always arrives CONCRETE: every public tool method resolves it in
# Python via DocumentTargetedTools._doc first, so there is deliberately no
# `front document` branch here. That branch was the field report's issue #1 -
# a call omitting doc_name silently targeted whichever deck was frontmost.
_RESOLVE_DOC = """
        set targetDoc to document docName"""

# UI-scripting timeouts: build tools click through the Animate inspector with
# deliberate delays, so they need more headroom than plain AppleScript.
_UI_SCRIPT_TIMEOUT = 60.0


# One consistent routing signal on every element-creating primitive: with 59
# tools on the surface, a model asked for a 15-slide deck will otherwise chain
# ~5 of these per slide. They stay for editing; build_deck authors.
_EDIT_TAG = (
    " Edits an existing deck one element at a time; to author a deck (or add "
    "several slides at once) use build_deck, which builds all of them in one call."
)


class ContentTools(DocumentTargetedTools):
    """Content management tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all content management tools"""
        return [
            Tool(
                name="add_text_box",
                description=(
                    "Add a text box to a slide. Returns the item's index and its final "
                    "position/size after Keynote's auto-fit settles; x/y land exactly as "
                    "given." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "text": {"type": "string", "description": "Text content"},
                        "x": {
                            "type": "number",
                            "description": (
                                "X coordinate in points (optional). Origin (0,0) is top-left."
                            ),
                        },
                        "y": {
                            "type": "number",
                            "description": (
                                "Y coordinate in points (optional). Origin (0,0) is top-left."
                            ),
                        },
                        "font_size": {"type": "number", "description": "Font size (optional)"},
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "color": {
                            "type": "string",
                            "description": (
                                "Text color as 'r,g,b' with values 0-65535 (optional, "
                                "e.g. '65535,65535,65535' for white)"
                            ),
                        },
                        "width": {
                            "type": "number",
                            "description": (
                                "Text box width in points (optional). Omit to auto-fit "
                                "the text; a fixed width makes long text wrap inside it."
                            ),
                        },
                        "height": {
                            "type": "number",
                            "description": "Text box height in points (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "text"],
                },
            ),
            Tool(
                name="add_title",
                description=(
                    "Add a title text box to a slide (default 36pt). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "title": {"type": "string", "description": "Title text"},
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 36)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "color": {
                            "type": "string",
                            "description": "Text color as 'r,g,b' with values 0-65535 (optional)",
                        },
                        "centered": {
                            "type": "boolean",
                            "description": (
                                "Horizontally center the text on the slide, computed "
                                "server-side from the final auto-fit box width, which "
                                "hugs the rendered text (optional; overrides x)"
                            ),
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "title"],
                },
            ),
            Tool(
                name="add_subtitle",
                description=(
                    "Add a subtitle text box to a slide (default 24pt). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "subtitle": {"type": "string", "description": "Subtitle text"},
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 24)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "color": {
                            "type": "string",
                            "description": "Text color as 'r,g,b' with values 0-65535 (optional)",
                        },
                        "centered": {
                            "type": "boolean",
                            "description": (
                                "Horizontally center the text on the slide, computed "
                                "server-side from the final auto-fit box width, which "
                                "hugs the rendered text (optional; overrides x)"
                            ),
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "subtitle"],
                },
            ),
            Tool(
                name="add_bullet_list",
                description=(
                    "Add a bullet list to a slide (default 18pt). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List items",
                        },
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 18)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "items"],
                },
            ),
            Tool(
                name="add_numbered_list",
                description=(
                    "Add a numbered list to a slide (default 18pt). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List items",
                        },
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 18)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "items"],
                },
            ),
            Tool(
                name="add_code_block",
                description=(
                    "Add a monospaced code block to a slide (default 14pt Monaco). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "code": {"type": "string", "description": "Code content"},
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 14)",
                        },
                        "font_name": {
                            "type": "string",
                            "description": "Font name (optional, default Monaco)",
                        },
                        "color": {
                            "type": "string",
                            "description": "Text color as 'r,g,b' with values 0-65535 (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "code"],
                },
            ),
            Tool(
                name="add_quote",
                description=(
                    "Add a quote text box to a slide (default 20pt, wrapped in quotes). Returns the item's index and final position/size; x/y land exactly as given."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "quote": {"type": "string", "description": "Quote text"},
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "font_size": {
                            "type": "number",
                            "description": "Font size (optional, default 20)",
                        },
                        "font_name": {"type": "string", "description": "Font name (optional)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "quote"],
                },
            ),
            Tool(
                name="set_slide_content",
                description=(
                    "Set the slide's theme title and/or body placeholders. Uses the "
                    "theme's own fonts and colors, so styling stays consistent - prefer "
                    "this over manual text boxes on themed layouts. Works on Blank "
                    "slides too (new presentations default to Blank): the placeholder "
                    "is enabled (title/body showing) before its text is set." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "title": {
                            "type": "string",
                            "description": "Text for the theme title placeholder (optional)",
                        },
                        "body": {
                            "type": "string",
                            "description": "Text for the theme body placeholder (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="add_image",
                description=(
                    "Add an image from a local file to a slide. Returns the image's index and final position/size."
                    + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "image_path": {
                            "type": "string",
                            "description": "Path to the image file",
                        },
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "width": {
                            "type": "number",
                            "description": "Displayed width in points (optional; keeps native size if omitted)",
                        },
                        "height": {
                            "type": "number",
                            "description": "Displayed height in points (optional)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Accessibility alt text read by VoiceOver (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "image_path"],
                },
            ),
            Tool(
                name="get_slide_content",
                description=(
                    "Get all elements on a slide - returns counts and details (index, text, "
                    "position, size) for text items, images, shapes, and tables. Use the "
                    "indices with edit_text_item / delete_element / move_element / "
                    "resize_element."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="edit_text_item",
                description="Edit a text item's content by index on a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "item_index": {
                            "type": "integer",
                            "description": "Text item index (1-based)",
                        },
                        "new_text": {"type": "string", "description": "New text content"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "item_index", "new_text"],
                },
            ),
            Tool(
                name="delete_element",
                description="Delete an element by type and index from a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape", "table"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "element_type", "element_index"],
                },
            ),
            Tool(
                name="move_element",
                description="Move an element to new coordinates on a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape", "table"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "x": {"type": "number", "description": "New X coordinate in points"},
                        "y": {"type": "number", "description": "New Y coordinate in points"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "element_type", "element_index", "x", "y"],
                },
            ),
            Tool(
                name="resize_element",
                description="Resize an element on a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape", "table"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "width": {"type": "number", "description": "New width in points"},
                        "height": {"type": "number", "description": "New height in points"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": [
                        "slide_number",
                        "element_type",
                        "element_index",
                        "width",
                        "height",
                    ],
                },
            ),
            Tool(
                name="get_speaker_notes",
                description="Get presenter notes from a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="set_speaker_notes",
                description="Set presenter notes on a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "notes": {"type": "string", "description": "Notes text"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "notes"],
                },
            ),
            Tool(
                name="clear_slide",
                description=(
                    "Clear all user-created content from a slide, preserving background "
                    "images and theme placeholders"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="set_element_opacity",
                description="Set opacity (0-100) on any element",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape", "table"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "opacity": {"type": "number", "description": "Opacity value (0-100)"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "element_type", "element_index", "opacity"],
                },
            ),
            Tool(
                name="add_build_in",
                description=(
                    "Add a Build In animation to an element so it appears step-by-step "
                    "(e.g. bullets one by one on click). Uses UI scripting - requires "
                    "Accessibility permission. Do not add builds to container shapes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                        "effect": {
                            "type": "string",
                            "description": (
                                "Animation effect name (default: Appear). Options: Appear, "
                                "Dissolve, Fly In, Move In, Fade and Move, etc."
                            ),
                            "default": "Appear",
                        },
                        "delivery": {
                            "type": "string",
                            "description": (
                                "How to deliver the animation. Options: All at Once, "
                                "By Paragraph, By Paragraph Group, By Highlighted Paragraph"
                            ),
                            "default": "By Paragraph",
                        },
                    },
                    "required": ["slide_number", "element_type", "element_index"],
                },
            ),
            Tool(
                name="remove_build_in",
                description="Remove Build In animation from an element. Uses UI scripting.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape"],
                        },
                        "element_index": {
                            "type": "integer",
                            "description": "Element index (1-based)",
                        },
                    },
                    "required": ["slide_number", "element_type", "element_index"],
                },
            ),
            Tool(
                name="add_builds_to_slide",
                description=(
                    "Add Build In animations to multiple elements on a slide in one call. "
                    "Applies builds in order so elements appear sequentially on click. "
                    "Auto-skips bullet dots (text items containing only a bullet). Uses UI "
                    "scripting - requires Accessibility permission."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "element_type": {
                            "type": "string",
                            "description": "Element type",
                            "enum": ["text", "image", "shape"],
                            "default": "text",
                        },
                        "element_indices": {
                            "type": "string",
                            "description": (
                                "Comma-separated element indices (1-based), e.g. '5,7,9'. "
                                "Use get_slide_content to find indices."
                            ),
                        },
                        "effect": {
                            "type": "string",
                            "description": "Animation effect (default: Appear)",
                            "default": "Appear",
                        },
                    },
                    "required": ["slide_number", "element_indices"],
                },
            ),
            Tool(
                name="add_shape",
                description=(
                    "Create a rectangle shape with optional position, size, and opacity. "
                    "Note: fill color cannot be set via AppleScript; use opacity over "
                    "themed backgrounds instead." + _EDIT_TAG
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "x": {"type": "number", "description": "X coordinate in points (optional)"},
                        "y": {"type": "number", "description": "Y coordinate in points (optional)"},
                        "width": {
                            "type": "number",
                            "description": "Width in points (optional, default 200)",
                        },
                        "height": {
                            "type": "number",
                            "description": "Height in points (optional, default 200)",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Opacity value 0-100 (optional, default 100)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number"],
                },
            ),
        ]

    # ------------------------------------------------------------------
    # Shared implementation for every "add a text element" tool.
    # ------------------------------------------------------------------

    async def _add_text_element(
        self,
        slide_number: int,
        text: str,
        x: float | None,
        y: float | None,
        font_size: float | None,
        font_name: str,
        color: str,
        doc_name: str,
        width: float | None = None,
        height: float | None = None,
        centered: bool = False,
    ) -> tuple[str, str, str]:
        """Create a text item; returns (index, "x,y", "w,h") after settling.

        The index is located by object identity, NOT via ``count of text
        items``: Keynote's count includes the slide's hidden default
        title/body placeholder objects, so the count over-reports and the new
        item is not the last entry. The identity loop returns the index that
        get_slide_content / move_element / edit_text_item actually address.

        The box stays auto-sized unless the caller passes width/height.
        Keynote's auto-fit tracks the rendered text at every font size
        (verified live at 96/150/300/500pt, long/multiline/CJK text, on
        Keynote 14.5 - the legacy ">48pt tiny-box clipping" belonged to the
        old multi-call add/resize/edit flows and does not reproduce in this
        single-call flow; Keynote itself wraps lines that would outgrow the
        slide). The natural box is load-bearing for ``centered``: its center
        coincides with the rendered text's center (measured within 0.5pt),
        whereas any pre-widened box centers the BOX while the left-aligned
        text inside lands off-center - so never pre-widen it. The text is
        re-set after the font size as cheap insurance against auto-fit
        truncation regressions.

        Position is applied AFTER all font/size mutations. Text items are
        born at the theme default font size (48pt measured) and auto-fit
        their box when the font size changes, keeping the box's vertical
        CENTER fixed - so a position set before the font size drifts by
        (h_before - h_after)/2 (horizontal auto-fit is left-anchored; x
        holds). Setting position last lands exactly. The final geometry is
        read back in the same osascript call and returned, in the same
        AppleScript coercion get_slide_content uses, so callers never need a
        follow-up read.
        """
        validate_slide_number(slide_number)
        x_pos, y_pos = validate_coordinates(x, y)
        rgb = parse_color(color)
        box_w: float | None = None
        box_h: float | None = None
        if width is not None or height is not None:
            box_w, box_h = validate_dimensions(width, height)

        argv = Argv()
        doc_slot = argv.reserve_doc()
        lines = text_item_fragment(
            argv,
            "T",
            text,
            x=x_pos if (x is not None or y is not None) else None,
            y=y_pos if (x is not None or y is not None) else None,
            font_size=font_size,
            font_name=font_name,
            color_rgb=rgb,
            width=box_w if width is not None else None,
            height=box_h if height is not None else None,
            centered=centered,
        )
        # Resolved here, not in the seven public callers: validation above
        # (coordinates, color, dimensions) must fail before an Apple event is
        # spent, or a bad color reports a document error instead of a color one.
        doc_name = self._doc(doc_name)
        argv.fill(doc_slot, doc_name)
        return run_single_fragment(self.runner, doc_name, slide_number, argv, lines)

    @staticmethod
    def _geometry_note(pos: str, size: str) -> str:
        """Human-readable final geometry: 'at (x, y), size WxH'."""
        return f"at ({pos.replace(',', ', ')}), size {size.replace(',', 'x')}"

    async def add_text_box(
        self,
        slide_number: int,
        text: str,
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        color: str = "",
        width: float | None = None,
        height: float | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add text box."""
        try:
            index, pos, size = await self._add_text_element(
                slide_number, text, x, y, font_size, font_name, color, doc_name, width, height
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added text box to slide {slide_number} (text item index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add text box: {e}")]

    async def add_title(
        self,
        slide_number: int,
        title: str,
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        color: str = "",
        centered: bool = False,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add title."""
        try:
            index, pos, size = await self._add_text_element(
                slide_number,
                title,
                x,
                y,
                font_size or 36,
                font_name,
                color,
                doc_name,
                centered=centered,
            )
            note = ", centered" if centered else ""
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added title to slide {slide_number} (text item index {index}{note}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add title: {e}")]

    async def add_subtitle(
        self,
        slide_number: int,
        subtitle: str,
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        color: str = "",
        centered: bool = False,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add subtitle."""
        try:
            index, pos, size = await self._add_text_element(
                slide_number,
                subtitle,
                x,
                y,
                font_size or 24,
                font_name,
                color,
                doc_name,
                centered=centered,
            )
            note = ", centered" if centered else ""
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added subtitle to slide {slide_number} (text item index {index}{note}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add subtitle: {e}")]

    async def add_bullet_list(
        self,
        slide_number: int,
        items: list[str],
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add bullet list."""
        try:
            text = "\n".join(f"• {item}" for item in items)
            doc_name = self._doc(doc_name)
            index, pos, size = await self._add_text_element(
                slide_number, text, x, y, font_size or 18, font_name, "", doc_name
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added bullet list to slide {slide_number} "
                        f"({len(items)} items, text item index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add bullet list: {e}")]

    async def add_numbered_list(
        self,
        slide_number: int,
        items: list[str],
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add numbered list."""
        try:
            text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))
            doc_name = self._doc(doc_name)
            index, pos, size = await self._add_text_element(
                slide_number, text, x, y, font_size or 18, font_name, "", doc_name
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added numbered list to slide {slide_number} "
                        f"({len(items)} items, text item index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add numbered list: {e}")]

    async def add_code_block(
        self,
        slide_number: int,
        code: str,
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        color: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add code block."""
        try:
            index, pos, size = await self._add_text_element(
                slide_number,
                code,
                x,
                y,
                font_size or 14,
                font_name or "Monaco",
                color,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added code block to slide {slide_number} (text item index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add code block: {e}")]

    async def add_quote(
        self,
        slide_number: int,
        quote: str,
        x: float | None = None,
        y: float | None = None,
        font_size: float | None = None,
        font_name: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add quote."""
        try:
            index, pos, size = await self._add_text_element(
                slide_number, f"“{quote}”", x, y, font_size or 20, font_name, "", doc_name
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added quote to slide {slide_number} (text item index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add quote: {e}")]

    async def set_slide_content(
        self,
        slide_number: int,
        title: str | None = None,
        body: str | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Set the theme title/body placeholder text on a slide."""
        try:
            validate_slide_number(slide_number)
            if title is None and body is None:
                return [TextContent(type="text", text="Nothing to set: provide title and/or body.")]
            set_title = (
                """
                        set title showing of targetSlide to true
                        set object text of default title item of targetSlide to theTitle"""
                if title is not None
                else "-- no title"
            )
            set_body = (
                """
                        set body showing of targetSlide to true
                        set object text of default body item of targetSlide to theBody"""
                if body is not None
                else "-- no body"
            )
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set theTitle to item 2 of argv
                    set theBody to item 3 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set targetSlide to slide {slide_number} of targetDoc
                        {set_title}
                        {set_body}
                    end tell
                end run
                """,
                doc_name,
                title or "",
                body or "",
            )
            parts = []
            if title is not None:
                parts.append("title")
            if body is not None:
                parts.append("body")
            return [
                TextContent(
                    type="text",
                    text=f"Set theme {' and '.join(parts)} on slide {slide_number}.",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set slide content: {e}")]

    async def add_image(
        self,
        slide_number: int,
        image_path: str,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        description: str = "",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add image."""
        try:
            validate_slide_number(slide_number)
            image_path = os.path.realpath(os.path.expanduser(validate_file_path(image_path)))
            if not os.path.isfile(image_path):
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to add image: file does not exist: {image_path}",
                    )
                ]
            x_pos, y_pos = validate_coordinates(x, y)
            box_w: float | None = None
            box_h: float | None = None
            if width is not None or height is not None:
                box_w, box_h = validate_dimensions(width, height)
            argv = Argv()
            doc_slot = argv.reserve_doc()
            lines = image_fragment(
                argv,
                "I",
                image_path,
                x=x_pos if (x is not None or y is not None) else None,
                y=y_pos if (x is not None or y is not None) else None,
                width=box_w if width is not None else None,
                height=box_h if height is not None else None,
                description=description,
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
                        f"Added image to slide {slide_number} (image index {index}) "
                        f"{self._geometry_note(pos, size)}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add image: {e}")]

    # --- Read / Edit / Delete tools ---

    async def get_slide_content(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Get all elements on a slide."""
        try:
            validate_slide_number(slide_number)
            doc_name = self._doc(doc_name)
            filter_block = TEXT_ITEM_FILTER
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        tell slide {slide_number} of targetDoc
                            set rawTextCount to count of text items
                            set imageCount to count of images
                            set shapeCount to count of shapes
                            set tableCount to count of tables

                            -- Placeholder filtering is defined ONCE, in
                            -- fragments.TEXT_ITEM_FILTER, so this reader and
                            -- describe_deck cannot disagree about which text
                            -- item is number i. See docs/INDEX_CONTRACT.md.
{filter_block}

                            set output to "text_items:" & (count of realIndices) & ¬
                                "|images:" & imageCount ¬
                                & "|shapes:" & shapeCount & "|tables:" & tableCount

                            repeat with n from 1 to (count of realIndices)
                                set i to (item n of realIndices) as integer
                                set role to item n of realRoles
                                set ti to text item i
                                set pos to position of ti
                                set output to output & "|||TEXT:" & i & ":::" & ¬
                                    (object text of ti) & ":::" & (item 1 of pos) & "," & ¬
                                    (item 2 of pos) & ":::" & (width of ti) & "," & ¬
                                    (height of ti) & ":::role:" & role
                            end repeat

                            repeat with i from 1 to imageCount
                                set img to image i
                                set pos to position of img
                                set output to output & "|||IMAGE:" & i & ":::" & ¬
                                    (item 1 of pos) & "," & (item 2 of pos) & ":::" & ¬
                                    (width of img) & "," & (height of img)
                            end repeat

                            repeat with i from 1 to shapeCount
                                set sh to shape i
                                set pos to position of sh
                                set output to output & "|||SHAPE:" & i & ":::" & ¬
                                    (item 1 of pos) & "," & (item 2 of pos) & ":::" & ¬
                                    (width of sh) & "," & (height of sh) & ":::opacity:" & ¬
                                    (opacity of sh)
                            end repeat

                            repeat with i from 1 to tableCount
                                set tb to table i
                                set pos to position of tb
                                set output to output & "|||TABLE:" & i & ":::" & ¬
                                    (item 1 of pos) & "," & (item 2 of pos) & ":::" & ¬
                                    (width of tb) & "," & (height of tb)
                            end repeat

                            return output
                        end tell
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get slide content: {e}")]

    async def edit_text_item(
        self, slide_number: int, item_index: int, new_text: str, doc_name: str = ""
    ) -> list[TextContent]:
        """Edit a text item's content by index."""
        try:
            validate_slide_number(slide_number)
            validate_index(item_index, "item_index")
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set newText to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {exists_guard("text item", item_index, slide_number)}
                        set object text of text item {item_index} of ¬
                            slide {slide_number} of targetDoc to newText
                    end tell
                end run
                """,
                doc_name,
                new_text,
            )
            return [
                TextContent(
                    type="text",
                    text=f"Text item {item_index} on slide {slide_number} updated.",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to edit text item: {e}")]

    async def delete_element(
        self, slide_number: int, element_type: str, element_index: int, doc_name: str = ""
    ) -> list[TextContent]:
        """Delete an element by type and index."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        -- Keynote silently ignores deleting a nonexistent
                        -- element; check explicitly so the caller hears about it
                        if not (exists {as_type} {element_index} of ¬
                                slide {slide_number} of targetDoc) then
                            error "No {as_type} {element_index} on slide {slide_number}. Invalid index." number -1719
                        end if
                        delete {as_type} {element_index} of slide {slide_number} of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=f"Deleted {element_type} {element_index} from slide {slide_number}.",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to delete element: {e}")]

    async def move_element(
        self,
        slide_number: int,
        element_type: str,
        element_index: int,
        x: float,
        y: float,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Move an element to new coordinates."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            x_pos, y_pos = validate_coordinates(x, y)
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {exists_guard(as_type, element_index, slide_number)}
                        set position of {as_type} {element_index} of ¬
                            slide {slide_number} of targetDoc to {{{x_pos}, {y_pos}}}
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Moved {element_type} {element_index} on slide {slide_number} "
                        f"to ({x_pos}, {y_pos})."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to move element: {e}")]

    async def resize_element(
        self,
        slide_number: int,
        element_type: str,
        element_index: int,
        width: float,
        height: float,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Resize an element."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            w, h = validate_dimensions(width, height)
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {exists_guard(as_type, element_index, slide_number)}
                        tell slide {slide_number} of targetDoc
                            set width of {as_type} {element_index} to {w}
                            set height of {as_type} {element_index} to {h}
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
                        f"Resized {element_type} {element_index} on slide "
                        f"{slide_number} to {w}x{h}."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to resize element: {e}")]

    async def get_speaker_notes(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Get presenter notes from a slide."""
        try:
            validate_slide_number(slide_number)
            doc_name = self._doc(doc_name)
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        return presenter notes of slide {slide_number} of targetDoc as text
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get speaker notes: {e}")]

    async def set_speaker_notes(
        self, slide_number: int, notes: str, doc_name: str = ""
    ) -> list[TextContent]:
        """Set presenter notes on a slide."""
        try:
            validate_slide_number(slide_number)
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set theNotes to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set presenter notes of slide {slide_number} of targetDoc to theNotes
                    end tell
                end run
                """,
                doc_name,
                notes,
            )
            return [TextContent(type="text", text=f"Speaker notes set on slide {slide_number}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set speaker notes: {e}")]

    async def clear_slide(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Clear user content from a slide, preserving theme placeholders."""
        try:
            validate_slide_number(slide_number)
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        tell slide {slide_number} of targetDoc
                            set defT to missing value
                            set defB to missing value
                            try
                                set defT to default title item
                            end try
                            try
                                set defB to default body item
                            end try

                            -- The sdef types default title/body items as
                            -- SHAPES (keynote-14.5.sdef: "default body item
                            -- ... type=shape"). Probing Keynote 14.5 found
                            -- them surfacing only among text items, never in
                            -- `shapes` - but describe_deck already guards the
                            -- shape loop by identity, so guarding here too
                            -- keeps the two readers honest and costs nothing.
                            -- Unguarded, this loop would delete a theme
                            -- placeholder outright on any build where they do
                            -- surface as shapes.
                            set shapeCount to count of shapes
                            repeat with i from shapeCount to 1 by -1
                                set sh to shape i
                                set keepShape to false
                                if defT is not missing value and sh is defT then
                                    set keepShape to true
                                end if
                                if defB is not missing value and sh is defB then
                                    set keepShape to true
                                end if
                                if not keepShape then delete sh
                            end repeat

                            -- Delete text items from highest to lowest, keeping
                            -- the theme's default title/body placeholder objects
                            -- (Keynote also surfaces them as phantom trailing
                            -- "text items"; deleting those entries would destroy
                            -- the placeholders)
                            set textCount to count of text items
                            repeat with i from textCount to 1 by -1
                                set ti to text item i
                                set keepIt to false
                                if defT is not missing value and ti is defT then
                                    set keepIt to true
                                end if
                                if defB is not missing value and ti is defB then
                                    set keepIt to true
                                end if
                                if not keepIt then delete ti
                            end repeat
                        end tell
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Cleared slide {slide_number}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to clear slide: {e}")]

    async def set_element_opacity(
        self,
        slide_number: int,
        element_type: str,
        element_index: int,
        opacity: float,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Set opacity on any element."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            opacity = validate_number(opacity, "opacity", minimum=0, maximum=100)
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {exists_guard(as_type, element_index, slide_number)}
                        set opacity of {as_type} {element_index} of ¬
                            slide {slide_number} of targetDoc to {int(opacity)}
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Set opacity of {element_type} {element_index} on slide "
                        f"{slide_number} to {opacity:g}."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set element opacity: {e}")]

    async def add_shape(
        self,
        slide_number: int,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        opacity: float | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Create a rectangle shape."""
        try:
            validate_slide_number(slide_number)
            x_pos, y_pos = validate_coordinates(x, y)
            w, h = validate_dimensions(
                width if width is not None else 200, height if height is not None else 200
            )
            op = validate_number(
                opacity if opacity is not None else 100, "opacity", minimum=0, maximum=100
            )
            argv = Argv()
            doc_slot = argv.reserve_doc()
            lines = shape_fragment(argv, "S", x=x_pos, y=y_pos, width=w, height=h, opacity=op)
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
                        f"Added shape to slide {slide_number} (shape index {index}) "
                        f"{self._geometry_note(pos, size)}, opacity {op:g}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add shape: {e}")]

    # --- Build animations (UI scripting) ---

    def _focus_document_for_ui(self, doc_name: str) -> None:
        """Bring ``doc_name``'s window to the front, for UI scripting.

        UI scripting drives the frontmost window, so a build tool cannot honor
        a doc_name without moving that document's window there first. Keynote's
        own ``set index of window N to 1`` does it (probed), and the front
        document really does follow. Verified afterwards rather than assumed: if
        the window will not come forward, the caller is told plainly instead of
        having builds applied to the wrong deck.
        """
        result = self.runner.run(
            """
            on run argv
                set docName to item 1 of argv
                tell application "Keynote"
                    activate
                    repeat with w in windows
                        if name of w is docName then
                            set index of w to 1
                            exit repeat
                        end if
                    end repeat
                    return name of front document
                end tell
            end run
            """,
            doc_name,
        )
        if result != doc_name:
            raise ParameterError(
                f"Build animations use UI scripting, which can only drive the "
                f"frontmost Keynote window. '{doc_name}' could not be brought "
                f"forward (the front document is '{result}'). Bring it forward "
                "in Keynote and retry, or close the other presentations."
            )

    def _select_slide_for_ui(self, slide_number: int, doc_name: str) -> None:
        """Select the slide in a separate osascript call before UI scripting.

        Absorbed workaround: without this separate call, the Animate inspector
        popover fails with error -2700 after a slide change.
        """
        self._focus_document_for_ui(doc_name)
        self.runner.run(
            f"""
            on run argv
                set docName to item 1 of argv
                tell application "Keynote"
                    activate
                    set current slide of document docName to ¬
                        slide {slide_number} of document docName
                end tell
            end run
            """,
            doc_name,
        )

    def _restore_format_pane(self) -> None:
        """Switch the inspector back to Format after a build tool ran.

        The build tools leave the Animate inspector open, and with it open
        ``make new line`` fails DETERMINISTICALLY with -10000 "AppleEvent
        handler failed" (verified live; other make-new classes still work).
        Best-effort: UI state must never fail the build call itself.
        """
        try:
            self.runner.run(
                """
                tell application "System Events"
                    tell application process "Keynote"
                        click menu item "Format" of menu 1 of menu item "Inspector" of ¬
                            menu 1 of menu bar item "View" of menu bar 1
                    end tell
                end tell
                """,
                timeout=10.0,
            )
        except Exception:
            logger.debug("Could not restore the Format inspector pane", exc_info=True)

    async def add_build_in(
        self,
        slide_number: int,
        element_type: str,
        element_index: int,
        effect: str = "Appear",
        delivery: str = "By Paragraph",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add a Build In animation to an element using UI scripting (System Events)."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self._select_slide_for_ui(slide_number, doc_name)

            # Full UI scripting flow. System Events targets window 1 of the
            # Keynote process; _select_slide_for_ui has already brought
            # doc_name's window there and verified it, so window 1 IS the
            # requested document.
            # 1. Select element  2. Open Animate inspector  3. Build In tab
            # 4. Add effect  5. Set delivery
            self.runner.run(
                f"""
                on run argv
                    set effectName to item 1 of argv
                    set deliveryName to item 2 of argv
                    set docName to item 3 of argv

                    -- Step 1: Select element (select_slide first, or the popover
                    -- will not appear - error -2700)
                    tell application "Keynote"
                        activate
                        tell document docName
                            set current slide to slide {slide_number}
                            set the selection to ¬
                                {{{as_type} {element_index} of slide {slide_number}}}
                        end tell
                    end tell
                    delay 0.5

                    -- Step 2: Open Animate inspector
                    tell application "System Events"
                        tell application process "Keynote"
                            click menu item "Animate" of menu 1 of menu item "Inspector" of ¬
                                menu 1 of menu bar item "View" of menu bar 1
                        end tell
                    end tell
                    delay 0.5

                    -- Step 3: Click Build In tab (radio button 1 = Build In)
                    tell application "System Events"
                        tell application process "Keynote"
                            set targetWin to window 1
                            click radio button 1 of radio group 1 of targetWin
                        end tell
                    end tell
                    delay 0.3

                    -- Step 4: Click "Add an Effect" or "Change" button
                    tell application "System Events"
                        tell application process "Keynote"
                            set targetWin to window 1
                            set btnName to ""
                            try
                                get button "Add an Effect" of targetWin
                                set btnName to "Add an Effect"
                            end try
                            if btnName is "" then
                                try
                                    get button "Change" of targetWin
                                    set btnName to "Change"
                                end try
                            end if
                            if btnName is "" then
                                error "Could not find Add an Effect or Change button"
                            end if
                            click button btnName of targetWin
                        end tell
                    end tell
                    -- MUST break out of tell block to let Keynote show the popover
                    delay 2

                    -- Select effect from popover
                    tell application "System Events"
                        tell application process "Keynote"
                            set targetWin to window 1
                            set po to missing value
                            try
                                set po to pop over 1 of button "Add an Effect" of targetWin
                            end try
                            if po is missing value then
                                try
                                    set po to pop over 1 of button "Change" of targetWin
                                end try
                            end if
                            if po is missing value then
                                try
                                    set po to pop over 1 of targetWin
                                end try
                            end if
                            if po is missing value then
                                error "Could not find effect popover"
                            end if
                            click button effectName of scroll area 1 of po
                        end tell
                    end tell
                    delay 0.5

                    -- Step 5: Set delivery if not "All at Once"
                    if deliveryName is not "All at Once" then
                        tell application "System Events"
                            tell application process "Keynote"
                                set targetWin to window 1
                                set deliveryPopup to pop up button 3 of ¬
                                    scroll area 1 of targetWin
                                click deliveryPopup
                                delay 0.3
                                click menu item deliveryName of menu 1 of deliveryPopup
                            end tell
                        end tell
                        delay 0.3
                    end if
                end run
                """,
                effect,
                delivery,
                doc_name,
                timeout=_UI_SCRIPT_TIMEOUT,
            )

            self._restore_format_pane()
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Added Build In '{effect}' with delivery '{delivery}' to "
                        f"{element_type} {element_index} on slide {slide_number}."
                    ),
                )
            ]
        except Exception as e:
            self._restore_format_pane()
            return [TextContent(type="text", text=f"Failed to add build in: {e}")]

    async def remove_build_in(
        self, slide_number: int, element_type: str, element_index: int, doc_name: str = ""
    ) -> list[TextContent]:
        """Remove Build In animation from an element using UI scripting."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            validate_index(element_index, "element_index")
            as_type = ELEMENT_TYPE_MAP[element_type]
            doc_name = self._doc(doc_name)
            self._select_slide_for_ui(slide_number, doc_name)

            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    -- Select element
                    tell application "Keynote"
                        activate
                        tell document docName
                            set current slide to slide {slide_number}
                            set the selection to ¬
                                {{{as_type} {element_index} of slide {slide_number}}}
                        end tell
                    end tell
                    delay 0.5

                    -- Open Animate inspector, Build In tab
                    tell application "System Events"
                        tell application process "Keynote"
                            click menu item "Animate" of menu 1 of menu item "Inspector" of ¬
                                menu 1 of menu bar item "View" of menu bar 1
                        end tell
                    end tell
                    delay 0.5

                    tell application "System Events"
                        tell application process "Keynote"
                            set targetWin to window 1
                            click radio button 1 of radio group 1 of targetWin
                            delay 0.3

                            -- "Change" button means a build exists
                            try
                                get button "Change" of targetWin
                            on error
                                return "no_build"
                            end try

                            click button "Change" of targetWin
                        end tell
                    end tell
                    -- MUST break out of tell block to let Keynote show the popover
                    delay 2

                    -- Select "None" from the popover
                    tell application "System Events"
                        tell application process "Keynote"
                            set targetWin to window 1
                            set po to missing value
                            try
                                set po to pop over 1 of targetWin
                            end try
                            if po is missing value then
                                try
                                    set po to pop over 1 of button "Change" of targetWin
                                end try
                            end if
                            if po is missing value then
                                error "Could not find effect popover for removal"
                            end if
                            click button "None" of scroll area 1 of po
                        end tell
                    end tell
                    delay 0.3
                end run
                """,
                doc_name,
                timeout=_UI_SCRIPT_TIMEOUT,
            )

            self._restore_format_pane()
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Removed Build In from {element_type} {element_index} "
                        f"on slide {slide_number}."
                    ),
                )
            ]
        except Exception as e:
            self._restore_format_pane()
            return [TextContent(type="text", text=f"Failed to remove build in: {e}")]

    async def add_builds_to_slide(
        self,
        slide_number: int,
        element_indices: str,
        element_type: str = "text",
        effect: str = "Appear",
        doc_name: str = "",
    ) -> list[TextContent]:
        """Add Build In animations to multiple elements. Skips bullet-dot-only items."""
        try:
            validate_slide_number(slide_number)
            validate_element_type(element_type)
            indices = [int(i.strip()) for i in element_indices.split(",") if i.strip()]
        except ValueError:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Invalid element_indices {element_indices!r}: expected "
                        "comma-separated integers, e.g. '5,7,9'."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add builds: {e}")]
        if not indices:
            return [TextContent(type="text", text="No element indices provided.")]
        for idx in indices:
            if idx < 1:
                return [
                    TextContent(
                        type="text",
                        text=f"Invalid element index {idx}: must be a positive integer.",
                    )
                ]

        try:
            # Resolved here rather than in a leading guard: this method has no
            # try wrapping its own validation, and an ambiguous document must
            # not escape as an exception.
            doc_name = self._doc(doc_name)
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add builds: {e}")]

        # Check which indices are bullet dots (text is just a bullet) and skip them
        as_type = ELEMENT_TYPE_MAP[element_type]
        dots_to_skip: set[int] = set()
        if element_type == "text":
            try:
                index_list = ", ".join(str(i) for i in indices)
                result = self.runner.run(
                    f"""
                    on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        tell document docName
                            set dotIndices to {{}}
                            repeat with idx in {{{index_list}}}
                                try
                                    set t to object text of {as_type} idx of ¬
                                        slide {slide_number} as text
                                    if t is "•" or t is "• " then
                                        set end of dotIndices to idx as integer
                                    end if
                                end try
                            end repeat
                            set AppleScript's text item delimiters to ","
                            set joined to dotIndices as text
                            set AppleScript's text item delimiters to ""
                            return joined
                        end tell
                    end tell
                    end run
                    """,
                    doc_name,
                )
                if result.strip():
                    dots_to_skip = {int(x) for x in result.strip().split(",") if x.strip()}
            except Exception:  # noqa: S110 - best-effort skip detection
                pass

        results = []
        for idx in indices:
            if idx in dots_to_skip:
                results.append(f"text {idx}: skipped (bullet dot)")
                continue
            response = await self.add_build_in(
                slide_number, element_type, idx, effect, "All at Once", doc_name
            )
            text = response[0].text
            if text.startswith("Failed"):
                results.append(f"{element_type} {idx}: FAILED - {text}")
            else:
                results.append(f"{element_type} {idx}: OK")

        return [
            TextContent(
                type="text",
                text=f"Builds applied to slide {slide_number}:\n" + "\n".join(results),
            )
        ]
