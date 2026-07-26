"""AppleScript execution for Keynote-MCP.

All user-controlled strings are passed to osascript as argv (``osascript -
arg1 arg2 …`` with an ``on run argv`` handler in the script), never
interpolated into AppleScript source. Numeric values may be interpolated by
callers only after strict validation.
"""

import logging
import os
import subprocess

from .error_handler import AppleScriptError, FileOperationError, handle_applescript_error

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0

# A wedged AppleEvent queue (e.g. after an AppleScript `open` of a file
# outside Keynote's sandbox container, or an unanswered modal sheet) makes
# EVERY Apple event hang. The probe must answer well inside this bound if the
# queue is healthy.
PROBE_TIMEOUT = 3.0

_WEDGE_RECOVERY = (
    "Keynote's AppleEvent queue appears wedged: a trivial probe event timed "
    "out, so every Apple event will hang until Keynote restarts. Recovery: "
    "force-quit Keynote (`killall Keynote` - the scripted quit is itself an "
    "Apple event and would hang), reopen it, then reload documents with "
    "open_presentation. This state usually follows a blocked modal dialog or "
    "an attempt to open a file outside Keynote's sandbox container."
)


def _env_timeout() -> float:
    raw = os.environ.get("KEYNOTE_MCP_TIMEOUT", "")
    try:
        value = float(raw)
        return value if value > 0 else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


class AppleScriptRunner:
    """Runs AppleScript through osascript with bounded timeouts."""

    # Shared across instances: once one call discovers the wedge, every other
    # tool class fails fast instead of burning its full timeout.
    _queue_wedged = False

    def __init__(self, timeout: float | None = None):
        self.timeout = timeout if timeout is not None else _env_timeout()

    def _probe_queue_ok(self) -> bool:
        """Cheap health check of Keynote's AppleEvent queue.

        Returns True when Keynote is not running (nothing to wedge) or when it
        answers a trivial Apple event within PROBE_TIMEOUT; False when the
        probe itself hangs - the signature of a wedged queue.
        """
        try:
            running = subprocess.run(
                ["/usr/bin/pgrep", "-x", "Keynote"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if running.returncode != 0:
                return True
            subprocess.run(
                ["/usr/bin/osascript", "-e", 'tell application "Keynote" to count documents'],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT,
            )
            return True
        except subprocess.TimeoutExpired:
            return False
        except OSError:
            # Can't run the probe at all; don't mask the original failure.
            return True

    def run(self, script: str, *argv: str, timeout: float | None = None) -> str:
        """Execute AppleScript source, passing ``argv`` as run-handler arguments.

        Scripts that receive arguments must declare ``on run argv``. Arguments
        reach the script uninterpreted, so quotes/backslashes/newlines in user
        input cannot alter the script.
        """
        if AppleScriptRunner._queue_wedged:
            if self._probe_queue_ok():
                AppleScriptRunner._queue_wedged = False
            else:
                raise AppleScriptError(_WEDGE_RECOVERY)

        args = [str(a) for a in argv]
        effective_timeout = timeout if timeout is not None else self.timeout
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable, script via stdin
                ["/usr/bin/osascript", "-", *args],
                input=script,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            if not self._probe_queue_ok():
                AppleScriptRunner._queue_wedged = True
                raise AppleScriptError(
                    f"osascript timed out after {effective_timeout:.0f}s. {_WEDGE_RECOVERY}"
                ) from None
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

    def open_in_keynote(self, file_path: str) -> None:
        """Open a file in Keynote via LaunchServices, like a double-click.

        LaunchServices grants Keynote a per-file sandbox extension; a direct
        AppleScript ``open`` of a file outside Keynote's sandbox container
        wedges the whole AppleEvent queue (zero windows, every later event
        timing out), so that path must never be used.
        """
        try:
            result = subprocess.run(  # noqa: S603 - fixed executable, validated path
                ["/usr/bin/open", "-a", "Keynote", file_path],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
        except subprocess.TimeoutExpired:
            raise FileOperationError(f"LaunchServices timed out opening {file_path}") from None
        except OSError as e:
            raise FileOperationError(f"Failed to run /usr/bin/open: {e}") from e
        if result.returncode != 0:
            raise FileOperationError(
                f"LaunchServices could not open {file_path}: "
                f"{result.stderr.strip() or 'unknown error'}"
            )

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
