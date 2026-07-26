"""Shared base for the tool classes.

Exists for one job: every tool resolves its target document the same way, in
Python, through ``_doc``. Before Phase 9 each tool class carried its own copy
of an AppleScript fragment that fell back to the frontmost document whenever
docName was empty — five identical copies, and every one of them was a place
where a call could silently land on whichever deck the user happened to have
in front.
"""

from __future__ import annotations

from ..utils import AppleScriptRunner, resolve_document


class DocumentTargetedTools:
    """Mixin giving a tool class one resolved-document entry point."""

    runner: AppleScriptRunner

    def _doc(self, doc_name: str = "") -> str:
        """Resolve ``doc_name`` to a concrete open-document name.

        Every public tool method calls this first, so the name that reaches
        AppleScript is never empty and every reply can say which document it
        acted on. Raises ParameterError when the target is ambiguous (several
        documents open, no session default) rather than guessing — the
        guessing is the bug this replaced.
        """
        return resolve_document(self.runner, doc_name)
