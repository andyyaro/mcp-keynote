"""Utility modules for Keynote-MCP."""

from .applescript_runner import AppleScriptRunner
from .error_handler import (
    ELEMENT_TYPE_MAP,
    AppleScriptError,
    FileOperationError,
    KeynoteError,
    ParameterError,
    parse_color,
    rgb65535_to_hex,
    validate_coordinates,
    validate_dimensions,
    validate_element_type,
    validate_file_path,
    validate_index,
    validate_number,
    validate_slide_number,
)
from .fonts import split_font_name
from .session import (
    SESSION,
    DocumentSession,
    open_document_names,
    resolve_document,
)

__all__ = [
    "ELEMENT_TYPE_MAP",
    "SESSION",
    "AppleScriptError",
    "AppleScriptRunner",
    "DocumentSession",
    "FileOperationError",
    "KeynoteError",
    "ParameterError",
    "open_document_names",
    "parse_color",
    "resolve_document",
    "rgb65535_to_hex",
    "split_font_name",
    "validate_coordinates",
    "validate_dimensions",
    "validate_element_type",
    "validate_file_path",
    "validate_index",
    "validate_number",
    "validate_slide_number",
]
