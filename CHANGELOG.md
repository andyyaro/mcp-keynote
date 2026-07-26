# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-07-26

This fork ([andyyaro/mcp-keynote](https://github.com/andyyaro/mcp-keynote))
diverges from [ByAxe/keynote-mcp](https://github.com/ByAxe/keynote-mcp)
(itself a fork of [easychen/keynote-mcp](https://github.com/easychen/keynote-mcp)).
Every tool was validated against the Keynote 14.5 scripting dictionary and
executed against a live Keynote; see `docs/TOOL_MATRIX.md` and
`docs/MODERNIZATION_REPORT.md`.

### Changed — breaking

- **AppleScript injection closed.** All user strings now reach `osascript`
  as argv (`on run argv`), never interpolated into script source. A slide
  title containing `"` or `\` can no longer alter the script.
- **stdout is protocol-pure.** All logging goes to stderr, controlled by
  `KEYNOTE_MCP_LOG_LEVEL`; stray `print()`s and the banner-printing
  `start_server.py` launcher are gone. Run with `keynote-mcp`,
  `python -m keynote_mcp`, or `uv run keynote-mcp`.
- **Packaging.** PEP 621 `pyproject.toml` with the `uv_build` backend is the
  single source of truth; `setup.py` and `requirements*.txt` deleted;
  `uv.lock` committed; `requires-python >= 3.11`; `mcp` pinned `>=1.28,<2`
  (v2 migration inventory in `docs/MCP_V2_MIGRATION.md`).
- **`create_presentation`** no longer silently saves to `~/Desktop`; pass
  the new optional `save_path` to save. The unused `template` argument was
  removed.
- **`get_presentation_resolution` removed** — exact duplicate of
  `get_slide_size`.
- **`add_image`** no longer falls back to inserting a `movie` or pasting via
  the clipboard (which clobbered the user's clipboard).

### Added

- **`set_slide_content`** — writes the theme's title/body placeholders
  (`default title item` / `default body item`) for theme-consistent styling.
- **Font-clipping workaround absorbed**: fonts > 48pt auto-size their text
  box and restore truncated text server-side; the manual
  resize-then-edit dance from the skill is no longer needed. `add_text_box`
  gained `width`/`height`; `add_title`/`add_subtitle` gained `color`.
- **Actionable errors**: -1743 names the Automation pane, assistive-access
  errors name the Accessibility pane, -1728/-1719 suggest the introspection
  tools, timeouts point at modal dialogs. Every osascript call has a bounded
  timeout (default 30 s, `KEYNOTE_MCP_TIMEOUT` override).
- **Tests**: 270 unit tests (95% line coverage, no GUI) + a
  `pytest -m keynote` integration tier against a real Keynote, deselected by
  default. CI (macos-latest) runs ruff, mypy --strict, and unit tests on
  Python 3.11/3.12/3.13.

### Fixed

- Out-of-range `delete_slide`/`delete_element` used to silently succeed
  (Keynote no-ops them); both now verify existence and report the error.
- `screenshot_slide` restores each slide's original skipped state instead of
  un-skipping every slide.
- Build-animation tools target `window 1` of the Keynote process (window
  titles don't reliably match document names) and select the slide in a
  separate osascript call, fixing intermittent -2700/-1728 popover failures.
- Keynote 14.5 reports invalid indices as error -1719; it is now mapped to
  the object-not-found guidance instead of being misread as an Accessibility
  problem.

### Removed

- Dead `.applescript` script library and the `.scpt` loader (all tools emit
  inline argv-based scripts).
- Unused dependencies: Pillow, typing-extensions, python-dotenv (environment
  comes from the MCP client config).

## [1.0.1] - 2025

Upstream ByAxe release: PyPI packaging, keynote-presentation skill, build
animation tools, English translation of the original easychen project.

## [1.0.0]

First upstream release (easychen/keynote-mcp).
