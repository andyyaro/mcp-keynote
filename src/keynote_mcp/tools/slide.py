"""Slide management tools."""

from mcp.types import TextContent, Tool

from ..utils import AppleScriptRunner, validate_slide_number

_DOC_ARG = {
    "type": "string",
    "description": "Document name (optional, defaults to front document)",
}

_RESOLVE_DOC = """
        if docName is "" then
            set targetDoc to front document
        else
            set targetDoc to document docName
        end if"""


class SlideTools:
    """Slide management tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all slide management tools"""
        return [
            Tool(
                name="add_slide",
                description="Add a new slide to the presentation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "position": {
                            "type": "integer",
                            "description": "Insert position (optional, 0 = append at end)",
                        },
                        "layout": {
                            "type": "string",
                            "description": (
                                "Slide layout (master slide) name, e.g. 'Blank'. Optional; "
                                "defaults to Blank. See get_available_layouts."
                            ),
                        },
                    },
                },
            ),
            Tool(
                name="delete_slide",
                description="Delete a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_number": {
                            "type": "integer",
                            "description": "Slide number to delete",
                        },
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="duplicate_slide",
                description="Duplicate a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_number": {
                            "type": "integer",
                            "description": "Slide number to duplicate",
                        },
                        "new_position": {
                            "type": "integer",
                            "description": (
                                "Position for the copy (optional, 0 = right after the source)"
                            ),
                        },
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="move_slide",
                description="Move a slide to a different position",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "from_position": {
                            "type": "integer",
                            "description": "Source position",
                        },
                        "to_position": {
                            "type": "integer",
                            "description": "Target position",
                        },
                    },
                    "required": ["from_position", "to_position"],
                },
            ),
            Tool(
                name="get_slide_count",
                description="Get slide count",
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
            Tool(
                name="select_slide",
                description=(
                    "Select (navigate to) a specific slide. Required before add_build_in "
                    "when working on a different slide."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_number": {"type": "integer", "description": "Slide number"},
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="set_slide_layout",
                description="Set slide layout (base slide / master slide)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "layout": {
                            "type": "string",
                            "description": "Layout name (see get_available_layouts)",
                        },
                    },
                    "required": ["slide_number", "layout"],
                },
            ),
            Tool(
                name="get_slide_info",
                description="Get slide info (number, layout, text item count)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "slide_number": {"type": "integer", "description": "Slide number"},
                    },
                    "required": ["slide_number"],
                },
            ),
            Tool(
                name="get_available_layouts",
                description="Get list of available slide layouts (master slides)",
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
        ]

    async def add_slide(
        self, doc_name: str = "", position: int = 0, layout: str = "Blank"
    ) -> list[TextContent]:
        """Add a new slide."""
        try:
            if position != 0:
                validate_slide_number(position)
            if not layout:
                layout = "Blank"
            position_clause = (
                "set newSlide to make new slide at end of slides of targetDoc"
                if position == 0
                else f"set newSlide to make new slide at before slide {position} of targetDoc"
            )
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set layoutName to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {position_clause}
                        set layoutNote to layoutName
                        try
                            set base layout of newSlide to slide layout layoutName of targetDoc
                        on error
                            set layoutNote to "'" & layoutName & "' not found, kept default layout"
                        end try
                        return (slide number of newSlide as text) & "|" & layoutNote
                    end tell
                end run
                """,
                doc_name,
                layout,
            )
            number, _, layout_note = result.partition("|")
            return [TextContent(type="text", text=f"Added slide #{number} (layout: {layout_note})")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to add slide: {e}")]

    async def delete_slide(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Delete a slide."""
        try:
            validate_slide_number(slide_number)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        -- Keynote silently ignores deleting a nonexistent
                        -- slide; check explicitly so the caller hears about it
                        if not (exists slide {slide_number} of targetDoc) then
                            error "Slide {slide_number} does not exist. Invalid index." number -1719
                        end if
                        delete slide {slide_number} of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Deleted slide {slide_number}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to delete slide: {e}")]

    async def duplicate_slide(
        self, slide_number: int, doc_name: str = "", new_position: int = 0
    ) -> list[TextContent]:
        """Duplicate a slide."""
        try:
            validate_slide_number(slide_number)
            if new_position != 0:
                validate_slide_number(new_position)
            if new_position == 0:
                duplicate_clause = "duplicate sourceSlide to after sourceSlide"
                new_number = slide_number + 1
            elif new_position > slide_number:
                duplicate_clause = (
                    f"duplicate sourceSlide to after slide {new_position} of targetDoc"
                )
                new_number = new_position + 1
            else:
                duplicate_clause = (
                    f"duplicate sourceSlide to before slide {new_position} of targetDoc"
                )
                new_number = new_position
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set sourceSlide to slide {slide_number} of targetDoc
                        {duplicate_clause}
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Duplicated slide, new number: {new_number}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to duplicate slide: {e}")]

    async def move_slide(
        self, from_position: int, to_position: int, doc_name: str = ""
    ) -> list[TextContent]:
        """Move a slide to a different position."""
        try:
            validate_slide_number(from_position)
            validate_slide_number(to_position)

            if from_position == to_position:
                return [TextContent(type="text", text=f"Slide already at position {to_position}")]

            # Use 'before' when moving backward, 'after' when moving forward.
            # Plain 'move X to slide Y' REPLACES slide Y, destroying it.
            if to_position < from_position:
                insert_ref = f"before slide {to_position}"
            else:
                insert_ref = f"after slide {to_position}"

            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        move slide {from_position} of targetDoc to {insert_ref} of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=f"Moved slide from position {from_position} to position {to_position}",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to move slide: {e}")]

    async def get_slide_count(self, doc_name: str = "") -> list[TextContent]:
        """Get slide count."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        return count of slides of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Slide count: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get slide count: {e}")]

    async def select_slide(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Select a specific slide."""
        try:
            validate_slide_number(slide_number)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set current slide of targetDoc to slide {slide_number} of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Selected slide {slide_number}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to select slide: {e}")]

    async def set_slide_layout(
        self, slide_number: int, layout: str, doc_name: str = ""
    ) -> list[TextContent]:
        """Set slide layout."""
        try:
            validate_slide_number(slide_number)
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set layoutName to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        if not (exists slide layout layoutName of targetDoc) then
                            return "layout_not_found"
                        end if
                        set base layout of slide {slide_number} of targetDoc to ¬
                            slide layout layoutName of targetDoc
                        return "success"
                    end tell
                end run
                """,
                doc_name,
                layout,
            )
            if result == "success":
                return [
                    TextContent(type="text", text=f"Set slide {slide_number} layout to: {layout}")
                ]
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Layout not found: {layout}. "
                        "Use get_available_layouts to list valid names."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set slide layout: {e}")]

    async def get_slide_info(self, slide_number: int, doc_name: str = "") -> list[TextContent]:
        """Get slide info."""
        try:
            validate_slide_number(slide_number)
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set targetSlide to slide {slide_number} of targetDoc
                        set layoutName to "Unknown Layout"
                        try
                            set layoutName to name of base layout of targetSlide
                        end try
                        set textCount to 0
                        try
                            set textCount to count of text items of targetSlide
                        end try
                        return (slide number of targetSlide as text) & "|||" & ¬
                            layoutName & "|||" & (textCount as text)
                    end tell
                end run
                """,
                doc_name,
            )
            parts = result.split("|||")
            if len(parts) >= 3:
                number, layout, text_count = parts[0], parts[1], parts[2]
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Slide {slide_number} info:\n- Number: {number}\n"
                            f"- Layout: {layout}\n- Text item count: {text_count}"
                        ),
                    )
                ]
            return [TextContent(type="text", text=f"Slide {slide_number} info: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get slide info: {e}")]

    async def get_available_layouts(self, doc_name: str = "") -> list[TextContent]:
        """Get available layouts."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set layoutNames to name of every slide layout of targetDoc
                        set AppleScript's text item delimiters to "|||"
                        set joined to layoutNames as text
                        set AppleScript's text item delimiters to ""
                        return joined
                    end tell
                end run
                """,
                doc_name,
            )
            layouts = [layout.strip() for layout in result.split("|||") if layout.strip()]
            if layouts:
                listing = "\n".join(f"- {layout}" for layout in layouts)
                return [TextContent(type="text", text=f"Available layouts:\n{listing}")]
            return [TextContent(type="text", text="No available layouts found")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get layouts: {e}")]
