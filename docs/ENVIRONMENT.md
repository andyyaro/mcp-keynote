# Environment — ground truth for this modernization

Captured 2026-07-25 on the machine where every claim in this repo was verified.
All AppleScript property/command claims are validated against the Keynote
scripting dictionary, tracked at `docs/keynote-14.5.sdef` (regenerate for a
newer Keynote with the command below).

## Host

| Item | Value | How captured |
|------|-------|--------------|
| macOS | 26.5.1 (build 25F80), Apple Silicon (arm64) | `sw_vers` |
| Keynote | 14.5 | `defaults read /Applications/Keynote.app/Contents/Info.plist CFBundleShortVersionString` |
| Python (project venv) | 3.13.14 (uv-managed CPython) | `.venv/bin/python --version` |
| Python (system default) | 3.14.6 (Homebrew) | `python3 --version` |
| uv | 0.11.29 | `uv --version` |
| mcp (resolved) | 1.28.1 | `.venv/bin/python -c "import importlib.metadata; print(importlib.metadata.version('mcp'))"` |

## MCP SDK versions on PyPI (verified 2026-07-25)

`uv pip index versions` does not exist in uv 0.11.29, so versions were
verified against the PyPI JSON API (`https://pypi.org/pypi/mcp/json`):

- Latest stable: **1.28.1** (the 1.x line)
- Pre-releases: 2.0.0a1 … 2.0.0a3, 2.0.0b1, 2.0.0b2 (v2 reworks the SDK for
  the 2026-07-28 protocol spec — see `docs/MCP_V2_MIGRATION.md`)

This repo pins `mcp>=1.28,<2`.

## Keynote scripting dictionary (the spec)

```sh
sdef /Applications/Keynote.app > .scratch/keynote.sdef
```

Note: `sdef(1)` requires full Xcode; on a Command Line Tools–only machine the
identical dictionary ships inside the app bundle:

```sh
cp /Applications/Keynote.app/Contents/Resources/Keynote.sdef .scratch/keynote.sdef
```

The dictionary `xi:include`s the standard suite (open/close/save/quit/…)
from `/System/Library/ScriptingDefinitions/CocoaStandard.sdef`; consult that
file for standard verbs that don't appear in the Keynote suites.

### Facts from the sdef that shaped this fork (Keynote 14.5)

- `slide` has `base layout` (type `slide layout`, rw) with official synonym
  **`base slide`**; the `slide layout` class has official synonym
  **`master slide`**. Both spellings used in this repo are therefore valid.
- `document` has `document theme` (rw). There is **no** `theme` property
  synonym on document — `set theme of doc …` is not per-spec.
- `shape` and `text item`: `background fill type` is **read-only** and there
  is no writable fill-color property → shape fill color cannot be set via
  AppleScript. `opacity` (integer) is rw.
- `image.file` is read-only (`file name` is rw); images are created with
  `make new image with properties {file: …}`.
- `rich text` (the `object text` of a shape/text item) exposes `color`,
  `font` (text), `size` (real) — all rw.
- `iWork item` (parent of shape/text item/image/…): `position` (point),
  `width`/`height` (integer) — all rw; `locked` (boolean) rw.
- Export formats: HTML, QuickTime movie, PDF, slide images, Microsoft
  PowerPoint, Keynote 09; image export formats: JPEG, PNG, TIFF.
- There is no AppleScript access to build animations, build order, or
  connection-line routing — those exist only via UI scripting
  (System Events + Accessibility permission).
