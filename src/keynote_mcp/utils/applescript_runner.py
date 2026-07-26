"""AppleScript execution for Keynote-MCP.

All user-controlled strings are passed to osascript as argv (``osascript -
arg1 arg2 …`` with an ``on run argv`` handler in the script), never
interpolated into AppleScript source. Numeric values may be interpolated by
callers only after strict validation.
"""

import logging
import os
import subprocess

from .error_handler import AppleScriptError, handle_applescript_error

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


def _env_timeout() -> float:
    raw = os.environ.get("KEYNOTE_MCP_TIMEOUT", "")
    try:
        value = float(raw)
        return value if value > 0 else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


class AppleScriptRunner:
    """Runs AppleScript through osascript with bounded timeouts."""

    def __init__(self, timeout: float | None = None):
        self.timeout = timeout if timeout is not None else _env_timeout()

    def run(self, script: str, *argv: str, timeout: float | None = None) -> str:
        """Execute AppleScript source, passing ``argv`` as run-handler arguments.

        Scripts that receive arguments must declare ``on run argv``. Arguments
        reach the script uninterpreted, so quotes/backslashes/newlines in user
        input cannot alter the script.
        """
        args = [str(a) for a in argv]
        effective_timeout = timeout if timeout is not None else self.timeout
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable, script via stdin
                ["osascript", "-", *args],
                input=script,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            raise AppleScriptError(
                f"osascript timed out after {effective_timeout:.0f}s. A modal dialog in "
                "Keynote (save sheet, 'What's New' window, missing-font alert) may be "
                "blocking automation - switch to Keynote and dismiss any open dialog."
            ) from None
        except OSError as e:
            raise AppleScriptError(f"Failed to execute osascript: {e}") from e

        if result.returncode != 0:
            handle_applescript_error(result.stderr)
            # handle_applescript_error always raises for non-empty stderr;
            # guard against an empty stderr with a non-zero exit.
            raise AppleScriptError(
                f"osascript exited with status {result.returncode} and no error output"
            )
        return result.stdout.strip()

    # Backwards-compatible name used throughout the tool classes for scripts
    # that take no user-controlled strings.
    def run_inline_script(self, script_code: str, timeout: float | None = None) -> str:
        return self.run(script_code, timeout=timeout)

    def check_keynote_running(self) -> bool:
        """Check if Keynote is running (via System Events)."""
        script = """
        tell application "System Events"
            return (name of processes) contains "Keynote"
        end tell
        """
        try:
            return self.run(script).lower() == "true"
        except AppleScriptError:
            return False

    def launch_keynote(self) -> None:
        """Launch the Keynote application."""
        self.run('tell application "Keynote" to activate')

    def quit_keynote(self) -> None:
        """Quit the Keynote application."""
        self.run('tell application "Keynote" to quit')

    def get_keynote_version(self) -> str:
        """Get the Keynote version."""
        return self.run('tell application "Keynote" to return version')
