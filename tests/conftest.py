"""Shared fixtures for keynote-mcp tests."""

import subprocess
from unittest.mock import patch

import pytest

from keynote_mcp.tools.content import ContentTools
from keynote_mcp.tools.deck import DeckTools
from keynote_mcp.tools.export import ExportTools
from keynote_mcp.tools.objects import ObjectTools
from keynote_mcp.tools.presentation import PresentationTools
from keynote_mcp.tools.slide import SlideTools
from keynote_mcp.utils.applescript_runner import AppleScriptRunner
from keynote_mcp.utils.session import SESSION


@pytest.fixture(autouse=True)
def _reset_wedge_flag():
    """The wedge flag is class-level state; never leak it between tests."""
    AppleScriptRunner._queue_wedged = False
    yield
    AppleScriptRunner._queue_wedged = False


@pytest.fixture(autouse=True)
def _reset_document_session():
    """The session default document is process-global, like the real server's.

    Without this, a test that creates or opens a presentation leaves its name
    as the default and later tests resolve to it instead of doing their own
    lookup - which showed up as build-tool tests passing alone and failing in
    the suite.
    """
    SESSION.reset()
    yield
    SESSION.reset()


@pytest.fixture
def mock_subprocess_run():
    """Patch subprocess.run to prevent real osascript calls."""
    with patch("keynote_mcp.utils.applescript_runner.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["osascript", "-"],
            returncode=0,
            stdout="success",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def runner(mock_subprocess_run):
    """AppleScriptRunner with mocked subprocess."""
    return AppleScriptRunner()


@pytest.fixture
def content_tools(mock_subprocess_run):
    """ContentTools with mocked AppleScript runner."""
    return ContentTools()


@pytest.fixture
def presentation_tools(mock_subprocess_run):
    """PresentationTools with mocked AppleScript runner."""
    return PresentationTools()


@pytest.fixture
def slide_tools(mock_subprocess_run):
    """SlideTools with mocked AppleScript runner."""
    return SlideTools()


@pytest.fixture
def export_tools(mock_subprocess_run):
    """ExportTools with mocked AppleScript runner."""
    return ExportTools()


@pytest.fixture
def object_tools(mock_subprocess_run):
    """ObjectTools with mocked AppleScript runner."""
    return ObjectTools()


@pytest.fixture
def deck_tools(mock_subprocess_run):
    """DeckTools with mocked AppleScript runner."""
    return DeckTools()
