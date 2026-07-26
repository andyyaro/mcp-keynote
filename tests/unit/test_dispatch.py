"""Server dispatch: every tool routes, errors never escape, handlers survive."""

from unittest.mock import patch

import mcp.types as mtypes
import pytest
from mcp.types import TextContent

from keynote_mcp.server import KeynoteMCPServer


@pytest.fixture
def server(mock_subprocess_run, monkeypatch):
    monkeypatch.delenv("UNSPLASH_KEY", raising=False)
    return KeynoteMCPServer()


# (tool name, minimal arguments, osascript stdout the parser expects)
DISPATCH_CASES = [
    ("create_presentation", {"title": "t"}, "Doc|default theme"),
    ("open_presentation", {"file_path": "/tmp/x.key"}, "x.key"),
    ("save_presentation", {}, "x.key"),
    ("close_presentation", {"should_save": False}, "x.key"),
    ("list_presentations", {}, "a|||b"),
    ("set_presentation_theme", {"theme_name": "Slate"}, "success"),
    ("get_presentation_info", {}, "doc|||3|||Slate"),
    ("get_available_themes", {}, "Slate|||Black"),
    ("get_slide_size", {}, "1920,1080"),
    ("add_slide", {"position": 2, "layout": "Blank"}, "2|Blank"),
    ("delete_slide", {"slide_number": 1}, ""),
    ("duplicate_slide", {"slide_number": 1}, ""),
    ("move_slide", {"from_position": 1, "to_position": 2}, ""),
    ("move_slide", {"from_position": 2, "to_position": 2}, ""),
    ("get_slide_count", {}, "4"),
    ("select_slide", {"slide_number": 1}, ""),
    ("set_slide_layout", {"slide_number": 1, "layout": "Blank"}, "success"),
    ("get_slide_info", {"slide_number": 1}, "1|||Blank|||3"),
    ("get_available_layouts", {}, "Blank|||Title"),
    ("add_text_box", {"slide_number": 1, "text": "hi", "x": 5, "font_size": 96}, "3"),
    ("add_title", {"slide_number": 1, "title": "hi", "color": "1,2,3"}, "1"),
    ("add_subtitle", {"slide_number": 1, "subtitle": "hi"}, "1"),
    ("add_bullet_list", {"slide_number": 1, "items": ["a", "b"]}, "1"),
    ("add_numbered_list", {"slide_number": 1, "items": ["a"]}, "1"),
    ("add_code_block", {"slide_number": 1, "code": "x=1", "color": "1,2,3"}, "1"),
    ("add_quote", {"slide_number": 1, "quote": "q"}, "1"),
    ("set_slide_content", {"slide_number": 1, "title": "t", "body": "b"}, ""),
    ("set_slide_content", {"slide_number": 1}, ""),
    ("get_slide_content", {"slide_number": 1}, "text_items:0"),
    ("edit_text_item", {"slide_number": 1, "item_index": 1, "new_text": "x"}, ""),
    ("delete_element", {"slide_number": 1, "element_type": "text", "element_index": 1}, ""),
    (
        "move_element",
        {"slide_number": 1, "element_type": "shape", "element_index": 1, "x": 5, "y": 6},
        "",
    ),
    (
        "resize_element",
        {"slide_number": 1, "element_type": "image", "element_index": 1, "width": 5, "height": 6},
        "",
    ),
    ("get_speaker_notes", {"slide_number": 1}, "notes"),
    ("set_speaker_notes", {"slide_number": 1, "notes": "n"}, ""),
    ("clear_slide", {"slide_number": 1}, ""),
    (
        "set_element_opacity",
        {"slide_number": 1, "element_type": "shape", "element_index": 1, "opacity": 8},
        "",
    ),
    ("add_build_in", {"slide_number": 1, "element_type": "text", "element_index": 1}, "w"),
    ("remove_build_in", {"slide_number": 1, "element_type": "text", "element_index": 1}, "w"),
    ("add_builds_to_slide", {"slide_number": 1, "element_indices": "1,2"}, "w"),
    ("add_builds_to_slide", {"slide_number": 1, "element_indices": ""}, "w"),
    ("add_builds_to_slide", {"slide_number": 1, "element_indices": "x,y"}, "w"),
    ("add_shape", {"slide_number": 1, "opacity": 8}, ""),
    ("add_table", {"slide_number": 1, "data": [["a", "b"], ["c", 1]]}, "TB|1|0,0|600,300"),
    ("add_table", {"slide_number": 1, "data": [["tiny"]]}, ""),
    (
        "add_chart",
        {
            "slide_number": 1,
            "chart_type": "bar",
            "row_names": ["r"],
            "column_names": ["c"],
            "data": [[1]],
        },
        "CH|1|0,0|600,400",
    ),
    (
        "add_chart",
        {"slide_number": 1, "chart_type": "donut", "row_names": [], "column_names": [], "data": []},
        "",
    ),
    ("add_line", {"slide_number": 1, "x1": 0, "y1": 0, "x2": 9, "y2": 9}, "LN|1|0,0|9,9"),
    (
        "add_colored_panel",
        {"slide_number": 1, "x": 0, "y": 0, "width": 10, "height": 10},
        "PN|1|0,0|10,10",
    ),
    (
        "style_text_range",
        {"slide_number": 1, "item_index": 1, "start": 1, "end": 2, "color": "#FFF"},
        "",
    ),
    ("style_text_range", {"slide_number": 1, "item_index": 1, "start": 1, "end": 2}, ""),
    ("replace_image", {"slide_number": 1, "image_index": 1, "image_path": "/no/such.png"}, ""),
    (
        "set_element_style",
        {"slide_number": 1, "element_type": "shape", "element_index": 1, "rotation": 10},
        "",
    ),
    ("set_slide_transition", {"slide_number": 1, "effect": "push"}, "push|1.0"),
    ("set_slide_transition", {"slide_number": 1, "effect": "warp-speed"}, ""),
    ("set_slide_skipped", {"slide_number": 1, "skipped": True}, "true"),
    ("set_slide_size", {"width": 1920, "height": 1080}, "1920x1080"),
    ("set_slide_size", {"width": 5, "height": 5}, ""),
    ("set_document_settings", {"auto_loop": True}, ""),
    ("set_document_settings", {}, ""),
    ("build_deck", {"spec": {"slides": "garbage"}}, ""),
    ("build_deck", {}, ""),
    ("describe_deck", {}, "not-a-parseable-head"),
    ("export_presentation", {"format": "html", "output_path": "/tmp/deck-out"}, ""),
    ("export_presentation", {"format": "gif", "output_path": "/tmp/x"}, ""),
    ("export_pdf", {"output_path": "/tmp/out.pdf"}, ""),
    ("search_unsplash_images", {"query": "cat"}, ""),
    ("add_unsplash_image_to_slide", {"slide_number": 1, "query": "cat"}, ""),
    ("get_random_unsplash_image", {"slide_number": 1}, ""),
    ("no_such_tool", {}, ""),
]


