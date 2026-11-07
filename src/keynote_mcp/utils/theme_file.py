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
from typing import TYPE_CHECKING

from .error_handler import FileOperationError, ParameterError, validate_file_path

if TYPE_CHECKING:
    from .applescript_runner import AppleScriptRunner

# Keynote 15.x ("Creator Studio") is com.apple.Keynote; 14.x was
# com.apple.iWork.Keynote. Used only when the targeted app's id cannot be read.
_CONTAINER_IDS = ("com.apple.Keynote", "com.apple.iWork.Keynote")


def keynote_bundle_id(runner: AppleScriptRunner) -> str:
    """Bundle id of the app ``tell application "Keynote"`` drives, or "".

    Both containers can exist on one Mac (a 15.x trial next to 14.x, or a
    leftover after an uninstall). Staging into the OTHER app's container
    would put the file outside the driven app's sandbox, which is the wedge
    staging exists to avoid, so the container is chosen by this id.
    """
    try:
        return runner.run('return id of application "Keynote"', timeout=10.0).strip()
    except Exception:
        return ""


def keynote_container_data(bundle_id: str = "") -> str:
    """The ``Data`` directory of Keynote's sandbox container.

    With ``bundle_id`` only that app's container counts; without it (the id
    could not be read) the first existing container wins.
    """
    ids = (bundle_id,) if bundle_id else _CONTAINER_IDS
    for candidate in ids:
        data = os.path.expanduser(f"~/Library/Containers/{candidate}/Data")
        if os.path.isdir(data):
            return data
    raise FileOperationError(
        "Keynote's sandbox container was not found (looked for "
        f"{', '.join(ids)} under ~/Library/Containers). Launch Keynote "
        "once, or install the theme by double-clicking it and pass its name as theme."
    )


def resolve_theme_file(path: str) -> str:
    """Validate a theme-file argument and return its absolute path."""
    given = os.path.expanduser(validate_file_path(path))
    # The extension is checked on the path as given: a Brand.kth symlink may
    # point at a file whose own name says nothing.
    if not given.rstrip("/").lower().endswith(".kth"):
        raise ParameterError(f"theme_file must be a Keynote theme (.kth): {given}")
    if not os.path.exists(given):
        raise ParameterError(f"theme_file does not exist: {given}")
    return os.path.realpath(given)


def stage_theme_file(path: str, bundle_id: str = "") -> str:
    """Copy a validated ``.kth`` into Keynote's container; return the copy's path.

    A theme may be a single zip file or a package directory; both are copied.
    Call :func:`discard_staged_theme` in a ``finally`` once the document built
    from it is saved.
    """
    tmp = os.path.join(keynote_container_data(bundle_id), "tmp")
    os.makedirs(tmp, exist_ok=True)
    staged = os.path.join(tmp, f"keynote-mcp-theme-{uuid.uuid4().hex}.kth")
    try:
        if os.path.isdir(path):
            shutil.copytree(path, staged)
        else:
            shutil.copyfile(path, staged)
    except (OSError, RecursionError) as e:
        # A copy that failed part-way is never returned, so the caller's
        # finally cannot remove it; remove it here.
        discard_staged_theme(staged)
        raise FileOperationError(
            f"Could not copy the theme into Keynote's sandbox ({staged}): {e}. If macOS "
            "asked to allow access to data from other apps, allow it and retry."
        ) from e
    return staged


def discard_staged_theme(staged: str) -> None:
    """Best-effort removal of a staged copy."""
    if os.path.isdir(staged) and not os.path.islink(staged):
        shutil.rmtree(staged, ignore_errors=True)
    else:
        try:
            os.remove(staged)
        except OSError:
            pass
