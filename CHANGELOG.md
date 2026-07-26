# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-07-26

Fixes for five defects surfaced by a live field test (a real 4-slide deck
build) that Phase 3's happy-path verification missed. Details in
`docs/MODERNIZATION_REPORT.md` § Field test findings; per-tool re-verification
in `docs/TOOL_MATRIX.md` (91 live checks, 0 failed).

### Changed — behavior

- **`create_presentation` always saves.** Leaving the document unsaved armed
  a trap: the first save opens a modal sheet that blocks the AppleEvent
  queue, then Keynote default-saves to iCloud as `Untitled.key`. Without
  `save_path` the document now goes to `<title>.key` in `~/Documents`
  (override the directory with `KEYNOTE_MCP_SAVE_DIR`), uniquified, and the
  response includes the resolved path. The first slide now defaults to the
  Blank layout (matching `add_slide`); `set_slide_content` remains the
  opt-in to theme placeholders and works on Blank slides.
- **`open_presentation` goes through LaunchServices** (`open -a Keynote` +
  poll). The AppleScript `open` verb wedges Keynote's AppleEvent queue for
  any file outside its sandbox container; LaunchServices grants the per-file
  sandbox extension a double-click would. Verified from `~/Downloads` and
  `~/Desktop`.
- **`save_presentation` refuses plain save on a never-saved document**
  (fast, with guidance) instead of opening the modal sheet; new `save_path`
  argument rescues unsaved documents. Re-pathing a saved document is
  refused — Keynote's AppleScript save-as hangs outside the sandbox.
- **`add_*` tools return the true element index** (located by object
  identity), the same index `get_slide_content` / `move_element` /
  `edit_text_item` consume. Previously `count of text items` over-reported
  (e.g. 6 for the element addressed as 4).
- **`get_slide_content` / `get_slide_info` no longer report phantom text
  items.** Keynote counts the hidden default title/body placeholder objects
  among "text items" (as 0x0 empties — and twice when showing); both tools
  now filter by identity. Five adds report exactly five items. `clear_slide`
  preserves placeholders by identity instead of the empty-text-at-0,0
  heuristic.
- **`screenshot_slide` reports what its export omits**: Keynote drops
  unfilled placeholder text boxes from slide-image exports, so the image is
  not a faithful editor view; the response now counts the omitted boxes.

### Added

- **`centered` parameter on `add_title`/`add_subtitle`** — server-side
  horizontal centering computed from the final box width.
- **Wedged-queue detection**: on an osascript timeout a 3-second probe
  distinguishes a modal dialog from a wedged AppleEvent queue; once wedged,
  subsequent calls fail fast with the `killall Keynote` recovery path
  instead of burning full timeouts.
- **`KEYNOTE_MCP_SAVE_DIR`** environment variable — default directory for
  `create_presentation` without `save_path`.

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
