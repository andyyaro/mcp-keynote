"""Session document resolution — which presentation a call actually targets.

Before Phase 9 every tool that omitted ``doc_name`` resolved to Keynote's
``front document`` **inside the AppleScript**, once per call. Three
consequences, all observed in the field:

1. A call right after ``open_presentation`` could land on a different deck that
   happened to be frontmost, because "frontmost" is the user's window order,
   not the session's intent.
2. Nothing in any reply said which document was used, so a wrong target was
   invisible — ``screenshot_slide`` returned a confident correctness note about
   a presentation nobody had asked about.
3. With several decks open, the server guessed instead of asking.

This module replaces the guess. Resolution happens in **Python**, produces a
CONCRETE document name, and that name is what reaches AppleScript — so
``front document`` no longer appears anywhere in the tool layer, and every
reply can name its target.

Cost: at most one extra Apple event per session. An explicit ``doc_name``
needs none; a remembered session default needs none; only the first
default-less call has to look at the open documents, and it adopts the answer.
"""

from __future__ import annotations

import logging
import threading

from .error_handler import ParameterError

logger = logging.getLogger(__name__)


class DocumentSession:
    """The session's default document, remembered across tool calls.

    ``create_presentation`` and ``open_presentation`` set it: the document a
    caller just made or opened is what the next call means. ``close_presentation``
    clears it when that document is the one closing.
    """

    def __init__(self) -> None:
        self._default: str = ""
        self._lock = threading.Lock()
        # The most recently resolved document, for echoing into replies.
        self._last_resolved: str = ""

    # --- session default ---------------------------------------------------
    def set_default(self, doc_name: str) -> None:
        if not doc_name:
            return
        with self._lock:
            if self._default != doc_name:
                logger.info("Session default document is now %r", doc_name)
            self._default = doc_name

    def get_default(self) -> str:
        with self._lock:
            return self._default

    def clear_default(self, doc_name: str = "") -> None:
        """Forget the default. With ``doc_name``, only if it IS the default."""
        with self._lock:
            if not doc_name or self._default == doc_name:
                self._default = ""

    # --- echo --------------------------------------------------------------
    def note_resolved(self, doc_name: str) -> None:
        with self._lock:
            self._last_resolved = doc_name

    @property
    def last_resolved(self) -> str:
        with self._lock:
            return self._last_resolved

    def reset(self) -> None:
        """Test hook: forget everything."""
        with self._lock:
            self._default = ""
            self._last_resolved = ""


# One session per server process.
SESSION = DocumentSession()


def open_document_names(runner: object) -> list[str]:
    """Names of every open Keynote document, in Keynote's own order."""
    result = runner.run(  # type: ignore[attr-defined]
        """
        tell application "Keynote"
            if (count of documents) is 0 then return ""
            set docNames to name of every document
            set AppleScript's text item delimiters to "|||"
            set joined to docNames as text
            set AppleScript's text item delimiters to ""
            return joined
        end tell
        """
    )
    return [n for n in result.split("|||") if n]


def _ambiguous_error(names: list[str]) -> ParameterError:
    listed = "\n".join(f"  - {n}" for n in names)
    return ParameterError(
        f"{len(names)} presentations are open and no document was specified, so "
        "this call would have had to guess which one you meant:\n"
        f"{listed}\n"
        "Pass doc_name to choose one. (open_presentation and "
        "create_presentation set the session default automatically; a call "
        "that arrives without one after several documents are open is exactly "
        "the case that used to silently target whichever window was frontmost.)"
    )


def resolve_document(runner: object, doc_name: str = "") -> str:
    """Resolve ``doc_name`` to a concrete open-document name.

    - explicit ``doc_name`` — trusted as given (no Apple event spent; a
      nonexistent name surfaces as Keynote's own -1728, which the error
      handler expands with the open-document list)
    - empty, session default set — the default
    - empty, no default — the single open document, adopted as the default;
      an error naming the candidates if there are several, or none

    Raises ParameterError rather than guessing.
    """
    if doc_name:
        SESSION.note_resolved(doc_name)
        return doc_name

    default = SESSION.get_default()
    if default:
        SESSION.note_resolved(default)
        return default

    names = open_document_names(runner)
    if not names:
        raise ParameterError(
            "No Keynote presentation is open. Use create_presentation to make "
            "one or open_presentation to open an existing file."
        )
    if len(names) > 1:
        raise _ambiguous_error(names)

    SESSION.set_default(names[0])
    SESSION.note_resolved(names[0])
    return names[0]
