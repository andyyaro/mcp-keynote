"""Field-test regressions for the sandbox trap (Phase 8.1).

The Phase 3 harness only exercised documents it created itself with an
explicit save_path, so it never saw: the unsaved-document save sheet, the
AppleScript-open queue wedge, or the recovery path. These tests pin the
fixed behavior with a mocked runner.
"""

import subprocess

import pytest

from keynote_mcp.utils.applescript_runner import AppleScriptRunner
from keynote_mcp.utils.error_handler import AppleScriptError
from keynote_mcp.utils.session import SESSION


def last_cmd(mock_run) -> list:
    return mock_run.call_args.args[0]


class TestCreateDefaultSavePath:
    async def test_default_path_resolved_and_returned(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        mock_subprocess_run.return_value.stdout = "Deck.key|default theme"
        result = await presentation_tools.create_presentation("Deck")
        expected = str(tmp_path / "Deck.key")
        assert last_cmd(mock_subprocess_run)[3] == expected
        assert expected in result[0].text

    async def test_title_sanitized_for_filename(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        mock_subprocess_run.return_value.stdout = "x|default theme"
        await presentation_tools.create_presentation("My/Deck: 2026")
        save_path = last_cmd(mock_subprocess_run)[3]
        assert save_path.startswith(str(tmp_path))
        basename = save_path.rsplit("/", 1)[1]
        assert ":" not in basename
        assert basename.endswith(".key")

    async def test_existing_file_is_never_overwritten(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        (tmp_path / "Deck.key").write_bytes(b"existing")
        mock_subprocess_run.return_value.stdout = "x|default theme"
        await presentation_tools.create_presentation("Deck")
        assert last_cmd(mock_subprocess_run)[3] == str(tmp_path / "Deck-2.key")

    async def test_explicit_path_gets_key_extension(
        self, presentation_tools, mock_subprocess_run, tmp_path
    ):
        mock_subprocess_run.return_value.stdout = "x|default theme"
        await presentation_tools.create_presentation("t", save_path=str(tmp_path / "deck"))
        assert last_cmd(mock_subprocess_run)[3] == str(tmp_path / "deck.key")

    async def test_first_slide_defaults_to_blank_layout(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        # A theme's first slide starts on a title layout whose unfilled
        # placeholders add_* tools would overlap; the server defaults it to
        # Blank (matching add_slide) and reports the choice.
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        mock_subprocess_run.return_value.stdout = "Deck.key|default theme|first slide: Blank layout"
        result = await presentation_tools.create_presentation("Deck")
        script = mock_subprocess_run.call_args.kwargs["input"]
        assert 'slide layout "Blank"' in script
        assert script.index('slide layout "Blank"') < script.index("save newDoc")
        assert "first slide: Blank layout" in result[0].text

    async def test_save_is_unconditional_in_script(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        mock_subprocess_run.return_value.stdout = "x|default theme"
        await presentation_tools.create_presentation("t")
        script = mock_subprocess_run.call_args.kwargs["input"]
        assert "save newDoc in POSIX file savePath" in script
        assert 'if savePath is not ""' not in script


class TestSavePresentationGuard:
    async def test_unsaved_without_path_is_refused(self, presentation_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "UNSAVED_NO_PATH|Untitled"
        result = await presentation_tools.save_presentation()
        text = result[0].text
        assert text.startswith("Failed to save presentation")
        assert "save_path" in text
        assert "modal" in text

    async def test_unsaved_with_path_saves(self, presentation_tools, mock_subprocess_run, tmp_path):
        target = tmp_path / "deck"
        mock_subprocess_run.return_value.stdout = f"SAVED|deck.key|{target}.key"
        result = await presentation_tools.save_presentation(save_path=str(target))
        assert last_cmd(mock_subprocess_run)[3] == f"{target}.key"
        assert result[0].text == f"Saved presentation: deck.key ({target}.key)"

    async def test_repathing_saved_document_is_refused(
        self, presentation_tools, mock_subprocess_run, tmp_path
    ):
        mock_subprocess_run.return_value.stdout = "ALREADY_SAVED|/somewhere/deck.key"
        result = await presentation_tools.save_presentation(save_path=str(tmp_path / "new.key"))
        text = result[0].text
        assert text.startswith("Failed to save presentation")
        assert "already saved" in text

    async def test_script_checks_file_before_saving(self, presentation_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "SAVED|d|/p.key"
        await presentation_tools.save_presentation()
        script = mock_subprocess_run.call_args.kwargs["input"]
        assert "file of targetDoc" in script
        assert "UNSAVED_NO_PATH" in script


class TestOpenPresentation:
    async def test_missing_file_fails_without_subprocess(
        self, presentation_tools, mock_subprocess_run, tmp_path
    ):
        result = await presentation_tools.open_presentation(str(tmp_path / "nope.key"))
        assert "does not exist" in result[0].text
        assert not mock_subprocess_run.called

    async def test_opens_via_launchservices_not_applescript_open(
        self, presentation_tools, mock_subprocess_run, tmp_path
    ):
        deck = tmp_path / "deck.key"
        deck.write_bytes(b"stub")

        def fake_run(cmd, **kwargs):
            if cmd[0] == "/usr/bin/open":
                assert cmd[1:3] == ["-a", "Keynote"]
                assert cmd[3] == str(deck)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "deck.key", "")

        mock_subprocess_run.side_effect = fake_run
        result = await presentation_tools.open_presentation(str(deck))
        assert result[0].text.startswith("Opened presentation: deck.key")
        # The opened document becomes the session default, and says so.
        assert "session document" in result[0].text
        assert SESSION.get_default() == "deck.key"
        opens = [c for c in mock_subprocess_run.call_args_list if c.args[0][0] == "/usr/bin/open"]
        assert len(opens) == 1
        for c in mock_subprocess_run.call_args_list:
            script = c.kwargs.get("input", "")
            assert "open (POSIX file" not in script

    async def test_poll_timeout_gives_actionable_error(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("keynote_mcp.tools.presentation._OPEN_POLL_DEADLINE", 0.0)
        monkeypatch.setattr("keynote_mcp.tools.presentation._OPEN_POLL_INTERVAL", 0.0)
        deck = tmp_path / "deck.key"
        deck.write_bytes(b"stub")

        def fake_run(cmd, **kwargs):
            if cmd[0] == "/usr/bin/open":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_subprocess_run.side_effect = fake_run
        result = await presentation_tools.open_presentation(str(deck))
        assert "Failed to open presentation" in result[0].text
        assert "did not report a document" in result[0].text

    async def test_launchservices_failure_reported(
        self, presentation_tools, mock_subprocess_run, tmp_path
    ):
        deck = tmp_path / "deck.key"
        deck.write_bytes(b"stub")

        def fake_run(cmd, **kwargs):
            if cmd[0] == "/usr/bin/open":
                return subprocess.CompletedProcess(cmd, 1, "", "no application to open")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_subprocess_run.side_effect = fake_run
        result = await presentation_tools.open_presentation(str(deck))
        assert "Failed to open presentation" in result[0].text
        assert "LaunchServices" in result[0].text


class TestWedgeDetection:
    def test_timeout_with_dead_probe_reports_wedge(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(["osascript"], 30)
        with pytest.raises(AppleScriptError) as exc:
            AppleScriptRunner().run("return 1")
        assert "wedged" in str(exc.value)
        assert "killall Keynote" in str(exc.value)
        assert AppleScriptRunner._queue_wedged is True

    def test_wedged_state_fails_fast_without_running_script(self, mock_subprocess_run):
        AppleScriptRunner._queue_wedged = True
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(["pgrep"], 3)
        with pytest.raises(AppleScriptError) as exc:
            AppleScriptRunner().run("return 1")
        assert "wedged" in str(exc.value)
        # only the probe ran; the 30s script was never attempted
        for c in mock_subprocess_run.call_args_list:
            assert "input" not in c.kwargs

    def test_wedged_state_clears_when_probe_recovers(self, mock_subprocess_run):
        AppleScriptRunner._queue_wedged = True

        def fake_run(cmd, **kwargs):
            if cmd[0] == "/usr/bin/pgrep":
                # Keynote no longer running: queue cannot be wedged
                return subprocess.CompletedProcess(cmd, 1, "", "")
            return subprocess.CompletedProcess(cmd, 0, "ok", "")

        mock_subprocess_run.side_effect = fake_run
        assert AppleScriptRunner().run("return 1") == "ok"
        assert AppleScriptRunner._queue_wedged is False

    def test_timeout_with_healthy_probe_keeps_modal_message(self, mock_subprocess_run):
        def fake_run(cmd, **kwargs):
            if cmd[0] == "/usr/bin/pgrep":
                return subprocess.CompletedProcess(cmd, 1, "", "")
            raise subprocess.TimeoutExpired(cmd, 30)

        mock_subprocess_run.side_effect = fake_run
        with pytest.raises(AppleScriptError) as exc:
            AppleScriptRunner().run("return 1")
        assert "modal dialog" in str(exc.value)
        assert AppleScriptRunner._queue_wedged is False
