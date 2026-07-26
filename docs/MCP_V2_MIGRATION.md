# MCP Python SDK v2 migration inventory

Status as of 2026-07-25: this repo pins `mcp>=1.28,<2` (resolved: 1.28.1).
SDK v2 is a pre-release (latest on PyPI: 2.0.0a3/2.0.0b2) targeting the
2026-07-28 protocol spec. We deliberately did **not** adopt it in the
modernization pass. This file is the complete inventory of every place the
codebase touches SDK surface that v2 changes, so the upgrade is a mechanical
afternoon later.

## What v2 changes (relevant to us)

1. Stateless request/response model replaces the long-lived session plumbing.
2. `FastMCP` renamed to `MCPServer` (n/a here — we use the low-level `Server`).
3. Low-level `Server` takes handlers as **constructor parameters** instead of
   registration decorators.
4. `mcp.types` models move to snake_case field names
   (e.g. `Tool.inputSchema` → `Tool.input_schema`).

## Touchpoints, file by file

### `src/keynote_mcp/server.py` (the only file that talks to the server API)

| Line(s) | Current 1.x surface | v2 change |
|---------|--------------------|-----------|
| `from mcp.server import Server` | low-level `Server` class | constructor signature changes: handlers are passed in as parameters, not registered via decorators |
| `@self.server.list_tools()` decorator + inner `list_tools()` | decorator registration | becomes a `list_tools=` (or equivalent) constructor handler param |
| `@self.server.call_tool()` decorator + inner `call_tool(name, arguments)` | decorator registration | same — constructor handler param; check the v2 handler signature (request-scoped context object in the stateless model) |
| `from mcp.server.stdio import stdio_server` + `async with stdio_server() as (read, write)` | stdio transport context manager yielding a stream pair | transport API reworked for stateless request/response; expect a run-server helper rather than raw stream pairs |
| `self.server.run(read_stream, write_stream, self.server.create_initialization_options())` | explicit run + `create_initialization_options()` | `create_initialization_options()` goes away/changes with stateless init; run entrypoint changes shape |
| `from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource` | camelCase pydantic models | snake_case field renames; `EmbeddedResource`/content union types may be reshaped for the 2026-07-28 spec |

### `src/keynote_mcp/tools/*.py` (types only — no server API)

Every tool module imports `from mcp.types import Tool, TextContent`.

| Surface | Count | v2 change |
|---------|-------|-----------|
| `Tool(name=…, description=…, inputSchema={…})` | 45 constructor calls (content 21, presentation 10, slide 9, unsplash 3, export 2) | `inputSchema=` → `input_schema=` (mechanical rename; pydantic v2 aliases may accept both — verify, don't assume) |
| `TextContent(type="text", text=…)` | 122 constructor calls across `src/` | field names already snake_case; verify the `type` discriminator survives the spec update |

### Not SDK surface (no action)

- `utils/` touches only `subprocess`/`osascript` — no SDK imports.
- Tests use the public tool classes and a subprocess-spawned server; the
  protocol-level tests (`initialize` handshake in
  `tests/unit/test_stdio_protocol.py`) hardcode `protocolVersion` — bump the
  requested protocol version string when moving to the 2026-07-28 spec.

## Suggested v2 upgrade sequence

1. Bump pin to `mcp>=2,<3`; `uv lock`.
2. Fix imports/constructor in `server.py` (one file, ~30 lines of real change).
3. `grep -rn inputSchema src/` → rename to `input_schema` (45 sites, sed-able).
4. Update `protocolVersion` in the stdio handshake test.
5. `uv run pytest` — the unit tier exercises tool schemas, dispatch, and the
   stdio handshake, so a green run is meaningful coverage of the migration.
