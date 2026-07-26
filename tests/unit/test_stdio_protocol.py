"""Protocol hygiene: stdout carries framed JSON-RPC only, and the server
survives garbage tool calls.

These tests spawn the real server as a subprocess and speak MCP stdio
(newline-delimited JSON-RPC). No Keynote interaction: the garbage calls fail
parameter validation before any osascript runs.
"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from mcp.types import LATEST_PROTOCOL_VERSION

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "keynote_mcp"

READ_TIMEOUT = 15.0


class ServerProcess:
    """Minimal newline-delimited JSON-RPC client over a server subprocess."""

    def __init__(self):
        env = os.environ.copy()
        env.pop("UNSPLASH_KEY", None)
        env["KEYNOTE_MCP_LOG_LEVEL"] = "DEBUG"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "keynote_mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)

    def send(self, message: dict):
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()

    def recv_raw(self) -> bytes:
        try:
            return self._lines.get(timeout=READ_TIMEOUT)
        except queue.Empty:
            pytest.fail("Timed out waiting for a JSON-RPC response on stdout")

    def recv(self) -> dict:
        return json.loads(self.recv_raw())

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=10)


@pytest.fixture
def server():
    server = ServerProcess()
    yield server
    server.close()


def _initialize(server: ServerProcess) -> bytes:
    server.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        }
    )
    first = server.recv_raw()
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return first


def test_first_stdout_bytes_are_framed_jsonrpc(server):
    """The very first bytes on stdout must be a valid JSON-RPC initialize
    response - no banners, no prints, no log lines."""
    first = _initialize(server)
    assert first.lstrip()[:1] == b"{", f"stdout began with non-JSON bytes: {first[:80]!r}"
    message = json.loads(first)
    assert message["jsonrpc"] == "2.0"
    assert message["id"] == 1
    assert "result" in message
    assert message["result"]["serverInfo"]["name"] == "keynote-mcp"


def test_garbage_tool_call_returns_error_and_server_survives(server):
    """A tool call with garbage arguments returns a structured error, and the
    server still answers a subsequent tools/list."""
    _initialize(server)

    server.send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "delete_slide", "arguments": {}},
        }
    )
    response = server.recv()
    assert response["id"] == 2
    assert "result" in response, f"expected a result, got: {response}"
    text = response["result"]["content"][0]["text"]
    assert "slide_number" in text or "error" in text.lower()

    # Wrong-typed argument as well
    server.send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "delete_slide", "arguments": {"slide_number": -42}},
        }
    )
    response = server.recv()
    assert response["id"] == 3
    assert "result" in response
    assert "Invalid slide number" in response["result"]["content"][0]["text"]

    # Unknown tool name
    server.send(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
        }
    )
    response = server.recv()
    assert response["id"] == 4

    # The server must still be alive and serving
    server.send({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
    response = server.recv()
    assert response["id"] == 5
    tools = response["result"]["tools"]
    assert len(tools) >= 30
    assert server.proc.poll() is None, "server process died"


def test_tools_list_schemas_are_objects(server):
    """Every advertised tool has an object inputSchema with properties."""
    _initialize(server)
    server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    response = server.recv()
    for tool in response["result"]["tools"]:
        schema = tool["inputSchema"]
        assert schema["type"] == "object", f"{tool['name']} schema is not an object"
        assert "properties" in schema, f"{tool['name']} schema has no properties"


def test_no_tty_reads_in_source():
    """The server must never block on input() or direct TTY reads."""
    offenders = []
    for path in SRC_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "input(" in text.replace("run_inline", "") or "getpass" in text:
            offenders.append(path.name)
    assert not offenders, f"possible TTY reads in: {offenders}"


def test_no_print_calls_in_source():
    """print() writes to stdout and corrupts the JSON-RPC stream."""
    offenders = []
    for path in SRC_DIR.rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "print(" in stripped:
                offenders.append(f"{path.name}:{i}")
    assert not offenders, f"stray print() calls: {offenders}"
