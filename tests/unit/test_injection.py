"""Injection safety: user strings must reach osascript as argv, never spliced
into AppleScript source.

For every tool that accepts user text we call it with adversarial strings and
assert (a) the string is passed as an argv element of the osascript command,
and (b) the generated AppleScript source does not contain it.
"""

import pytest

ADVERSARIAL = [
    'he said "hello" and left',
    'backslash \\ and escaped quote \\"',
    'quote" then ¬\ntell application "Finder" to quit',
    "line one\nline two\nline three",
    "emoji 🎉🚀 CJK 中文字符 RTL שלום עולם",
    "trailing backslash \\",
    '"; do shell script "true"; "',
]


def _calls(mock_run):
    """(cmd_list, script_source) pairs for every osascript invocation."""
    out = []
    for call in mock_run.call_args_list:
        cmd = call.args[0] if call.args else call.kwargs.get("args")
        out.append((cmd, call.kwargs.get("input", "")))
    return out


def _assert_string_safe(mock_run, payload: str):
    calls = _calls(mock_run)
    assert calls, "osascript was never invoked"
    in_argv = any(payload in cmd[2:] for cmd, _ in calls)
    in_source = any(payload in script for _, script in calls)
    assert in_argv, f"payload was not passed via argv: {payload!r}"
    assert not in_source, f"payload was spliced into AppleScript source: {payload!r}"
    for cmd, script in calls:
        assert cmd[:2] == ["/usr/bin/osascript", "-"]
        if len(cmd) > 2:
            assert "on run argv" in script, "script takes argv but has no run handler"


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_add_text_box_payload_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.add_text_box(1, payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_edit_text_item_payload_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.edit_text_item(1, 1, payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_speaker_notes_payload_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.set_speaker_notes(1, payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_doc_name_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.get_slide_content(1, doc_name=payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_create_presentation_theme_via_argv(presentation_tools, mock_subprocess_run, payload):
    mock_subprocess_run.return_value.stdout = "Untitled|default theme"
    await presentation_tools.create_presentation("t", theme=payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_open_presentation_path_via_argv(presentation_tools, mock_subprocess_run, payload):
    await presentation_tools.open_presentation(payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_set_layout_via_argv(slide_tools, mock_subprocess_run, payload):
    mock_subprocess_run.return_value.stdout = "success"
    await slide_tools.set_slide_layout(1, payload)
    _assert_string_safe(mock_subprocess_run, payload)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_bullet_items_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.add_bullet_list(1, [payload, "second"])
    calls = _calls(mock_subprocess_run)
    assert any(any(payload in arg for arg in cmd[2:]) for cmd, _ in calls)
    assert all(payload not in script for _, script in calls)


@pytest.mark.parametrize("payload", ADVERSARIAL)
async def test_build_effect_via_argv(content_tools, mock_subprocess_run, payload):
    await content_tools.add_build_in(1, "text", 1, effect=payload)
    _assert_string_safe(mock_subprocess_run, payload)


async def test_font_name_via_argv(content_tools, mock_subprocess_run):
    payload = 'Evil" Font ¬\n"'
    await content_tools.add_text_box(1, "text", font_name=payload)
    _assert_string_safe(mock_subprocess_run, payload)


async def test_color_string_is_validated_not_spliced(content_tools, mock_subprocess_run):
    """A color that is not 'int,int,int' must be rejected before any osascript
    call - it is the one string interpolated into source after validation."""
    result = await content_tools.add_text_box(1, "text", color='0,0,0} & (do shell script "true")')
    assert "Failed" in result[0].text
    assert not mock_subprocess_run.called


async def test_valid_color_is_interpolated_as_numbers(content_tools, mock_subprocess_run):
    await content_tools.add_text_box(1, "text", color="65535, 0, 128")
    ((_, script),) = _calls(mock_subprocess_run)[-1:]
    assert "{65535, 0, 128}" in script
