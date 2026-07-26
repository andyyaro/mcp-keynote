"""Error handling utilities for Keynote-MCP."""

import re


class KeynoteError(Exception):
    """Base exception for Keynote operations"""


class AppleScriptError(KeynoteError):
    """AppleScript execution error"""


class FileOperationError(KeynoteError):
    """File operation error"""


class ParameterError(KeynoteError):
    """Parameter validation error"""


_ERROR_NUMBER_RE = re.compile(r"\((-\d+)\)")

# AppleScript / Apple Event error numbers worth translating into something a
# caller can act on. -1743 and "assistive access" name the exact System
# Settings pane to fix.
_AUTOMATION_FIX = (
    "Automation permission is missing (Apple Event error -1743). Open "
    "System Settings > Privacy & Security > Automation, find the app that "
    "launched this MCP server (your terminal or IDE), and enable its toggle "
    "for Keynote (and System Events for build animations). Then retry."
)
_ACCESSIBILITY_FIX = (
    "Accessibility (UI scripting) permission is missing. Open System Settings "
    "> Privacy & Security > Accessibility and enable the app that launched "
    "this MCP server (your terminal or IDE). Only build-animation tools need "
    "this permission."
)
_NOT_FOUND_FIX = (
    "AppleScript could not find the referenced object (error -1728/-1719: "
    "object not found or invalid index). The slide number, element index, or "
    "document name probably does not exist - check with get_slide_count / "
    "get_slide_content / list_presentations."
)


def handle_applescript_error(error_output: str) -> None:
    """Translate osascript stderr into a typed, actionable exception.

    Raises for any non-empty error output; returns silently for empty output.
    """
    if not error_output or not error_output.strip():
        return

    error_output = error_output.strip()
    lowered = error_output.lower()
    match = _ERROR_NUMBER_RE.search(error_output)
    code = int(match.group(1)) if match else None

    if code == -1743 or "not authorized to send apple events" in lowered:
        raise AppleScriptError(f"{_AUTOMATION_FIX}\nOriginal error: {error_output}")

    if "assistive access" in lowered or code == -25211:
        raise AppleScriptError(f"{_ACCESSIBILITY_FIX}\nOriginal error: {error_output}")

    # -1728 = object not found; -1719 = invalid index ("Can't get slide 99...").
    # Keynote 14.5 reports bad slide/element indices as -1719.
    if (
        code in (-1728, -1719)
        or "can't get" in lowered
        or "can’t get" in lowered
        or "invalid index" in lowered
    ):
        raise AppleScriptError(f"{_NOT_FOUND_FIX}\nOriginal error: {error_output}")

    if code == -600 or "isn't running" in lowered or "isn’t running" in lowered:
        raise AppleScriptError(
            f"Keynote is not running (error -600). Open Keynote and retry.\n"
            f"Original error: {error_output}"
        )

    if code == -1712 or "timed out" in lowered:
        raise AppleScriptError(
            "The Apple event timed out (error -1712). Keynote may be showing a "
            f"modal dialog - dismiss it and retry.\nOriginal error: {error_output}"
        )

    if "syntax error" in lowered:
        raise AppleScriptError(f"AppleScript syntax error: {error_output}")

    if "file" in lowered and ("not found" in lowered or "doesn't exist" in lowered):
        raise FileOperationError(f"File operation error: {error_output}")

    raise AppleScriptError(f"AppleScript error: {error_output}")


def validate_slide_number(slide_number: int | None, max_slides: int | None = None) -> int:
    """Validate slide number"""
    if slide_number is None:
        raise ParameterError("Slide number is required")

    if not isinstance(slide_number, int) or isinstance(slide_number, bool) or slide_number < 1:
        raise ParameterError(f"Invalid slide number: {slide_number}. Must be a positive integer.")

    if max_slides is not None and slide_number > max_slides:
        raise ParameterError(f"Slide number {slide_number} exceeds maximum slides {max_slides}")

    return slide_number


