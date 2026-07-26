"""Utility modules for Keynote-MCP."""

from .applescript_runner import AppleScriptRunner
from .error_handler import (
    ELEMENT_TYPE_MAP,
    AppleScriptError,
    FileOperationError,
    KeynoteError,
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

__all__ = [
    "ELEMENT_TYPE_MAP",
    "AppleScriptError",
    "AppleScriptRunner",
    "FileOperationError",
    "KeynoteError",
    "ParameterError",
    "parse_color",
    "validate_coordinates",
    "validate_dimensions",
    "validate_element_type",
    "validate_file_path",
    "validate_index",
    "validate_number",
    "validate_slide_number",
]
