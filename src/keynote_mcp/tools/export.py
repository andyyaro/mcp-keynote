"""Export and screenshot tools."""

import glob
import logging
import os
import shutil
import tempfile

from mcp.types import TextContent, Tool

from ..utils import (
    AppleScriptRunner,
    ParameterError,
    validate_file_path,
    validate_slide_number,
)

logger = logging.getLogger(__name__)

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
# Movie export renders slides in near-real time; give it far more headroom.
_MOVIE_EXPORT_TIMEOUT = 600.0

# Trusted literal maps - only these values reach AppleScript source.
_PDF_LAYOUTS = {
    "slides": "IndividualSlides",
    "slides_with_notes": "SlideWithNotes",
    "handouts": "Handouts",
}
_PDF_QUALITY = {"good": "Good", "better": "Better", "best": "Best"}
_MOVIE_FORMATS = {
    "360p": "format360p",
    "540p": "format540p",
    "720p": "format720p",
    "1080p": "format1080p",
    "2160p": "format2160p",
    "native": "native size",
}
_IMAGE_FORMATS = {"png": "PNG", "jpeg": "JPEG", "tiff": "TIFF"}
_EXPORT_FORMATS = {
    "pptx": "Microsoft PowerPoint",
    "movie": "QuickTime movie",
    "html": "HTML",
    "images": "slide images",
    "key09": "Keynote 09",
}

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
                description=(
                    "Export the presentation as PDF. Optional layout "
                    "('slides' default, 'slides_with_notes' for presenter-notes "
                    "pages, 'handouts'), image quality, and skipped-slide "
                    "inclusion."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": "string",
                            "description": "Output file path",
                        },
                        "layout": {
                            "type": "string",
                            "enum": ["slides", "slides_with_notes", "handouts"],
                            "description": "Page layout (default slides)",
                        },
                        "image_quality": {
                            "type": "string",
                            "enum": ["good", "better", "best"],
                            "description": "PDF image quality (default best)",
                        },
                        "include_skipped": {
                            "type": "boolean",
                            "description": "Include skipped slides (default false)",
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["output_path"],
                },
            ),
            Tool(
                name="export_presentation",
                description=(
                    "Export the whole presentation to another format: 'pptx' "
                    "(Microsoft PowerPoint), 'movie' (QuickTime .m4v - slow, "
                    "renders in near-real time), 'html' (player bundle folder), "
                    "'images' (one PNG/JPEG/TIFF per slide into a folder), or "
                    "'key09' (legacy Keynote). For PDF use export_pdf."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["pptx", "movie", "html", "images", "key09"],
                            "description": "Target format",
                        },
                        "output_path": {
                            "type": "string",
                            "description": (
                                "Output file path (pptx/movie/key09) or folder path (html/images)"
                            ),
                        },
                        "movie_format": {
                            "type": "string",
                            "enum": ["360p", "540p", "720p", "1080p", "2160p", "native"],
                            "description": "Movie resolution (default 1080p; movie only)",
                        },
                        "image_format": {
                            "type": "string",
                            "enum": ["png", "jpeg", "tiff"],
                            "description": "Per-slide image format (default png; images only)",
                        },
                        "include_skipped": {
                            "type": "boolean",
                            "description": (
                                "Include skipped slides (default false). Keynote IGNORES "
                                "this for the images format - skipped slides are always "
                                "omitted there; it works on export_pdf."
                            ),
                        },
                        "doc_name": _DOC_ARG,
                    },
                    "required": ["format", "output_path"],
                },
            ),
        ]

    def _read_skipped_states(self, doc_name: str) -> str:
        """Every slide's `skipped` flag as a compact "1,0,1" string."""
        raw = self.runner.run(
            f"""
            on run argv
                set docName to item 1 of argv
                tell application "Keynote"
                    {_RESOLVE_DOC}
                    set out to ""
                    repeat with s in slides of targetDoc
                        if skipped of s then
                            set out to out & "1,"
                        else
                            set out to out & "0,"
                        end if
                    end repeat
                    return out
                end tell
            end run
            """,
            doc_name,
        )
        return raw.strip().rstrip(",")

    def _restore_skipped_states(self, doc_name: str, flags: str) -> None:
        """Put the `skipped` flags back. Best-effort: never masks the real error."""
        if not flags:
            return
        try:
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set flagText to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        set AppleScript's text item delimiters to ","
                        set parts to text items of flagText
                        set AppleScript's text item delimiters to ""
                        set n to count of slides of targetDoc
                        repeat with i from 1 to (count of parts)
                            if i is less than or equal to n then
                                set skipped of slide i of targetDoc to ((item i of parts) is "1")
                            end if
                        end repeat
                    end tell
                end run
                """,
                doc_name,
                flags,
            )
        except Exception:
            logger.warning(
                "Could not restore slides' skipped state after a screenshot export. "
                "If the deck now plays or exports as empty, unskip its slides in "
                "Keynote (Slide > Skip Slide) or with set_slide_skipped.",
                exc_info=True,
            )

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
            #
            # The read and the restore are SEPARATE osascript calls on purpose.
            # Doing all three in one script means an export that outlives the
            # timeout (or a modal dialog) kills the script before the restore
            # line, leaving the user's document with EVERY slide skipped -
            # after which exports produce nothing and playback shows nothing,
            # with no hint why. Holding the states in Python lets the restore
            # run in a `finally`, whatever happened to the export.
            saved_states = self._read_skipped_states(doc_name)
            try:
                self.runner.run(
                    f"""
                    on run argv
                        set docName to item 1 of argv
                        set outputFolder to item 2 of argv
                        tell application "Keynote"
                            {_RESOLVE_DOC}
                            tell targetDoc
                                set skipped of every slide to true
                                set skipped of slide {slide_number} to false
                            end tell
                            try
                                export targetDoc as slide images to (POSIX file outputFolder) ¬
                                    with properties {{image format:{export_format}, ¬
                                    skipped slides:false}}
                            end try
                        end tell
                    end run
                    """,
                    doc_name,
                    temp_folder,
                    timeout=_EXPORT_TIMEOUT,
                )
            finally:
                self._restore_skipped_states(doc_name, saved_states)

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

    async def export_pdf(
        self,
        output_path: str,
        layout: str = "slides",
        image_quality: str = "best",
        include_skipped: bool = False,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Export presentation as PDF with the probed export options."""
        try:
            output_path = validate_file_path(output_path)
            if layout not in _PDF_LAYOUTS:
                raise ParameterError(
                    f"Invalid layout {layout!r}. Must be one of {sorted(_PDF_LAYOUTS)}."
                )
            if image_quality not in _PDF_QUALITY:
                raise ParameterError(
                    f"Invalid image_quality {image_quality!r}. "
                    f"Must be one of {sorted(_PDF_QUALITY)}."
                )
            skipped_flag = "true" if include_skipped else "false"
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set outputPath to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        export targetDoc to (POSIX file outputPath) as PDF ¬
                            with properties {{export style:{_PDF_LAYOUTS[layout]}, ¬
                            PDF image quality:{_PDF_QUALITY[image_quality]}, ¬
                            skipped slides:{skipped_flag}}}
                    end tell
                end run
                """,
                doc_name,
                output_path,
                timeout=_EXPORT_TIMEOUT,
            )
            note = "" if layout == "slides" else f" ({layout} layout)"
            return [TextContent(type="text", text=f"Exported PDF to: {output_path}{note}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to export PDF: {e}")]

    async def export_presentation(
        self,
        format: str,
        output_path: str,
        movie_format: str = "1080p",
        image_format: str = "png",
        include_skipped: bool = False,
        doc_name: str = "",
    ) -> list[TextContent]:
        """Export to PPTX / movie / HTML / per-slide images / Keynote 09."""
        try:
            output_path = validate_file_path(output_path)
            if format not in _EXPORT_FORMATS:
                raise ParameterError(
                    f"Invalid format {format!r}. Must be one of {sorted(_EXPORT_FORMATS)}."
                )
            if movie_format not in _MOVIE_FORMATS:
                raise ParameterError(
                    f"Invalid movie_format {movie_format!r}. "
                    f"Must be one of {sorted(_MOVIE_FORMATS)}."
                )
            if image_format not in _IMAGE_FORMATS:
                raise ParameterError(
                    f"Invalid image_format {image_format!r}. "
                    f"Must be one of {sorted(_IMAGE_FORMATS)}."
                )
            output_path = os.path.abspath(os.path.expanduser(output_path))
            expected_ext = {"pptx": ".pptx", "movie": ".m4v", "key09": ".key"}.get(format)
            if expected_ext and not output_path.lower().endswith(expected_ext):
                output_path += expected_ext
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            skipped_flag = "true" if include_skipped else "false"
            props = ""
            timeout = _EXPORT_TIMEOUT
            if format == "movie":
                props = f" with properties {{movie format:{_MOVIE_FORMATS[movie_format]}}}"
                timeout = _MOVIE_EXPORT_TIMEOUT
            elif format == "images":
                props = (
                    f" with properties {{image format:{_IMAGE_FORMATS[image_format]}, "
                    f"skipped slides:{skipped_flag}}}"
                )
            self.runner.run(
                f"""
                on run argv
                    set docName to item 1 of argv
                    set outputPath to item 2 of argv
                    tell application "Keynote"
                        {_RESOLVE_DOC}
                        export targetDoc to (POSIX file outputPath) ¬
                            as {_EXPORT_FORMATS[format]}{props}
                    end tell
                end run
                """,
                doc_name,
                output_path,
                timeout=timeout,
            )
            exists = os.path.exists(output_path)
            detail = {
                "movie": f" ({movie_format})",
                "images": f" ({image_format} per slide)",
            }.get(format, "")
            status = "" if exists else " WARNING: output not found on disk afterwards."
            if include_skipped and format == "images":
                # Probed live: `skipped slides:true` changes nothing for the
                # slide-images export (identical file counts either way),
                # while it works for PDF. Say so rather than imply otherwise.
                status += (
                    " NOTE: Keynote ignores include_skipped for image exports - "
                    "skipped slides are omitted regardless. Use export_pdf "
                    "(include_skipped=true) if you need them, or unskip first."
                )
            return [
                TextContent(
                    type="text",
                    text=f"Exported {format}{detail} to: {output_path}.{status}",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Failed to export presentation: {e}")]
