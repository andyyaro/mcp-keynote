# CLAUDE.md — keynote-mcp

## What this is

An MCP (Model Context Protocol) server that controls Apple Keynote via
AppleScript. It exposes 59 tools: whole-deck declarative building
(`build_deck`/`describe_deck`), presentations, slides, content (text,
images, lists, code blocks, theme placeholders), NATIVE tables and charts,
rendered color panels, per-range text styling, transitions, styles
(`.keynote-mcp.toml`), build animations, exports (PDF/PPTX/movie/HTML/
images), and Unsplash (opt-in). The capability boundary is documented and
probe-verified: `docs/CAPABILITY_MATRIX.md` (what the dictionary offers vs.
what we expose) and `docs/CEILING.md` (what is impossible and why — read it
before attempting anything on its CANNOT list).

## How to run

```bash
uv --directory /path/to/mcp-keynote run keynote-mcp
```

Registered in Claude Code as:
```bash
claude mcp add keynote-mcp -- uv --directory ~/dev/mcp-keynote run keynote-mcp
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
                           (get + live set), document settings
    slide.py             — add/delete/duplicate/move/select slides, layouts,
                           transitions, skipped slides
    content.py           — text boxes/titles/lists/code/quotes (font, color,
                           auto-fit boxes, exact centering), theme
                           placeholders (set_slide_content), images, shapes,
                           edit/move/resize/delete elements, speaker notes,
                           clear_slide, build animations (UI scripting)
    fragments.py         — SINGLE SOURCE of element-creation AppleScript
                           (argv-safe fragment builders + trusted literal
                           maps) consumed by content/objects/deck alike
    objects.py           — native add_table/add_chart, add_line, rendered
                           add_colored_panel, style_text_range,
                           replace_image, set_element_style
    deck.py              — build_deck (JSON spec + markdown dialect,
                           validate-all-then-build, batched sessions,
                           per-element try isolation) and describe_deck
    export.py            — screenshot_slide, export_pdf (+options),
                           export_presentation (pptx/movie/html/images/key09)
    unsplash.py          — Unsplash REST tools (need UNSPLASH_KEY)
  utils/
    applescript_runner.py — runs '/usr/bin/osascript -' with user strings as
                            argv; bounded timeouts
    error_handler.py      — exception hierarchy, validators (parse_color
                            takes #RRGGBB or r,g,b), stderr→actionable
                            error mapping (-1743/-1728/-1719/-600/-1712)
    styles.py             — DeckStyle + built-ins (plain/boardroom/midnight/
                            editorial), .keynote-mcp.toml loading
    render.py             — pure-Python PNG rendering (rounded panels)
tests/
  unit/                  — no GUI, no Keynote; runs in CI (95% coverage)
  integration/           — @pytest.mark.keynote; drives a real Keynote
docs/                    — ENVIRONMENT.md (verified host facts),
                           TOOL_MATRIX.md (per-tool verification),
                           CAPABILITY_MATRIX.md (sdef coverage analysis),
                           CEILING.md (what is impossible and why),
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
6. **A visual tool gets a RENDERED check, never a structural one.** Counts,
   property read-backs and "the file exists" prove an object exists, never
   that it looks like anything — that is exactly how a pie chart shipped
   rendering as one 100% slice with `count of charts is 1` passing. The
   harness owns helpers for this (`render_slide`, `at`, `ink_bbox`,
   `ink_fraction`, `fill_areas`, `pdf_page_count` in
   `scripts/verify_tools.py`); use them, and where no render can show the
   effect (build animations, transitions) say so in the TOOL_MATRIX row
   instead of leaving the check looking stronger than it is. Two notes from
   building them: ink is detected as a high-pass against the image's own
   blur, because themes paint gradient backgrounds that a "differs from the
   background color" test flags entirely; and chart fills are found by area
   against a background ring, not by saturation, because theme series colors
   include neutral gray.

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
- The legacy ">48pt tiny-box clipping" does NOT reproduce on Keynote 14.5 in
  the server's single-osascript-call flow (probed at 96/150/300/500pt with
  long/multiline/CJK text): auto-fit tracks the text at every size, Keynote
  itself wraps lines that would outgrow the slide (box stayed ≤ ~1800pt),
  and the auto-fit box hugs the rendered text — box center ≡ visual text
  center within 0.5pt (pixel-measured). That equivalence is what makes
  `centered` visually exact, so never pre-widen the box (the old
  0.58·pt/char heuristic centered the box while the left-aligned text
  inside sat ~110pt left of slide center at 96pt). Re-setting the text
  after sizing is kept as cheap insurance against truncation regressions.
- Text items are born at the theme default font size (48pt, default theme)
  and auto-fit when the size changes, keeping the box's vertical CENTER
  fixed — a position set before sizing drifts by (h_before−h_after)/2
  (horizontal auto-fit is left-anchored; x holds). Explicit `set height` on
  a text item snaps back to auto-fit with the same center-math side effect.
  Hence `_add_text_element` applies position AFTER all sizing and every
  add_* returns the settled geometry read back in the same osascript call.
- `move slide X to slide Y` REPLACES slide Y — always `before/after slide Y`.
- Build animations, build order, "With Previous" timing, and connection-line
  routing have no AppleScript API; builds use System Events UI scripting
  (Accessibility permission), the rest is manual-only.

### 3.0.0 capability-expansion facts (probe-verified; see CAPABILITY_MATRIX/CEILING)

- **`st` is a reserved AppleScript token** (the ordinal suffix in `1st`) —
  `set st to ""` is a syntax error. So are `before`, `nd`, `rd`, `th`. Never
  use them as script variable names.
- The Compatibility-Suite **`add chart` requires the target slide to be the
  `current slide`** — otherwise it SILENTLY creates nothing. Chart data is
  write-once (the `chart` class exposes only geometry); update = delete +
  re-add. **Pie slices come from the grouped axis**: grouping by a
  single-entry axis renders one 100% slice (chart_fragment auto-corrects).
- **Native tables need ≥2 rows AND ≥2 columns** (-10000 below that). Cell
  values set to a string starting `=` become live formulas. Table range
  styling (font/size/color/bg/alignment/wrap) all works.
- **`make new group` is a complete silent no-op** (0 items created);
  element-level `duplicate` raises "can not be copied" (-1717); z-order =
  creation order and cannot be changed (-10024). build_deck's spec order IS
  paint order — panels before the text on them.
- **Movie/audio insertion is impossible**: `{file:…}` fails coercion,
  `{file name:…}` silently creates nothing.
- Document `width`/`height` are rw on a LIVE document (probed 1024×768 →
  1920×1080); Keynote rescales layout content itself.
- `set file name of image N to POSIX file …` replaces an image in place,
  geometry preserved; the bare-text form raises -1703.
- `skipped:true` inside `make new slide with properties` is silently
  ignored — set it as its own statement.
- describe_deck round-trip limits: charts come back geometry-only
  (`chart_type: null` — correctly rejected if rebuilt as-is) and embedded
  images keep only a basename once the source file is gone.
- **`make new line` fails with -10000 while the Animate inspector is open**
  (deterministic; other make-new classes keep working). The build tools
  restore the Format pane when they finish (`_restore_format_pane`). This
  was first misdiagnosed as a transient — the isolated repro passed because
  it never opened the inspector; only the full-harness ordering exposed it.
  The general fact — scripting outcomes depend on Keynote's visible UI state,
  which no tool controls — is a section of `docs/CEILING.md` ("UI state
  affects scripting"). Its rule for new code: if a tool changes app or
  document state the caller did not ask for, capture the old state in
  **Python**, restore it in a `finally`, and make the restore best-effort.
  Restoring inside the same script is not enough — a timeout or a modal
  dialog kills the script before the restore line runs. `screenshot_slide`
  had exactly that hole: it skips every slide to isolate one for export, and
  a slow export left the user's whole deck skipped.
- Element-creation AppleScript lives ONLY in `tools/fragments.py`; new
  element kinds get a fragment there so build_deck and the single tool stay
  identical. New tool = schema + method + `server._dispatch` case + fragment
  (if element) + `scripts/verify_tools.py` check + TOOL_MATRIX row.

### 4.1.0 facts (round-2 field feedback)

- **A schema property, a method parameter and a `_dispatch` line are three
  separate things, and all three must exist.** Since 4.0.0 rejects unknown
  arguments, a parameter missing from the schema is not merely undocumented —
  it is unreachable, and the call errors. Three build tools' `doc_name` and
  `describe_deck.include_text_runs` each shipped that way, one of them
  documented in TOOL_MATRIX.md. `tests/unit/test_tool_schemas.py` now compares
  all three, in both directions; do not add an argument without it.
- **Per-run text styling IS authorable**, contrary to what `build_deck`'s
  description asserted for two releases. `set color/size/font of characters S
  thru E of object text of <item>` works on a freshly created item in the same
  session. Order is load-bearing: AFTER the element's text (re-setting
  `object text` discards runs) and its box-level colour (which flattens them),
  BEFORE its position (a run that changes size re-triggers auto-fit, which
  holds the box's vertical centre). Offsets are 1-based INCLUSIVE and are
  validated against the text in Python — `characters 5 thru 400` of a
  12-character string is a runtime error one element deep in a batched build.
- **Keynote renders text through a colour profile.** An authored `#830041`
  paints as ~(138,37,82), not (131,0,65). Not a write error: a hand-made deck
  renders the same maroon at (138,32,82). A rendered check must compare against
  what the app paints, with a tolerance (~45) far below the separation between
  the colours being told apart.
