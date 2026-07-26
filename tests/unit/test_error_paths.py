"""Every tool method returns a 'Failed …' text (never raises) when osascript
errors underneath it."""

import subprocess

import pytest

from keynote_mcp.server import _configure_logging

NOT_FOUND = (
    "execution error: Keynote got an error: Can’t get slide 9 of document 1. Invalid index. (-1719)"
)


def _fail(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["osascript", "-"], returncode=1, stdout="", stderr=NOT_FOUND
    )


PRESENTATION_CALLS = [
    ("create_presentation", ("t",), {}),
    ("open_presentation", ("/x.key",), {}),
    ("save_presentation", (), {}),
    ("close_presentation", (), {}),
    ("list_presentations", (), {}),
    ("set_presentation_theme", ("Slate",), {}),
    ("get_presentation_info", (), {}),
    ("get_available_themes", (), {}),
    ("get_slide_size", (), {}),
]

SLIDE_CALLS = [
    ("add_slide", (), {}),
    ("delete_slide", (1,), {}),
    ("duplicate_slide", (1,), {}),
    ("move_slide", (1, 2), {}),
    ("get_slide_count", (), {}),
    ("select_slide", (1,), {}),
    ("set_slide_layout", (1, "Blank"), {}),
    ("get_slide_info", (1,), {}),
    ("get_available_layouts", (), {}),
]

CONTENT_CALLS = [
    ("add_text_box", (1, "t"), {}),
    ("add_title", (1, "t"), {}),
    ("add_subtitle", (1, "t"), {}),
    ("add_bullet_list", (1, ["a"]), {}),
    ("add_numbered_list", (1, ["a"]), {}),
    ("add_code_block", (1, "c"), {}),
    ("add_quote", (1, "q"), {}),
    ("set_slide_content", (1,), {"title": "t"}),
    ("get_slide_content", (1,), {}),
    ("edit_text_item", (1, 1, "x"), {}),
    ("delete_element", (1, "text", 1), {}),
    ("move_element", (1, "text", 1, 0, 0), {}),
    ("resize_element", (1, "text", 1, 10, 10), {}),
    ("get_speaker_notes", (1,), {}),
    ("set_speaker_notes", (1, "n"), {}),
    ("clear_slide", (1,), {}),
    ("set_element_opacity", (1, "shape", 1, 50), {}),
    ("add_build_in", (1, "text", 1), {}),
    ("remove_build_in", (1, "text", 1), {}),
    ("add_shape", (1,), {}),
]


@pytest.mark.parametrize(("method", "args", "kwargs"), PRESENTATION_CALLS)
async def test_presentation_error_paths(
    presentation_tools, mock_subprocess_run, method, args, kwargs
):
    _fail(mock_subprocess_run)
    result = await getattr(presentation_tools, method)(*args, **kwargs)
    assert result[0].text.startswith("Failed"), result[0].text


@pytest.mark.parametrize(("method", "args", "kwargs"), SLIDE_CALLS)
async def test_slide_error_paths(slide_tools, mock_subprocess_run, method, args, kwargs):
    _fail(mock_subprocess_run)
    result = await getattr(slide_tools, method)(*args, **kwargs)
    assert result[0].text.startswith("Failed"), result[0].text


@pytest.mark.parametrize(("method", "args", "kwargs"), CONTENT_CALLS)
async def test_content_error_paths(content_tools, mock_subprocess_run, method, args, kwargs):
    _fail(mock_subprocess_run)
    result = await getattr(content_tools, method)(*args, **kwargs)
    assert result[0].text.startswith("Failed"), result[0].text


async def test_builds_batch_skips_bullet_dots(content_tools, mock_subprocess_run):
    # dot-detection script reports index 1 as a bullet dot; index 2 proceeds
    mock_subprocess_run.return_value.stdout = "1"
    result = await content_tools.add_builds_to_slide(1, "1,2")
    text = result[0].text
    assert "text 1: skipped (bullet dot)" in text
    assert "text 2: OK" in text


async def test_builds_batch_reports_failures(content_tools, mock_subprocess_run):
    _fail(mock_subprocess_run)
    result = await content_tools.add_builds_to_slide(1, "2")
    assert "FAILED" in result[0].text


def test_configure_logging_respects_env(monkeypatch):
    monkeypatch.setenv("KEYNOTE_MCP_LOG_LEVEL", "DEBUG")
    _configure_logging()
    monkeypatch.setenv("KEYNOTE_MCP_LOG_LEVEL", "not-a-level")
    _configure_logging()


def test_main_module_importable():
    import keynote_mcp.__main__  # noqa: F401 - import must not start the server
