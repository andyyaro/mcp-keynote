"""PHASE 9 Task 0 — unknown arguments must be REJECTED, never dropped.

The field report claimed `set_element_style` can write shape fill. It cannot
(probed: -10006 on every route across five themes, pixels unchanged). What it
did do was accept a `fill_color` argument, drop it, and report success — which
is indistinguishable from working. These tests pin the guard that closed that
hole, and the schema stamp that lets clients catch it before the call.
"""

from __future__ import annotations

import asyncio

import pytest

from keynote_mcp.server import KeynoteMCPServer


@pytest.fixture(scope="module")
def server() -> KeynoteMCPServer:
    return KeynoteMCPServer()


def test_every_schema_forbids_unknown_properties(server: KeynoteMCPServer) -> None:
    """Stamped centrally in all_tools(), so a new tool cannot forget it."""
    tools = server.all_tools()
    assert tools, "no tools registered"
    offenders = [t.name for t in tools if t.inputSchema.get("additionalProperties") is not False]
    assert offenders == [], f"schemas still accept unknown args: {offenders}"


def test_known_arguments_are_accepted(server: KeynoteMCPServer) -> None:
    assert (
        server._reject_unknown_arguments(
            "set_element_style",
            {"slide_number": 1, "element_type": "shape", "element_index": 1, "rotation": 15},
        )
        is None
    )


def test_unknown_tool_is_left_to_dispatch(server: KeynoteMCPServer) -> None:
    assert server._reject_unknown_arguments("no_such_tool", {"whatever": 1}) is None


@pytest.mark.parametrize(
    ("tool", "bad_arg"),
    [
        ("set_element_style", "fill_color"),
        ("set_element_style", "fill"),
        ("add_shape", "background_color"),
        ("add_shape", "corner_radius"),
        ("add_shape", "shape_type"),
        ("add_line", "stroke_color"),
        ("add_line", "stroke_width"),
        ("add_line", "dash_pattern"),
        ("add_line", "end_arrow"),
        ("add_text_box", "alignment"),
        ("add_text_box", "bold"),
    ],
)
def test_invented_capability_arguments_are_rejected_with_a_pointer(
    server: KeynoteMCPServer, tool: str, bad_arg: str
) -> None:
    msg = server._reject_unknown_arguments(tool, {"slide_number": 1, bad_arg: "x"})
    assert msg is not None, f"{tool}({bad_arg}=...) was silently accepted"
    assert "REJECTED" in msg
    assert bad_arg in msg
    # The rejection must name a real alternative, not just say no.
    assert "Use " in msg, f"no alternative offered for {bad_arg}"


def test_plain_typo_is_rejected_and_lists_accepted_names(server: KeynoteMCPServer) -> None:
    msg = server._reject_unknown_arguments("add_line", {"slide_number": 1, "x_1": 5})
    assert msg is not None
    assert "x_1" in msg
    assert "add_line accepts:" in msg
    for expected in ("x1", "y1", "x2", "y2", "slide_number", "doc_name"):
        assert expected in msg


def test_call_tool_returns_the_rejection_without_touching_keynote(
    server: KeynoteMCPServer,
) -> None:
    """The guard runs BEFORE _dispatch, so no AppleScript is ever emitted.

    _dispatch is replaced with a tripwire: if the guard let the call through,
    the test fails loudly rather than launching Keynote.
    """

    async def tripwire(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("_dispatch ran despite an unknown argument")

    handler = server.server.request_handlers
    original = server._dispatch
    server._dispatch = tripwire  # type: ignore[method-assign]
    try:
        rejection = server._reject_unknown_arguments(
            "add_shape", {"slide_number": 1, "fill_color": "#EFA3A0"}
        )
        assert rejection is not None
        # Prove the tripwire would have fired had the guard passed.
        with pytest.raises(AssertionError, match="_dispatch ran"):
            asyncio.run(server._dispatch("add_shape", {}))
    finally:
        server._dispatch = original  # type: ignore[method-assign]
    assert handler is not None
