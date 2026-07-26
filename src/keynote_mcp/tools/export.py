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


class ExportTools:
    """Export and screenshot tools class"""

    def __init__(self) -> None:
        self.runner = AppleScriptRunner()

    def get_tools(self) -> list[Tool]:
        """Get all export and screenshot tools"""
        return [
            Tool(
                name="screenshot_slide",
                description="Export a single slide as an image file (PNG or JPEG)",
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
            return [
                TextContent(
                    type="text",
                    text=f"Captured screenshot of slide {slide_number} to: {output_path}",
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
