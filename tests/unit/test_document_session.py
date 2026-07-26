"""PHASE 9 Task 1 — document resolution must never guess.

The field report's highest-severity item: tools that omitted ``doc_name``
resolved to Keynote's ``front document`` inside the AppleScript, so a call
right after ``open_presentation`` could land on a different deck that happened
to be frontmost, and nothing in the reply said which document was used.
``screenshot_slide`` returned "the export matches the editor view" for slides
belonging to a presentation nobody had asked about.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mcp.types import TextContent

from keynote_mcp.server import KeynoteMCPServer, _echo_resolved_document
from keynote_mcp.utils.error_handler import ParameterError
from keynote_mcp.utils.session import SESSION, open_document_names, resolve_document


class FakeRunner:
    """Runner that answers the document-listing script with a fixed set."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.calls = 0

    def run(self, _script: str, *_argv: str, **_kwargs: object) -> str:
        self.calls += 1
        return "|||".join(self.names)


class TestResolveDocument:
    def test_explicit_name_is_used_and_costs_no_apple_event(self) -> None:
        runner = FakeRunner(["A.key", "B.key"])
        assert resolve_document(runner, "B.key") == "B.key"
        assert runner.calls == 0, "an explicit doc_name must not need a lookup"

    def test_single_open_document_is_adopted_as_the_session_default(self) -> None:
        runner = FakeRunner(["Only.key"])
        assert resolve_document(runner) == "Only.key"
        assert SESSION.get_default() == "Only.key"
        # Adopted, so the next call spends no further Apple event.
        before = runner.calls
        assert resolve_document(runner) == "Only.key"
        assert runner.calls == before

    def test_session_default_wins_over_a_lookup(self) -> None:
        SESSION.set_default("Chosen.key")
        runner = FakeRunner(["Other.key", "Chosen.key"])
        assert resolve_document(runner) == "Chosen.key"
        assert runner.calls == 0

    def test_several_open_and_no_default_is_an_error_that_names_them(self) -> None:
        runner = FakeRunner(["A.key", "B.key", "C.key"])
        with pytest.raises(ParameterError) as excinfo:
            resolve_document(runner)
        message = str(excinfo.value)
        # The whole point: say what the candidates are instead of picking one.
        for name in ("A.key", "B.key", "C.key"):
            assert name in message
        assert "doc_name" in message
        assert "guess" in message

    def test_no_documents_open_is_an_actionable_error(self) -> None:
        runner = FakeRunner([])
        with pytest.raises(ParameterError) as excinfo:
            resolve_document(runner)
        message = str(excinfo.value)
        assert "No Keynote presentation is open" in message
        assert "create_presentation" in message
        assert "open_presentation" in message

    def test_closing_the_default_forgets_it(self) -> None:
        SESSION.set_default("Gone.key")
        SESSION.clear_default("Gone.key")
        assert SESSION.get_default() == ""

    def test_closing_a_different_document_keeps_the_default(self) -> None:
        SESSION.set_default("Keep.key")
        SESSION.clear_default("Other.key")
        assert SESSION.get_default() == "Keep.key"


class TestOpenDocumentNames:
    def test_empty_result_is_no_documents_not_one_blank_name(self) -> None:
        runner = MagicMock()
        runner.run.return_value = ""
        assert open_document_names(runner) == []


class TestEchoResolvedDocument:
    def test_appends_the_resolved_document(self) -> None:
        SESSION.note_resolved("Deck.key")
        out = _echo_resolved_document([TextContent(type="text", text="Added shape")])
        assert out[0].text == "Added shape\n[document: Deck.key]"

    def test_no_echo_when_nothing_was_resolved(self) -> None:
        SESSION.note_resolved("")
        out = _echo_resolved_document([TextContent(type="text", text="53 themes")])
        assert out[0].text == "53 themes"

    def test_no_duplicate_when_the_reply_already_names_it(self) -> None:
        SESSION.note_resolved("Deck.key")
        out = _echo_resolved_document([TextContent(type="text", text="Closed Deck.key")])
        assert out[0].text == "Closed Deck.key"

    def test_error_replies_are_labelled_too(self) -> None:
        """A failure especially needs to say which document it failed on."""
        SESSION.note_resolved("Deck.key")
        out = _echo_resolved_document([TextContent(type="text", text="Failed to add shape: x")])
        assert "[document: Deck.key]" in out[0].text


class TestNoFrontDocumentFallbackRemains:
    def test_tool_layer_never_says_front_document(self) -> None:
        """The guess is gone structurally, not just by convention.

        Any reintroduced `front document` in a resolution path would restore
        the exact bug, so the absence is asserted rather than trusted.
        """
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "src" / "keynote_mcp"
        offenders = []
        for path in root.rglob("*.py"):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("--"):
                    continue
                if "front document" in line and "targetDoc" in line:
                    offenders.append(f"{path.name}:{lineno}")
        assert offenders == [], f"front-document resolution reintroduced at {offenders}"


class TestSchemaDocumentsTheBehavior:
    def test_doc_name_description_no_longer_promises_front_document(self) -> None:
        server = KeynoteMCPServer()
        for tool in server.all_tools():
            desc = tool.inputSchema.get("properties", {}).get("doc_name", {}).get("description", "")
            if desc:
                assert "front document" not in desc, tool.name
                assert "session document" in desc, tool.name