@pytest.mark.parametrize(("name", "arguments", "stdout"), DISPATCH_CASES)
async def test_dispatch_returns_text_content(server, mock_subprocess_run, name, arguments, stdout):
    mock_subprocess_run.return_value.stdout = stdout
    result = await server._dispatch(name, arguments)
    assert len(result) >= 1
    assert all(isinstance(item, TextContent) for item in result)


async def test_dispatch_add_image(server, mock_subprocess_run, tmp_path):
    image = tmp_path / "img.png"
    image.write_bytes(b"png")
    result = await server._dispatch(
        "add_image", {"slide_number": 1, "image_path": str(image), "x": 1, "y": 2}
    )
    assert isinstance(result[0], TextContent)


async def test_dispatch_screenshot_slide(server, mock_subprocess_run, tmp_path):
    result = await server._dispatch(
        "screenshot_slide",
        {"slide_number": 1, "output_path": str(tmp_path / "s.png"), "format": "jpg"},
    )
    # runner is mocked so no file is produced - the tool must say so, not raise
    assert "not generated" in result[0].text


async def _call(server, name, arguments):
    handler = server.server.request_handlers[mtypes.CallToolRequest]
    request = mtypes.CallToolRequest(
        method="tools/call",
        params=mtypes.CallToolRequestParams(name=name, arguments=arguments),
    )
    return (await handler(request)).root


async def test_handler_missing_required_arg_is_structured_error(server):
    result = await _call(server, "delete_slide", {})
    assert result.isError is True or "slide_number" in result.content[0].text


async def test_handler_parameter_error_is_text_not_crash(server):
    result = await _call(server, "delete_slide", {"slide_number": -2})
    assert "Invalid slide number" in result.content[0].text


async def test_handler_survives_unexpected_exception(server):
    with patch.object(server, "_dispatch", side_effect=RuntimeError("boom")):
        result = await _call(server, "get_slide_count", {})
        assert "Unknown error: boom" in result.content[0].text
    # and the server still answers afterwards
    list_handler = server.server.request_handlers[mtypes.ListToolsRequest]
    listing = (await list_handler(mtypes.ListToolsRequest(method="tools/list"))).root
    assert len(listing.tools) >= 40


async def test_handler_missing_args_key_entirely(server):
    result = await _call(server, "list_presentations", {})
    assert isinstance(result.content[0], TextContent)


async def test_unsplash_disabled_without_key(server):
    result = await server._dispatch("search_unsplash_images", {"query": "cat"})
    assert "UNSPLASH_KEY" in result[0].text


async def test_unsplash_dispatch_forwards_args(mock_subprocess_run, monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setenv("UNSPLASH_KEY", "k")
    server = KeynoteMCPServer()
    assert server.unsplash_tools is not None
    sentinel = [TextContent(type="text", text="ok")]
    server.unsplash_tools.search_unsplash_images = AsyncMock(return_value=sentinel)
    server.unsplash_tools.add_unsplash_image_to_slide = AsyncMock(return_value=sentinel)
    server.unsplash_tools.get_random_unsplash_image = AsyncMock(return_value=sentinel)

    assert (await server._dispatch("search_unsplash_images", {"query": "q"})) == sentinel
    assert (
        await server._dispatch(
            "add_unsplash_image_to_slide", {"slide_number": 1, "query": "q", "x": 1}
        )
    ) == sentinel
    assert (await server._dispatch("get_random_unsplash_image", {"slide_number": 1})) == sentinel
    server.unsplash_tools.search_unsplash_images.assert_awaited_once_with(
        query="q", per_page=10, orientation=None, order_by="relevant"
    )