- **`build_deck`'s spec rejects unknown keys at deck/slide/element/run level.**
  Adding an element field means adding it to `_ELEMENT_KEYS` in `deck.py`, and
  anything `describe_deck` EMITS but cannot write back goes in the matching
  `_TOLERATED` set instead — otherwise the format refuses its own output. The
  live harness is what caught the two that were missed (`rendered` and the
  image `description` on a decoded panel), so run it after touching those sets.
- Invented-capability names (`fill_color`, `corner_radius`, `bold`, …) have ONE
  hint table, `utils/unsupported.py`, shared by the tool-argument boundary and
  the spec-key boundary. Add new ones there, not in either caller.

### Field-test facts (Phase 8 — the sandbox/save/placeholder traps)

- **Never send AppleScript `open` for a file outside Keynote's sandbox
  container** (~/Downloads, ~/Desktop, …): it wedges the AppleEvent queue
  entirely — zero windows, every subsequent event times out (-1712 even at
  90 s), and only force-quitting Keynote recovers. `open_presentation` uses
  LaunchServices (`open -a Keynote`) + a poll for the document; keep it that
  way. (Phase 3's open check passed only because Keynote itself had just
  saved the file, which leaves a sandbox extension behind.)
- **The first `save` of an unsaved document opens a modal save sheet** that
  blocks the queue until timeout — and Keynote then completes a default save
  to iCloud as `Untitled.key`, so the "failed" call half-succeeded in the
  wrong place. Hence: `create_presentation` always saves (default
  `~/Documents`, `KEYNOTE_MCP_SAVE_DIR` override) and `save_presentation`
  refuses a pathless save on a never-saved doc. Save-as to a new path on an
  already-saved doc hangs invisibly — refused too.
