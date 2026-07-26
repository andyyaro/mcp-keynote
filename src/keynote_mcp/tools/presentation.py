"""Presentation management tools."""

import os
import re
import time

from mcp.types import TextContent, Tool

from ..utils import SESSION, AppleScriptRunner, validate_file_path, validate_number
from .base import DocumentTargetedTools

_DOC_ARG = {
    "type": "string",
    "description": "Document name. Optional: defaults to the session document set by the last create_presentation/open_presentation, or to the only open presentation. With several open and no session default, the call fails and names them rather than guessing.",
}

# open_presentation polls for the opened document to appear; the first poll
# usually succeeds within half a second.
_OPEN_POLL_DEADLINE = 15.0
_OPEN_POLL_INTERVAL = 0.5

# Finds the open document whose file matches argv item 1 (a POSIX path).
_FIND_DOC_BY_PATH = """
on run argv
    set targetPath to item 1 of argv
    tell application "Keynote"
        repeat with d in documents
            try
                set f to file of d
                if f is not missing value then
                    if POSIX path of f is targetPath then return name of d
                end if
            end try
        end repeat
        return ""
    end tell
end run
"""


def _default_save_path(title: str) -> str:
    """Resolve the default .key path for a new presentation.

    Directory: $KEYNOTE_MCP_SAVE_DIR if set, else ~/Documents. The filename is
    the title with path-hostile characters replaced, uniquified with -2, -3, …
    so an existing file is never overwritten.
    """
    base_dir = os.environ.get("KEYNOTE_MCP_SAVE_DIR", "") or os.path.expanduser("~/Documents")
    safe = re.sub(r"[/:\x00]", "-", title).strip() or "Untitled"
    candidate = os.path.join(base_dir, f"{safe}.key")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(base_dir, f"{safe}-{counter}.key")
        counter += 1
    return candidate


def _normalize_key_path(path: str) -> str:
    """Expand, absolutize, and ensure a .key extension on a save path."""
    path = os.path.abspath(os.path.expanduser(path.strip()))
    if not path.endswith(".key"):
        path += ".key"
    return path


# AppleScript fragment: resolve argv item 1 into targetDoc. Used inside a
# `tell application "Keynote"` block; docName arrives via argv, never
# interpolated into source.
# docName always arrives CONCRETE: every public tool method resolves it in
# Python via DocumentTargetedTools._doc first, so there is deliberately no
# `front document` branch here. That branch was the field report's issue #1 -
# a call omitting doc_name silently targeted whichever deck was frontmost.
_RESOLVE_DOC = """
        set targetDoc to document docName"""


