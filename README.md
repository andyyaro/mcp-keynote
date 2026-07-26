# Keynote MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage 95%](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)](#development)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)

An MCP server that gives AI full control over Apple Keynote through AppleScript
automation. Build entire decks from one declarative spec — native tables and
charts, transitions, styles, speaker notes — and export to PDF, PPTX, movie,
or HTML. All via natural language.

This is a modernized fork of
[ByAxe/keynote-mcp](https://github.com/ByAxe/keynote-mcp) (itself a fork of
[easychen/keynote-mcp](https://github.com/easychen/keynote-mcp)). Every tool
was validated against the Keynote 14.5 scripting dictionary and executed
against a real Keynote — 196 live checks, 0 failed
([docs/TOOL_MATRIX.md](docs/TOOL_MATRIX.md)). Checks on anything visual
assert the rendered pixels or the exported file's contents, not just a count
that came back. The scripting dictionary's
full surface was mapped and probed
([docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)); what Keynote
genuinely cannot be told to do is documented in
[docs/CEILING.md](docs/CEILING.md). User input reaches AppleScript via
`osascript` argv, never string interpolation, so titles containing quotes,
backslashes, emoji, or CJK can't break (or hijack) the script.

## Quick Start

### Prerequisites

- macOS with Keynote installed
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

### Register with Claude Code

```bash
git clone https://github.com/andyyaro/mcp-keynote.git /path/to/mcp-keynote
claude mcp add keynote-mcp -- uv --directory /path/to/mcp-keynote run keynote-mcp
```

That exact command is verified end-to-end: it starts the server, lists the
tools, and executes them. Check health with `claude mcp list`.

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "keynote-mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-keynote", "run", "keynote-mcp"],
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
"Build the whole deck from this outline, boardroom style, with a revenue
 chart on slide 3 and speaker notes"
"Add a native table with the headcount numbers and a SUM row"
"Export the presentation as PPTX"
```

For multi-slide decks the model should reach for `build_deck` (one call for
the whole deck) rather than element-by-element tools; `describe_deck` reads
any open deck back as JSON for diffing or round-tripping.

Measured on a 20-slide deck: **81 primitive calls (21.8 s) versus 1 call
(11.9 s)**. The point is the call count, not the clock — both paths drive the
same Keynote GUI one AppleScript event at a time, so the wall-clock gain is
modest. What one call buys you is 81 fewer round trips, 81 fewer places for a
returned index or a coordinate to go wrong, whole-spec validation before
anything is created, and a deck described as content rather than as
coordinates.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Error mentions **-1743** / "Not authorized to send Apple events" | Automation permission missing | System Settings → Privacy & Security → **Automation** → your terminal/IDE → enable Keynote. If the prompt never appears, `tccutil reset AppleEvents <terminal-bundle-id>` and retry |
| Error mentions **-1728** or **-1719** / "Invalid index" | The referenced slide/element/document doesn't exist | Check with `get_slide_count`, `get_slide_content`, or `list_presentations` — indices are 1-based |
| "not allowed assistive access" | Accessibility permission missing (build tools only) | System Settings → Privacy & Security → **Accessibility** → enable your terminal/IDE, then restart it |
| "osascript timed out after 30s" | A modal Keynote dialog (save sheet, "What's New", missing font) is blocking automation | Switch to Keynote and dismiss the dialog; raise `KEYNOTE_MCP_TIMEOUT` for huge decks |
| Unsplash tools missing from tools/list | `UNSPLASH_KEY` not set | Set it in the MCP client config (opt-in feature) |
| Build animations fail intermittently | Keynote must be frontmost; UI scripting is timing-sensitive | Retry once; keep Keynote visible and the screen unlocked while builds run |

## Available Tools (59)

| Category | Tools |
|----------|-------|
| **Deck building** (2) | `build_deck` — an entire deck from one JSON spec or a markdown dialect (validated up front, per-element error isolation, one AppleScript session per ~5 slides, settled geometry reported, two-column auto-flow, styles); `describe_deck` — read a deck back into the same spec (diffable in git) |
| **Presentation** (11) | create, open, save, close, list, set/get theme, info, slide size (get + live resize), document settings (slide numbers, autoplay/loop/restart) |
| **Slides** (11) | add, delete, duplicate, move, select, count, layouts, slide info, transitions (all 43 effects), skip/unskip |
| **Content** (22) | text boxes / titles / subtitles (font, color, size — exact placement, server-side centering), bullet & numbered lists, code blocks, quotes, theme placeholders (`set_slide_content`), images (with size + alt text), shapes with opacity, edit/move/resize/delete elements, speaker notes, clear slide, build-in animations |
| **Native objects** (7) | tables (data, live `=SUM(…)` formulas, styled headers, column widths), charts (17 native types — bar/line/area/pie/scatter/stacked/3-D), lines, colored panels (rendered PNG — see below), per-range text styling (bold/color a word inside a box), replace image in place, rotation/reflection/lock |
| **Export** (4) | screenshot slide, PDF (slides / with-notes / handouts + quality), PPTX / QuickTime movie / HTML / per-slide images / Keynote 09 |
| **Unsplash** (3, opt-in) | search, add to slide, random image (requires `UNSPLASH_KEY`) |

Full per-tool verification status: [docs/TOOL_MATRIX.md](docs/TOOL_MATRIX.md).

### Styles

A deck-wide style — fonts, palette, margins, table header colors — comes
from a built-in (`plain`, `boardroom`, `midnight`, `editorial`), a
`.keynote-mcp.toml` next to the deck, or a TOML path passed as `style`.
`build_deck`, `add_table`, and `add_colored_panel` consult it, so decks stay
visually consistent without per-call coordinates and font names.

### Known Keynote limits

Not fixable via AppleScript — verified by live probes, documented with
workarounds in [docs/CEILING.md](docs/CEILING.md): shape fill color is
read-only (colored panels are therefore *rendered images*, not recolorable
in Keynote), text alignment exists only inside tables, no hyperlinks, no
grouping, no z-order control (creation order is paint order), no
movie/audio insertion, chart data is write-once, tables are 2×2 minimum,
and build-order/"With Previous"/connection-line routing require the
Keynote UI.

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
  tools/          # presentation, slide, content, objects (native tables/
                  # charts), deck (build_deck/describe_deck), fragments
                  # (shared AppleScript builders), export, unsplash
  utils/          # osascript runner (argv-based), error mapping, validation,
                  # styles (.keynote-mcp.toml), PNG panel rendering
skills/           # keynote-presentation Claude Skill
docs/             # ENVIRONMENT, TOOL_MATRIX, CAPABILITY_MATRIX, CEILING,
                  # MCP_V2_MIGRATION, MODERNIZATION_REPORT
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
