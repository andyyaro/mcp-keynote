# Keynote MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage 95%](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)](#development)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)

An MCP server that gives AI full control over Apple Keynote through AppleScript
automation. Create, edit, and export presentations — all via natural language.

This is a modernized fork of
[ByAxe/keynote-mcp](https://github.com/ByAxe/keynote-mcp) (itself a fork of
[easychen/keynote-mcp](https://github.com/easychen/keynote-mcp)). Every tool
in this fork was validated against the Keynote 14.5 scripting dictionary and
executed against a real Keynote — see [docs/TOOL_MATRIX.md](docs/TOOL_MATRIX.md).
User input reaches AppleScript via `osascript` argv, never string
interpolation, so titles containing quotes, backslashes, emoji, or CJK can't
break (or hijack) the script.

## Quick Start

### Prerequisites

- macOS with Keynote installed
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

### Register with Claude Code

```bash
git clone https://github.com/andyyaro/mcp-keynote.git ~/Downloads/mcp-keynote
claude mcp add keynote-mcp -- uv --directory ~/Downloads/mcp-keynote run keynote-mcp
```

That exact command is verified end-to-end: it starts the server, lists the
tools, and executes them. Check health with `claude mcp list`.

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "keynote-mcp": {
      "command": "uv",
      "args": ["--directory", "/Users/you/Downloads/mcp-keynote", "run", "keynote-mcp"],
      "env": { "UNSPLASH_KEY": "optional_key_here" }
    }
  }
}
```

**Other MCP clients:** command `uv --directory <repo> run keynote-mcp`,
transport stdio.

### macOS permissions (TCC)

macOS attributes permissions to the app that *launches* the server — your
terminal or IDE, not Python. Grant, in **System Settings → Privacy &
Security**:

1. **Automation** → your terminal/IDE → enable **Keynote** (all tools) and
   **System Events** (build animations). The prompt appears on first use.
2. **Accessibility** → add and enable your terminal/IDE. Only needed for the
   build-animation tools (`add_build_in`, `remove_build_in`,
   `add_builds_to_slide`).

`./preflight-permissions.sh` walks every grant interactively and verifies
each one. Restart the terminal after granting — grants apply to processes
started afterwards.

### Install the Skill (recommended)

The `keynote-presentation` skill teaches Claude layout math, theme
compatibility, and design patterns:

```bash
cp -r skills/keynote-presentation ~/.claude/skills/keynote-presentation
```

For Claude.ai: zip `skills/keynote-presentation`, then Settings →
Capabilities → Skills → Upload skill.

### Use it

```
"Create a presentation about our Q1 results with 6 slides"
"Add a slide with a code example showing the API"
"Export the presentation as PDF"
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Error mentions **-1743** / "Not authorized to send Apple events" | Automation permission missing | System Settings → Privacy & Security → **Automation** → your terminal/IDE → enable Keynote. If the prompt never appears, `tccutil reset AppleEvents <terminal-bundle-id>` and retry |
| Error mentions **-1728** or **-1719** / "Invalid index" | The referenced slide/element/document doesn't exist | Check with `get_slide_count`, `get_slide_content`, or `list_presentations` — indices are 1-based |
| "not allowed assistive access" | Accessibility permission missing (build tools only) | System Settings → Privacy & Security → **Accessibility** → enable your terminal/IDE, then restart it |
| "osascript timed out after 30s" | A modal Keynote dialog (save sheet, "What's New", missing font) is blocking automation | Switch to Keynote and dismiss the dialog; raise `KEYNOTE_MCP_TIMEOUT` for huge decks |
| Unsplash tools missing from tools/list | `UNSPLASH_KEY` not set | Set it in the MCP client config (opt-in feature) |
| Build animations fail intermittently | Keynote must be frontmost; UI scripting is timing-sensitive | Retry once; keep Keynote visible and the screen unlocked while builds run |

## Available Tools (45)

| Category | Tools |
|----------|-------|
| **Presentation** (9) | create, open, save, close, list, set/get theme, info, slide size |
| **Slides** (9) | add, delete, duplicate, move, select, count, layouts, slide info |
| **Content** (22) | text boxes / titles / subtitles (font, color, size — large fonts auto-sized, no clipping), bullet & numbered lists, code blocks, quotes, theme placeholders (`set_slide_content`), images, shapes with opacity, edit/move/resize/delete elements, speaker notes, clear slide, build-in animations |
| **Export** (2) | screenshot slide, export PDF |
| **Unsplash** (3, opt-in) | search, add to slide, random image (requires `UNSPLASH_KEY`) |

Full per-tool verification status: [docs/TOOL_MATRIX.md](docs/TOOL_MATRIX.md).

Known Keynote limits (not fixable via AppleScript): shape fill color is
read-only (use the opacity workaround), connection-line routing, build-order
reordering, and "With Previous" timing require the Keynote UI.

## Environment variables

| Variable | Effect |
|----------|--------|
| `KEYNOTE_MCP_LOG_LEVEL` | Log level on stderr (`DEBUG`, `INFO`, …; default `INFO`) |
| `KEYNOTE_MCP_TIMEOUT` | Per-call osascript timeout in seconds (default 30) |
| `UNSPLASH_KEY` | Enables the Unsplash tools ([get a key](https://unsplash.com/developers)) |

## Development

```bash
uv sync --dev        # install
make test            # unit tests - no Keynote needed (95% coverage)
make test-integration # runs against a REAL Keynote; steals window focus
make check           # everything CI runs: ruff, mypy --strict, tests + coverage gate
```

Tests come in two tiers: `tests/unit/` runs anywhere (CI runs it on
macos-latest for Python 3.11–3.13); `tests/integration/` is marked
`keynote`, deselected by default, and drives a real Keynote locally.

```
src/keynote_mcp/
  server.py       # MCP stdio server, tool routing
  tools/          # presentation, slide, content, export, unsplash
  utils/          # osascript runner (argv-based), error mapping, validation
skills/           # keynote-presentation Claude Skill
docs/             # ENVIRONMENT, TOOL_MATRIX, MCP_V2_MIGRATION, MODERNIZATION_REPORT
```

## Standalone Binary

Accessibility permission is granted per-binary, so granting it to `python`
shares it with every Python process. For stricter isolation, build a
standalone binary that gets its own permission entry:

```bash
uv run --with pyinstaller pyinstaller --onefile --name keynote-mcp src/keynote_mcp/__main__.py
codesign -s - -f dist/keynote-mcp
```

Then point your MCP config at `/absolute/path/to/dist/keynote-mcp`.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- Original project by [easychen](https://github.com/easychen/keynote-mcp)
- Upstream fork, PyPI packaging, and the keynote-presentation skill by
  [ByAxe](https://github.com/ByAxe/keynote-mcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Unsplash](https://unsplash.com/)
