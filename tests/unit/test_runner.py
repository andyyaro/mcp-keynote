"""AppleScriptRunner: bounded timeouts, argv passing, error propagation."""

import subprocess
from unittest.mock import patch

import pytest

from keynote_mcp.utils.applescript_runner import DEFAULT_TIMEOUT, AppleScriptRunner
from keynote_mcp.utils.error_handler import AppleScriptError


def test_default_timeout_is_bounded(runner, mock_subprocess_run):
    runner.run("return 1")
    assert mock_subprocess_run.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_per_call_timeout_override(runner, mock_subprocess_run):
    runner.run("return 1", timeout=90)
    assert mock_subprocess_run.call_args.kwargs["timeout"] == 90


def test_env_timeout_override(mock_subprocess_run, monkeypatch):
    monkeypatch.setenv("KEYNOTE_MCP_TIMEOUT", "12.5")
    AppleScriptRunner().run("return 1")
    assert mock_subprocess_run.call_args.kwargs["timeout"] == 12.5


def test_env_timeout_garbage_falls_back(mock_subprocess_run, monkeypatch):
    monkeypatch.setenv("KEYNOTE_MCP_TIMEOUT", "not-a-number")
    AppleScriptRunner().run("return 1")
    assert mock_subprocess_run.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_timeout_maps_to_actionable_error(runner, mock_subprocess_run):
    mock_subprocess_run.side_effect = subprocess.TimeoutExpired(["osascript"], 30)
    with pytest.raises(AppleScriptError) as exc:
        runner.run("return 1")
    assert "modal dialog" in str(exc.value)


def test_argv_are_separate_arguments(runner, mock_subprocess_run):
    runner.run("on run argv\nreturn 1\nend run", "a b", 'c"d')
    cmd = mock_subprocess_run.call_args.args[0]
    assert cmd == ["/usr/bin/osascript", "-", "a b", 'c"d']
    assert mock_subprocess_run.call_args.kwargs["input"].startswith("on run argv")


def test_nonzero_exit_with_stderr_raises_mapped_error(runner, mock_subprocess_run):
    mock_subprocess_run.return_value = subprocess.CompletedProcess(
        args=["osascript", "-"],
        returncode=1,
        stdout="",
        stderr="execution error: Not authorized to send Apple events to Keynote. (-1743)",
    )
    with pytest.raises(AppleScriptError) as exc:
        runner.run("return 1")
    assert "Automation" in str(exc.value)


def test_nonzero_exit_without_stderr_still_raises(runner, mock_subprocess_run):
    mock_subprocess_run.return_value = subprocess.CompletedProcess(
        args=["osascript", "-"], returncode=1, stdout="", stderr=""
    )
    with pytest.raises(AppleScriptError):
        runner.run("return 1")


def test_oserror_wrapped(runner, mock_subprocess_run):
    mock_subprocess_run.side_effect = OSError("no osascript")
    with pytest.raises(AppleScriptError):
        runner.run("return 1")


def test_check_keynote_running_survives_error():
    with patch(
        "keynote_mcp.utils.applescript_runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["osascript"], 30),
    ):
        assert AppleScriptRunner().check_keynote_running() is False