- **`count of text items` lies.** The slide's `default title item` /
  `default body item` objects are counted even when hidden (surfacing as 0x0
  empty entries at 0,0) and TWICE when showing (in z-order and again
  trailing). Real items always come first, so real indices are stable.
  Filter by object identity (`text item i is defaultTitleItem`); identity
  comparison through the app works. `count of iWork items` is truthful.
- **`make new text item` does not append last** in the text-item index
  space (phantoms trail it) — locate the created item's index by identity,
  never report the count as the index.
- **Slide-image exports omit unfilled placeholder boxes**, so a screenshot
  is not a faithful editor view — `screenshot_slide` counts what it omitted.
- **`POSIX path of (file of doc)` inline fails to coerce (-1700)** right
  after a save; capture `file of doc` into a variable first.
- New presentations default slide 1 to the **Blank layout** (documented
  policy, matching `add_slide`); `set_slide_content` opts back into theme
  placeholders by setting `title/body showing` before filling.

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
- If every Keynote call suddenly times out, the AppleEvent queue is wedged
  (see field-test facts): the runner's probe reports it and the only fix is
  `killall Keynote` + relaunch + `open_presentation`. A scripted `quit` is
  itself an Apple event and will hang too.
- A tool marked "verified" in TOOL_MATRIX.md is only as good as what its
  check exercises — the matrix now records that per tool. When adding a
  check, prefer inputs the server did NOT produce itself (foreign files,
  unsaved docs, indices from responses), not just its own happy path.
