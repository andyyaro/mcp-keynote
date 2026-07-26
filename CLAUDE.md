# CLAUDE.md — keynote-mcp

## What this is

An MCP (Model Context Protocol) server that controls Apple Keynote via
AppleScript. It exposes 45 tools for creating presentations, managing slides,
adding content (text, images, lists, code blocks, theme placeholders),
build animations, exporting, and fetching images from Unsplash (opt-in).

## How to run

```bash
uv --directory /path/to/mcp-keynote run keynote-mcp
```

Registered in Claude Code as:
```bash
claude mcp add keynote-mcp -- uv --directory ~/Downloads/mcp-keynote run keynote-mcp
```

**After any code change, restart the MCP server** (exit/re-enter the Claude
Code session or use `/mcp`) — the running server keeps the old code.

## Project structure

```
src/keynote_mcp/
  __init__.py            — Package version
  __main__.py            — python -m keynote_mcp entry point
  server.py              — MCP stdio server: logging config, handler
                           registration, one _dispatch for all tool calls
  tools/
    presentation.py      — create/open/save/close/list, themes, slide size
    slide.py             — add/delete/duplicate/move/select slides, layouts
    content.py           — text boxes/titles/lists/code/quotes (font, color,
                           auto-sized boxes for large fonts), theme
                           placeholders (set_slide_content), images, shapes,
                           edit/move/resize/delete elements, speaker notes,
                           clear_slide, build animations (UI scripting)
    export.py            — screenshot_slide, export_pdf
    unsplash.py          — Unsplash REST tools (need UNSPLASH_KEY)
  utils/
    applescript_runner.py — runs '/usr/bin/osascript -' with user strings as
                            argv; bounded timeouts
    error_handler.py      — exception hierarchy, validators, stderr→actionable
                            error mapping (-1743/-1728/-1719/-600/-1712)
tests/
  unit/                  — no GUI, no Keynote; runs in CI (95% coverage)
  integration/           — @pytest.mark.keynote; drives a real Keynote
docs/                    — ENVIRONMENT.md (verified host facts),
                           TOOL_MATRIX.md (per-tool verification),
                           MCP_V2_MIGRATION.md, MODERNIZATION_REPORT.md
skills/keynote-presentation/ — Claude Skill (install: cp -r to ~/.claude/skills/)
```

## Architecture and key invariants

1. **Injection safety is the core invariant.** User strings are passed to
   `osascript` as argv consumed by `on run argv` — NEVER f-string user text
   into AppleScript source. Numbers may be interpolated only after strict
   validation (`validate_slide_number`, `validate_index`, `validate_number`,
   `parse_color`). `tests/unit/test_injection.py` enforces this; keep it
   passing for any new tool.
2. **stdout carries framed JSON-RPC only.** No `print()` anywhere in `src/`
   (a unit test greps for it). Logging goes to stderr; level via
   `KEYNOTE_MCP_LOG_LEVEL`.
3. **Every osascript call has a bounded timeout** (default 30 s,
   `KEYNOTE_MCP_TIMEOUT` override; UI scripting 60 s; exports 120 s) so a
   modal Keynote dialog can't hang the server.
4. **Tool handlers never raise.** Each method returns `[TextContent]`, with
   failures as "Failed to …" text; `server.call_tool` is the last-resort
   guard. A garbage tool call must leave the server serving (tested).
5. **Tool schemas** live inline in each `get_tools()`. New tool = schema in
   `get_tools()` + method + routing case in `server._dispatch()` + a row in
   `docs/TOOL_MATRIX.md` (verify against `docs/keynote-14.5.sdef` and a real
   Keynote first).

## Keynote facts learned by verification (don't re-litigate)

- The sdef is the spec: `sdef /Applications/Keynote.app` (or copy
  `Contents/Resources/Keynote.sdef`). `base slide`/`master slide` are
  official synonyms of `base layout`/`slide layout`.
- Shape/text fill color is NOT writable via AppleScript (`background fill
  type` is read-only). The opacity workaround is the only option.
- Keynote **silently no-ops** deleting a nonexistent slide/element — the
  delete tools check `exists …` first and raise -1719.
- Invalid indices surface as error **-1719** ("Invalid index"), not -1728.
- Window titles don't reliably match document names — UI scripting targets
  `window 1` of the Keynote process.
- Fonts > 48pt land in a tiny auto-sized box that truncates text; the server
  absorbs this (auto-size box before setting size, re-set text after).
- `move slide X to slide Y` REPLACES slide Y — always `before/after slide Y`.
- Build animations, build order, "With Previous" timing, and connection-line
  routing have no AppleScript API; builds use System Events UI scripting
  (Accessibility permission), the rest is manual-only.

## Development

```bash
uv sync --dev          # set up venv from uv.lock
make test              # unit tests (safe anywhere)
make test-integration  # REAL Keynote: steals window focus, needs TCC grants
make check             # CI parity: ruff + ruff format + mypy --strict + coverage gate
make format            # auto-fix + format
```

Integration tests are deselected by default (`addopts = -m 'not keynote'`).
They create scratch documents under `.scratch/` only, close without saving,
and quit Keynote only if they started it. Warn the user before running them:
UI-scripting tests take over window focus and keystrokes.

## Common pitfalls

- Code changes don't apply until the MCP server restarts.
- TCC permissions attach to the app that launched the server (terminal/IDE),
  not to Python. `./preflight-permissions.sh` walks all grants.
- `add_build_in` needs Keynote frontmost and an unlocked screen.
- Check original property values (`get_slide_content`) before modifying
  existing presentations; don't assume defaults.
