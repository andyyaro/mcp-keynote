"""Stage a ``.kth`` theme file where Keynote's sandbox can read it.

``make new document with data POSIX file <kth>`` builds a document from a
theme file that is not installed in the theme chooser (probed on Keynote
15.3.1: all 35 layouts of a company theme arrive). Keynote reads the file
itself, so a path outside its sandbox container risks the same AppleEvent
wedge as an AppleScript ``open`` there (see CLAUDE.md, field-test facts).
The file is therefore copied into the container's own ``tmp`` first, and the
copy is removed once the new document has been saved.
"""

from __future__ import annotations

import os
import shutil
import uuid

from .error_handler import FileOperationError, ParameterError, validate_file_path

# Keynote 15.x ("Creator Studio") is com.apple.Keynote; 14.x was
# com.apple.iWork.Keynote. The first container that exists wins.
_CONTAINER_IDS = ("com.apple.Keynote", "com.apple.iWork.Keynote")


def _container_tmp() -> str:
    for bundle_id in _CONTAINER_IDS:
        data = os.path.expanduser(f"~/Library/Containers/{bundle_id}/Data")
        if os.path.isdir(data):
            return os.path.join(data, "tmp")
    raise FileOperationError(
        "Keynote's sandbox container was not found (looked for "
        f"{', '.join(_CONTAINER_IDS)} under ~/Library/Containers). Launch Keynote "
        "once, or install the theme by double-clicking it and pass its name as theme."
    )


def resolve_theme_file(path: str) -> str:
    """Validate a theme-file argument and return its absolute path."""
    path = os.path.realpath(os.path.expanduser(validate_file_path(path)))
    if not path.lower().endswith(".kth"):
        raise ParameterError(f"theme_file must be a Keynote theme (.kth): {path}")
    if not os.path.exists(path):
        raise ParameterError(f"theme_file does not exist: {path}")
    return path


def stage_theme_file(path: str) -> str:
    """Copy a validated ``.kth`` into Keynote's container; return the copy's path.

    A theme may be a single zip file or a package directory; both are copied.
    Call :func:`discard_staged_theme` in a ``finally`` once the document built
    from it is saved.
    """
    tmp = _container_tmp()
    os.makedirs(tmp, exist_ok=True)
    staged = os.path.join(tmp, f"keynote-mcp-theme-{uuid.uuid4().hex}.kth")
    try:
        if os.path.isdir(path):
            shutil.copytree(path, staged)
        else:
            shutil.copyfile(path, staged)
    except OSError as e:
        raise FileOperationError(
            f"Could not copy the theme into Keynote's sandbox ({staged}): {e}. If macOS "
            "asked to allow access to data from other apps, allow it and retry."
        ) from e
    return staged


def discard_staged_theme(staged: str) -> None:
    """Best-effort removal of a staged copy."""
    if os.path.isdir(staged):
        shutil.rmtree(staged, ignore_errors=True)
    else:
        try:
            os.remove(staged)
        except OSError:
            pass