def validate_index(value: int, name: str = "index") -> int:
    """Validate a 1-based element index."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ParameterError(f"Invalid {name}: {value}. Must be a positive integer.")
    return value


def validate_coordinates(x: float | None, y: float | None) -> tuple[float, float]:
    """Validate coordinate values; None defaults to 0.0."""
    for name, value in (("x", x), ("y", y)):
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
        ):
            raise ParameterError(f"Invalid {name} coordinate: {value}")
    return float(x) if x is not None else 0.0, float(y) if y is not None else 0.0


def validate_number(
    value: float, name: str, minimum: float | None = None, maximum: float | None = None
) -> float:
    """Validate that a value is a real number within optional bounds."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ParameterError(f"Invalid {name}: {value!r}. Must be a number.")
    if minimum is not None and value < minimum:
        raise ParameterError(f"Invalid {name}: {value}. Must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ParameterError(f"Invalid {name}: {value}. Must be <= {maximum}.")
    return float(value)


def validate_file_path(file_path: str) -> str:
    """Validate file path"""
    if not file_path or not isinstance(file_path, str) or not file_path.strip():
        raise ParameterError("File path is required and must be a non-empty string")
    return file_path.strip()


VALID_ELEMENT_TYPES = {"text", "image", "shape", "table"}

# Maps public element type names to AppleScript class names. Values are
# trusted literals - only values from this dict may be interpolated into
# AppleScript source.
ELEMENT_TYPE_MAP = {
    "text": "text item",
    "image": "image",
    "shape": "shape",
    "table": "table",
}


def validate_element_type(element_type: str) -> str:
    """Validate element type"""
    if element_type not in VALID_ELEMENT_TYPES:
        raise ParameterError(
            f"Invalid element type: {element_type}. Must be one of: {sorted(VALID_ELEMENT_TYPES)}"
        )
    return element_type


def validate_dimensions(width: float | None, height: float | None) -> tuple[float, float]:
    """Validate width and height dimensions"""
    for name, value in (("width", width), ("height", height)):
        if value is not None and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0
        ):
            raise ParameterError(f"Invalid {name}: {value}. Must be positive.")
    return float(width) if width is not None else 0.0, float(height) if height is not None else 0.0


def parse_color(color: str) -> tuple[int, int, int] | None:
    """Parse a color string into validated 0-65535 RGB ints.

    Accepts '#RRGGBB' / '#RGB' hex or 'r,g,b' with values 0-65535. Returns
    None for an empty string. Raises ParameterError for anything else - this
    is what keeps color strings safe to interpolate into AppleScript source.
    """
    if not color:
        return None
    color = color.strip()
    if color.startswith("#"):
        hex_part = color[1:]
        if len(hex_part) == 3:
            hex_part = "".join(c * 2 for c in hex_part)
        if len(hex_part) != 6:
            raise ParameterError(f"Invalid color {color!r}. Hex form must be #RGB or #RRGGBB.")
        try:
            r8, g8, b8 = (int(hex_part[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            raise ParameterError(f"Invalid color {color!r}. Hex digits expected.") from None
        # 0-255 -> 0-65535 (0xFF -> 0xFFFF)
        return r8 * 257, g8 * 257, b8 * 257
    parts = [p.strip() for p in color.split(",")]
    if len(parts) != 3:
        raise ParameterError(
            f"Invalid color {color!r}. Expected 'r,g,b' with three components 0-65535."
        )
    try:
        r, g, b = (int(p) for p in parts)
    except ValueError:
        raise ParameterError(
            f"Invalid color {color!r}. Components must be integers 0-65535."
        ) from None
    for channel in (r, g, b):
        if not 0 <= channel <= 65535:
            raise ParameterError(f"Invalid color {color!r}. Components must be within 0-65535.")
    return r, g, b


def rgb65535_to_hex(triple: str) -> str:
    """Convert Keynote's "r,g,b" (each 0-65535) into "#RRGGBB".

    Keynote reports colour as three 16-bit channels, so every consumer had to
    divide by 257 and hex-encode by hand. Values Keynote produces are multiples
    of 257, so this is exact for them; anything else is rounded to the nearest
    8-bit channel. Returns "" if the input is not a usable triple, so a caller
    can tell a failed conversion from a real colour.
    """
    parts = [p.strip() for p in (triple or "").split(",")]
    if len(parts) != 3:
        return ""
    try:
        raw = [int(p) for p in parts]
    except ValueError:
        return ""
    # Validate the RAW 0-65535 range, not the divided one: -5 would otherwise
    # round to 0 and be reported as a perfectly plausible #000000.
    if any(c < 0 or c > 65535 for c in raw):
        return ""
    return "#{:02X}{:02X}{:02X}".format(*(round(c / 257) for c in raw))
