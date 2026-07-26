"""Export and screenshot tools."""

import glob
import os
import shutil
import tempfile

from mcp.types import TextContent, Tool

from ..utils import AppleScriptRunner, validate_file_path, validate_slide_number

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

# Exports of large decks can outlive the default osascript timeout.
_EXPORT_TIMEOUT = 120.0

# Counts visible text boxes with empty text on one slide - exactly what
# Keynote's image export silently omits. Skips the phantom surfacings of the
# default title/body placeholder objects (see content.get_slide_content).
_COUNT_UNFILLED_SCRIPT = """
                on run argv
                    set docName to item 1 of argv
                    tell application "Keynote"
                        {resolve_doc}
                        tell slide {slide_number} of targetDoc
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
                            set emptyCount to 0
                            repeat with i from 1 to (count of text items)
                                set ti to text item i
                                set phantom to false
                                if defT is not missing value and ti is defT then
                                    if seenTitle or (not titleShown) then set phantom to true
                                    set seenTitle to true
                                else if defB is not missing value and ti is defB then
                                    if seenBody or (not bodyShown) then set phantom to true
                                    set seenBody to true
                                end if
                                if not phantom then
                                    if (object text of ti as text) is "" then
                                        set emptyCount to emptyCount + 1
                                    end if
                                end if
                            end repeat
                            return emptyCount
                        end tell
                    end tell
                end run
"""


class ExportTools:
    """Export and screenshot tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all export and screenshot tools"""
        return [
            Tool(
                name="screenshot_slide",
                description=(
                    "Export a single slide as an image file (PNG or JPEG). NOT a "
                    "faithful editor view: Keynote's export omits unfilled placeholder "
                    "text boxes, so the image can look clean while the editor still "
                    "shows empty boxes. The response reports how many were omitted."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {"type": "integer", "description": "Slide number"},
                        "output_path": {
                            "type": "string",
                            "description": "Output file path",
                        },
                        "format": {
                            "type": "string",
                            "description": "Image format (png/jpg, default: png)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["slide_number", "output_path"],
                },
            ),
            Tool(
                name="export_pdf",
                description="Export the presentation as PDF",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": "string",
                            "description": "Output file path",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["output_path"],
                },
            ),
        ]

    async def screenshot_slide(
        self, slide_number: int, output_path: str, format: str = "png", doc_name: str = ""
    ) -> list[TextContent]:
        """Export a single slide as an image."""
        temp_folder = ""
        try:
            validate_slide_number(slide_number)
            output_path = validate_file_path(output_path)

            export_format = "JPEG" if format.lower() in ("jpg", "jpeg") else "PNG"
            extension = "jpeg" if export_format == "JPEG" else "png"
            output_dir = os.path.dirname(os.path.abspath(output_path))
            temp_folder = tempfile.mkdtemp(prefix="keynote_mcp_export_", dir=output_dir)

            # Export only the target slide by skipping all others, then restore
            # each slide's original skipped state.
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set outputFolder to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        tell targetDoc
                            set savedStates to skipped of every slide
                            set skipped of every slide to true
                            set skipped of slide {slide_number} to false
                        end tell
                        try
                            export targetDoc as slide images to (POSIX file outputFolder) ¬
                                with properties {{image format:{export_format}, ¬
                                skipped slides:false}}
                        end try
                        tell targetDoc
                            repeat with i from 1 to count of savedStates
                                set skipped of slide i to item i of savedStates
                            end repeat
                        end tell
                    end tell
                end run
                """,
                doc_name,
                temp_folder,
                timeout=_EXPORT_TIMEOUT,
            )

            generated = sorted(glob.glob(os.path.join(temp_folder, f"*.{extension}")))
            if not generated:
                generated = sorted(glob.glob(os.path.join(temp_folder, "*")))
            if not generated:
                return [
                    TextContent(
                        type="text",
                        text=(
                            "Screenshot file was not generated. Keynote may need "
                            "permission to write to the export folder."
                        ),
                    )
                ]
            shutil.move(generated[0], output_path)

            # Honesty check: the export silently omits unfilled placeholder
            # boxes, so tell the caller how far the image is from the editor.
            try:
                unfilled = int(
                    self.runner.run(
                        _COUNT_UNFILLED_SCRIPT.format(
                            resolve_doc=_RESOLVE_DOC, slide_number=slide_number
                        ),
                        doc_name,
                    )
                )
            except Exception:
                unfilled = -1
            if unfilled > 0:
                note = (
                    f" WARNING: {unfilled} unfilled placeholder text box(es) on this "
                    "slide are NOT rendered in the export - the editor shows them, "
                    "the image does not."
                )
            elif unfilled == 0:
                note = " No unfilled placeholders; the export matches the editor view."
            else:
                note = " (Unfilled-placeholder check unavailable for this slide.)"
            return [
                TextContent(
                    type="text",
                    text=f"Captured screenshot of slide {slide_number} to: {output_path}.{note}",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to screenshot slide: {e}")]
        finally:
            if temp_folder:
                shutil.rmtree(temp_folder, ignore_errors=True)

    async def export_pdf(self, output_path: str, doc_name: str = "") -> list[TextContent]:
        """Export presentation as PDF."""
        try:
            output_path = validate_file_path(output_path)
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set outputPath to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        export targetDoc to (POSIX file outputPath) as PDF
                    end tell
                end run
                """,
                doc_name,
                output_path,
                timeout=_EXPORT_TIMEOUT,
            )
            return [TextContent(type="text", text=f"Exported PDF to: {output_path}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to export PDF: {e}")]