class PresentationTools(DocumentTargetedTools):
    """Presentation management tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all presentation management tools"""
        return [
            Tool(
                name="create_presentation",
                description=(
                    "Create a new, EMPTY one-slide Keynote presentation and save it "
                    "immediately. If you already know what the slides should "
                    "contain, use build_deck instead - it creates the document AND "
                    "every slide in the same single call; come here only when you "
                    "want to start from a blank document. The "
                    "document is always saved: to save_path if given, otherwise to "
                    "<title>.key in ~/Documents (override the directory with the "
                    "KEYNOTE_MCP_SAVE_DIR environment variable). The response includes "
                    "the resolved path. Documents are never left unsaved - the first "
                    "save of an unsaved document opens a modal sheet that blocks all "
                    "automation. The first slide is set to the Blank layout (matching "
                    "add_slide's default) so add_* tools start from an empty canvas; "
                    "use set_slide_content or set_slide_layout to opt into theme "
                    "placeholders."
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
                                "Path to save the new .key file (optional; defaults to "
                                "<title>.key in ~/Documents or $KEYNOTE_MCP_SAVE_DIR, "
                                "uniquified if the file exists; '.key' is appended if "
                                "missing)"
                            ),
                        },
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="open_presentation",
                description=(
                    "Open an existing Keynote presentation. Uses LaunchServices (like a "
                    "double-click), so files outside Keynote's sandbox container - "
                    "~/Downloads, ~/Desktop, anywhere - open safely."
                ),
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
                description=(
                    "Save a presentation in place. For a document that has never been "
                    "saved, pass save_path - without it the call is refused, because "
                    "plain save on an unsaved document opens a modal sheet that blocks "
                    "automation and then lands in iCloud as Untitled.key."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_name": _DOC_ARG,
                        "save_path": {
                            "type": "string",
                            "description": (
                                "Where to save a never-saved document (optional; '.key' "
                                "appended if missing). Not valid for re-pathing an "
                                "already-saved document."
                            ),
                        },
                    },
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
            Tool(
                name="set_slide_size",
                description=(
                    "Resize the document's slides (in points). Standard: 1024x768; "
                    "wide: 1920x1080. Works on a live document (verified); Keynote "
                    "rescales layout content itself, so re-check element geometry "
                    "afterwards on populated decks."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "width": {"type": "integer", "description": "Slide width in points"},
                        "height": {"type": "integer", "description": "Slide height in points"},
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["width", "height"],
                },
            ),
            Tool(
                name="set_document_settings",
                description=(
                    "Set document playback/display settings: slide numbers, auto "
                    "loop, auto play on open, auto restart after idle, and the "
                    "idle timeout in seconds. Only the passed settings change."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_numbers_showing": {
                            "type": "boolean",
                            "description": "Show slide numbers (optional)",
                        },
                        "auto_loop": {
                            "type": "boolean",
                            "description": "Loop the slideshow (optional)",
                        },
                        "auto_play": {
                            "type": "boolean",
                            "description": "Play automatically when the file opens (optional)",
                        },
                        "auto_restart": {
                            "type": "boolean",
                            "description": "Restart when idle (optional)",
                        },
                        "maximum_idle_duration": {
                            "type": "integer",
                            "description": "Idle seconds before restart (optional)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                },
            ),
        ]

    async def create_presentation(
        self, title: str, theme: str = "", save_path: str = ""
    ) -> list[TextContent]:
        """Create a new presentation, always saved to a concrete path."""
        try:
            if save_path and save_path.strip():
                resolved_path = _normalize_key_path(save_path)
            else:
                resolved_path = _normalize_key_path(_default_save_path(title))
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

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
                        -- Default the first slide to Blank: themes start it on a
                        -- title layout whose unfilled placeholders the add_* tools
                        -- would overlap rather than fill. set_slide_content /
                        -- set_slide_layout opt back into theme placeholders.
                        set layoutNote to "first slide kept theme default layout"
                        try
                            if exists slide layout "Blank" of newDoc then
                                set base layout of slide 1 of newDoc to ¬
                                    slide layout "Blank" of newDoc
                                set layoutNote to "first slide: Blank layout"
                            end if
                        end try
                        save newDoc in POSIX file savePath
                        return (name of newDoc) & "|" & themeNote & "|" & layoutNote
                    end tell
                end run
                """,
                theme,
                resolved_path,
            )
            doc_name, _, rest = result.partition("|")
            theme_note, _, layout_note = rest.partition("|")
            notes = f"{theme_note}; {layout_note}" if layout_note else theme_note
            SESSION.set_default(doc_name)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Created presentation '{doc_name}' ({notes}), saved to "
                        f"{resolved_path}\nThis is now the session document: calls "
                        f"that omit doc_name will target it."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to create presentation: {e}")]

    async def open_presentation(self, file_path: str) -> list[TextContent]:
        """Open a presentation via LaunchServices, then wait for the document.

        A direct AppleScript ``open`` of a file outside Keynote's sandbox
        container wedges the AppleEvent queue; ``open -a Keynote`` gets a
        per-file sandbox extension the way a double-click does.
        """
        try:
            file_path = validate_file_path(file_path)
            file_path = os.path.realpath(os.path.expanduser(file_path))
            if not os.path.isfile(file_path):
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to open presentation: file does not exist: {file_path}",
                    )
                ]

            self.runner.open_in_keynote(file_path)

            deadline = time.monotonic() + _OPEN_POLL_DEADLINE
            while True:
                try:
                    name = self.runner.run(_FIND_DOC_BY_PATH, file_path, timeout=10.0)
                except Exception:
                    name = ""
                if name:
                    # The document a caller just opened is what the next call
                    # means. Without this the next doc_name-less call resolved
                    # to whatever was frontmost - the field report's issue #1.
                    SESSION.set_default(name)
                    return [
                        TextContent(
                            type="text",
                            text=(
                                f"Opened presentation: {name}\n"
                                f"This is now the session document: calls that omit "
                                f"doc_name will target it."
                            ),
                        )
                    ]
                if time.monotonic() >= deadline:
                    break
                time.sleep(_OPEN_POLL_INTERVAL)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Failed to open presentation: Keynote did not report a document "
                        f"for {file_path} within {_OPEN_POLL_DEADLINE:.0f}s. The file may "
                        "not be a Keynote document, or Keynote may be showing a dialog "
                        "(e.g. a version-conversion or missing-font alert)."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to open presentation: {e}")]

    async def save_presentation(self, doc_name: str = "", save_path: str = "") -> list[TextContent]:
        """Save a presentation, guarding the unsaved-document modal-sheet trap."""
        try:
            if save_path and save_path.strip():
                save_path = _normalize_key_path(save_path)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
            else:
                save_path = ""
            doc_name = self._doc(doc_name)
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set savePath to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set docFile to file of targetDoc
                        if docFile is missing value and savePath is "" then
                            return "UNSAVED_NO_PATH|" & (name of targetDoc)
                        end if
                        if docFile is not missing value and savePath is not "" then
                            return "ALREADY_SAVED|" & (POSIX path of docFile)
                        end if
                        if docFile is missing value then
                            save targetDoc in POSIX file savePath
                        else
                            save targetDoc
                        end if
                        -- Two-step read: 'POSIX path of (file of targetDoc)'
                        -- inline fails to coerce (-1700); capture first.
                        set savedFile to file of targetDoc
                        set savedPath to ""
                        if savedFile is not missing value then
                            set savedPath to POSIX path of savedFile
                        end if
                        return "SAVED|" & (name of targetDoc) & "|" & savedPath
                    end tell
                end run
                """,
                doc_name,
                save_path,
            )
            if result.startswith("UNSAVED_NO_PATH|"):
                name = result.partition("|")[2]
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Failed to save presentation: document '{name}' has never "
                            "been saved. Plain save would open a modal save sheet that "
                            "blocks all automation (and Keynote would then save it to "
                            "iCloud as Untitled.key). Call save_presentation again with "
                            "save_path to give it a location."
                        ),
                    )
                ]
            if result.startswith("ALREADY_SAVED|"):
                current = result.partition("|")[2]
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Failed to save presentation: document is already saved at "
                            f"{current}. Saving to a different path via AppleScript is "
                            "not supported (Keynote's save-as hangs on paths outside its "
                            "sandbox container) - call save_presentation without "
                            "save_path to save in place."
                        ),
                    )
                ]
            _, name, path = result.split("|", 2)
            path = path or save_path
            suffix = f" ({path})" if path else ""
            return [TextContent(type="text", text=f"Saved presentation: {name}{suffix}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to save presentation: {e}")]

    async def close_presentation(
        self, doc_name: str = "", should_save: bool = True
    ) -> list[TextContent]:
        """Close a presentation."""
        try:
            save_flag = "true" if should_save else "false"
            doc_name = self._doc(doc_name)
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
            SESSION.clear_default(result or doc_name)
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
            doc_name = self._doc(doc_name)
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
            doc_name = self._doc(doc_name)
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
            doc_name = self._doc(doc_name)
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

    async def set_slide_size(
        self, width: int, height: int, doc_name: str = ""
    ) -> list[TextContent]:
        """Resize the document's slides (probed live: rw on a live document)."""
        try:
            w = int(validate_number(width, "width", minimum=200, maximum=10000))
            h = int(validate_number(height, "height", minimum=200, maximum=10000))
            doc_name = self._doc(doc_name)
            result = self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set width of targetDoc to {w}
                        set height of targetDoc to {h}
                        return ((width of targetDoc) as text) & "x" & ¬
                            ((height of targetDoc) as text)
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Slide size is now {result} pt. Keynote rescaled layout "
                        "content; re-check element geometry with get_slide_content "
                        "if the deck was already populated."
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set slide size: {e}")]

    async def set_document_settings(
        self,
        slide_numbers_showing: bool | None = None,
        auto_loop: bool | None = None,
        auto_play: bool | None = None,
        auto_restart: bool | None = None,
        maximum_idle_duration: int | None = None,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Set document playback/display settings (all probed rw)."""
        try:
            ops = []
            changes = []
            for prop, value in (
                ("slide numbers showing", slide_numbers_showing),
                ("auto loop", auto_loop),
                ("auto play", auto_play),
                ("auto restart", auto_restart),
            ):
                if value is not None:
                    flag = "true" if value else "false"
                    ops.append(f"set {prop} of targetDoc to {flag}")
                    changes.append(f"{prop}={flag}")
            if maximum_idle_duration is not None:
                seconds = int(
                    validate_number(
                        maximum_idle_duration, "maximum_idle_duration", minimum=1, maximum=86400
                    )
                )
                ops.append(f"set maximum idle duration of targetDoc to {seconds}")
                changes.append(f"maximum idle duration={seconds}s")
            if not ops:
                return [
                    TextContent(
                        type="text",
                        text=(
                            "Failed to set document settings: nothing to set - pass "
                            "at least one setting."
                        ),
                    )
                ]
            body = "\n".join(ops)
            doc_name = self._doc(doc_name)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        {body}
                    end tell
                end run
                """,
                doc_name,
            )
            return [
                TextContent(type="text", text=f"Document settings updated: {', '.join(changes)}")
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to set document settings: {e}")]
