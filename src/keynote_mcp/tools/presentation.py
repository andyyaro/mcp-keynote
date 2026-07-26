"""Presentation management tools."""

from mcp.types import TextContent, Tool

from ..utils import AppleScriptRunner, validate_file_path

_DOC_ARG = {
    "type": "string",
    "description": "Document name (optional, defaults to front document)",
}

# AppleScript fragment: resolve argv item 1 into targetDoc. Used inside a
# `tell application "Keynote"` block; docName arrives via argv, never
# interpolated into source.
_RESOLVE_DOC = """
        if docName is "" then
            set targetDoc to front document
        else
            set targetDoc to document docName
        end if"""


class PresentationTools:
    """Presentation management tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all presentation management tools"""
        return [
            Tool(
                name="create_presentation",
                description=(
                    "Create a new Keynote presentation. If save_path is given the document "
                    "is saved there; otherwise it stays unsaved (name 'Untitled')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": (
                                "Presentation title; used as the filename when saving to "
                                "the default location"
                            ),
                        },
                        "theme": {
                            "type": "string",
                            "description": "Theme name (optional, see get_available_themes)",
                        },
                        "save_path": {
                            "type": "string",
                            "description": (
                                "Absolute path to save the new .key file (optional; if "
                                "omitted the document is left unsaved)"
                            ),
                        },
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="open_presentation",
                description="Open an existing Keynote presentation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the presentation file",
                        }
                    },
                    "required": ["file_path"],
                },
            ),
            Tool(
                name="save_presentation",
                description="Save a presentation",
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
            Tool(
                name="close_presentation",
                description="Close a presentation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "should_save": {
                            "type": "boolean",
                            "description": "Whether to save before closing (default: true)",
                        },
                    },
                },
            ),
            Tool(
                name="list_presentations",
                description="List all open presentations",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="set_presentation_theme",
                description="Set presentation theme",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "theme_name": {"type": "string", "description": "Theme name"},
                    },
                    "required": ["theme_name"],
                },
            ),
            Tool(
                name="get_presentation_info",
                description="Get presentation info (name, slide count, theme)",
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
            Tool(
                name="get_available_themes",
                description="Get list of available themes",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_slide_size",
                description=(
                    "Get slide size (width/height in points), aspect ratio, and layout "
                    "reference info such as safe margins and center coordinates"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"doc_name": _DOC_ARG},
                },
            ),
        ]

    async def create_presentation(
        self, title: str, theme: str = "", save_path: str = ""
    ) -> list[TextContent]:
        """Create a new presentation."""
        try:
            if not self.runner.check_keynote_running():
                self.runner.launch_keynote()

            result = self.runner.run(
                """
                on run argv
                    set themeName to item 1 of argv
                    set savePath to item 2 of argv
                    tell application "Keynote"
                        activate
                        if themeName is "" then
                            set newDoc to make new document
                            set themeNote to "default theme"
                        else
                            try
                                set newDoc to make new document with properties ¬
                                    {document theme:theme themeName}
                                set themeNote to "theme: " & themeName
                            on error
                                set newDoc to make new document
                                set themeNote to "theme '" & themeName & "' not found, used default"
                            end try
                        end if
                        if savePath is not "" then
                            save newDoc in POSIX file savePath
                        end if
                        return (name of newDoc) & "|" & themeNote
                    end tell
                end run
                """,
                theme,
                save_path,
            )
            doc_name, _, theme_note = result.partition("|")
            saved_note = f", saved to {save_path}" if save_path else ", unsaved"
            return [
                TextContent(
                    type="text",
                    text=f"Created presentation '{doc_name}' ({theme_note}{saved_note})",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to create presentation: {e}")]

    async def open_presentation(self, file_path: str) -> list[TextContent]:
        """Open a presentation."""
        try:
            file_path = validate_file_path(file_path)
            if not self.runner.check_keynote_running():
                self.runner.launch_keynote()

            result = self.runner.run(
                """
                on run argv
                    tell application "Keynote"
                        open (POSIX file (item 1 of argv))
                        return name of front document
                    end tell
                end run
                """,
                file_path,
            )
            return [TextContent(type="text", text=f"Opened presentation: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to open presentation: {e}")]

    async def save_presentation(self, doc_name: str = "") -> list[TextContent]:
        """Save a presentation."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        save targetDoc
                        return name of targetDoc
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Saved presentation: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to save presentation: {e}")]

    async def close_presentation(
        self, doc_name: str = "", should_save: bool = True
    ) -> list[TextContent]:
        """Close a presentation."""
        try:
            save_flag = "true" if should_save else "false"
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set theName to name of targetDoc
                        if {save_flag} then
                            close targetDoc saving yes
                        else
                            close targetDoc saving no
                        end if
                        return theName
                    end tell
                end run
                """,
                doc_name,
            )
            return [TextContent(type="text", text=f"Closed presentation: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to close presentation: {e}")]

    async def list_presentations(self) -> list[TextContent]:
        """List all open presentations."""
        try:
            result = self.runner.run(
                """
                tell application "Keynote"
                    set docNames to name of every document
                    set AppleScript's text item delimiters to "|||"
                    set joined to docNames as text
                    set AppleScript's text item delimiters to ""
                    return joined
                end tell
                """
            )
            if result:
                names = [n for n in result.split("|||") if n]
                listing = "\n".join(f"- {name}" for name in names)
                return [TextContent(type="text", text=f"Open presentations:\n{listing}")]
            return [TextContent(type="text", text="No open presentations")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to list presentations: {e}")]

    async def set_presentation_theme(
        self, theme_name: str, doc_name: str = ""
    ) -> list[TextContent]:
        """Set presentation theme."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set themeName to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        if not (exists theme themeName) then
                            return "theme_not_found"
                        end if
                        set document theme of targetDoc to theme themeName
                        return "success"
                    end tell
                end run
                """,
                doc_name,
                theme_name,
            )
            if result == "success":
                return [TextContent(type="text", text=f"Theme set: {theme_name}")]
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Theme not found: {theme_name}. "
                        "Use get_available_themes to list valid names."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set theme: {e}")]

    async def get_presentation_info(self, doc_name: str = "") -> list[TextContent]:
        """Get presentation info."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set themeName to "Unknown Theme"
                        try
                            set themeName to name of document theme of targetDoc
                        end try
                        return (name of targetDoc) & "|||" & ¬
                            (count of slides of targetDoc) & "|||" & themeName
                    end tell
                end run
                """,
                doc_name,
            )
            parts = result.split("|||")
            if len(parts) >= 3:
                name, slide_count, theme = parts[0], parts[1], parts[2]
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Presentation info:\n- Name: {name}\n"
                            f"- Slide count: {slide_count}\n- Theme: {theme}"
                        ),
                    )
                ]
            return [TextContent(type="text", text=f"Presentation info: {result}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get presentation info: {e}")]

    async def get_available_themes(self) -> list[TextContent]:
        """Get list of available themes."""
        try:
            result = self.runner.run(
                """
                tell application "Keynote"
                    set themeNames to name of every theme
                    set AppleScript's text item delimiters to "|||"
                    set joined to themeNames as text
                    set AppleScript's text item delimiters to ""
                    return joined
                end tell
                """
            )
            themes = [t for t in result.split("|||") if t.strip()]
            if themes:
                listing = "\n".join(f"- {t}" for t in themes)
                return [
                    TextContent(type="text", text=f"Available themes ({len(themes)}):\n{listing}")
                ]
            return [TextContent(type="text", text="No available themes found")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get theme list: {e}")]

    async def get_slide_size(self, doc_name: str = "") -> list[TextContent]:
        """Get slide size, aspect ratio, and layout reference info."""
        try:
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        return ((width of targetDoc) as text) & "," & ((height of targetDoc) as text)
                    end tell
                end run
                """,
                doc_name,
            )
            width_str, _, height_str = result.partition(",")
            width, height = float(width_str), float(height_str)
            ratio = width / height
            if 1.7 < ratio < 1.8:
                ratio_type = "16:9"
            elif 1.3 < ratio < 1.4:
                ratio_type = "4:3"
            else:
                ratio_type = "Custom"

            safe_w, safe_h = int(width * 0.9), int(height * 0.9)
            margin_x, margin_y = int((width - safe_w) / 2), int((height - safe_h) / 2)
            text = (
                f"Slide size info:\n"
                f"- Size: {width:.0f} x {height:.0f} pt\n"
                f"- Ratio: {ratio:.3f} ({ratio_type})\n"
                f"- Center: ({int(width / 2)}, {int(height / 2)})\n\n"
                f"Layout reference:\n"
                f"- Safe area: {safe_w} x {safe_h} pt\n"
                f"- Margins: {margin_x} x {margin_y} pt\n"
                f"- Suggested title area: y = {margin_y} - {margin_y + 100}\n"
                f"- Suggested content area: y = {margin_y + 120} - {safe_h + margin_y}"
            )
            return [TextContent(type="text", text=text)]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to get slide size: {e}")]
