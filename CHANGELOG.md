# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [4.1.0] - 2026-07-26

Round-2 field feedback: three defects, plus the run-authoring gap they exposed.
Every one is a case of documentation and behavior disagreeing — which is the
same failure as a dropped argument, one level up. 289 live checks, 0 failed.

### Added

- **`build_deck` authors text runs.** A text/title/subtitle/code/quote element
  takes `runs: [{start, end, color?, font_name?, font_size?, role?}]` over
  1-based inclusive offsets, so a tri-colour heading is ONE call instead of the
  element plus three `style_text_range` calls — and a described deck keeps its
  runs when rebuilt, which is the point of the format. `build_deck`'s own
  description had asserted this was impossible; it had never been probed. The
  write route always existed (`set color of characters S thru E …`), and inside
  the batched session it costs AppleScript lines, not Apple events. Runs are
  written after the element's text and colour (both of which would otherwise
  erase or flatten them) and before its position (a run that changes size
  re-triggers auto-fit, which holds the box's vertical centre). Verified in
  pixels: three distinct ink colours on the exported slide, then the UNEDITED
  description rebuilt and re-sampled with the first deck CLOSED, so a
  mistargeted export cannot pass.

### Fixed

- **`build_deck` silently ignored unknown keys at every level of `spec`** —
  deck, slide, element and run. The same silent-drop class 4.0.0 fixed at the
  tool-argument boundary, still live in the largest model-authored input the
  server takes: a spec with a mistyped `layuot`, an invented `fill_color` and a
  plausible `font` built with zero errors, and the render was the only place it
  showed. Unknown keys are now rejected with the accepted set named and nothing
  created; invented-capability names share one hint table with the argument
  boundary (`utils/unsupported.py`), so `fill_color` gets the same explanation
  and the same alternative in a spec as it does as an argument. Keys
  `describe_deck` emits that Keynote cannot write back (`rotation`, per-element
  `opacity`, shape `locked`/`reflection_showing`) are ACCEPTED so the round trip
  survives, and reported in the reply under `not_applied` — tolerating them
  silently would have been the original bug again.
- **Three tool arguments existed but could not be reached.** `doc_name` on
  `add_build_in`/`remove_build_in`/`add_builds_to_slide` was implemented in
  4.0.0 and announced in the CHANGELOG, but never added to the schema — so once
  4.0.0 began rejecting unknown arguments, passing it was an error.
  `describe_deck.include_text_runs` was implemented AND documented in
  TOOL_MATRIX.md, and likewise absent from the schema. Both directions are now
  pinned by tests that compare every schema against its method signature and
  against what `_dispatch` actually forwards.
- **`describe_deck` rebuilt a theme placeholder twice.** It reports a
  placeholder as `slide.title`/`body` AND as an indexed element (deliberately —
  see INDEX_CONTRACT.md), and `build_deck` built both, putting the heading in
  the placeholder and again as a loose text box on top of it.

### Documentation

- **`describe_deck`'s description still documented the v3 return shape**, which
  is all a model reads: none of 4.0.0's read fidelity — hex colours beside
  `color_65535`, font family/weight/style beside the PostScript name, per-run
  `runs`, `placeholder`, rotation/opacity/`fill_type`, the `not_reported` block,
  the index contract — was visible. Rewritten to the actual shape, field by
  field. The same audit rewrote `get_slide_content` (which gained per-item
  `role:` flagging and a filtered count), the five index-addressed writes (which
  gained `exists` guards), `open_presentation` (session default),
  `add_colored_panel` (round-trips via its filename), `style_text_range`
  (authoring belongs in the spec now) and the three build tools.
- **FIDELITY_REPORT.md and CEILING.md cited the real deck's H1 at y=817 in
  three places.** Measured value is **y≈543** — ink rows 480–607 of the
  1920×1080 reference export, and `describe_deck` reports the box at `y=461,
  h=158`. The conclusion those documents drew was right; the number offered as
  its evidence was never measured from anything. Now stated with its provenance.
- CEILING.md gained "Runs, which turned out not to be a ceiling at all",
  including the finding that **Keynote renders text through a colour profile** —
  an authored `#830041` lands at ~(138,37,82), and the original hand-made deck
  renders the same maroon at (138,32,82), so a rendered check must compare
  against what the app paints, not against what was sent.

## [4.0.0] - 2026-07-26

Fidelity and correctness pass, driven by an external field report from
reverse-engineering a real 35-slide, ~800-element technical architecture deck
([MCP-CONNECTOR-FEEDBACK.md](MCP-CONNECTOR-FEEDBACK.md)). 59 → 61 tools.

Major, because three fixes change behavior a caller could depend on: unknown
arguments are now rejected rather than ignored, an ambiguous document target is
now an error rather than a guess, and `describe_deck`'s element records gained
required addressing fields.

### The report's central claim was wrong, and finding out why exposed a real bug

The report stated `set_element_style` CAN write shape fill — which would have
made `add_colored_panel`'s PNG workaround obsolete. This repo has twice shipped
a workaround that outlived its cause, so the claim was treated as probably true
until probed. It is false: 12 write routes × 5 themes, all -10006/-2740, raw
four-char-code chevrons included, with the shape's rendered interior
byte-identical before and after. `properties of shape 1` returns the complete
record and it matches the sdef exactly — no fill, no shape type, no corner
radius, no stroke.

What produced the belief was a genuine defect: **every tool schema accepted
unknown arguments and the dispatcher read only the names it knew**, so
`set_element_style(fill_color="#EFA3A0")` was dropped and reported as success.
Unknown arguments are now rejected before dispatch, naming the accepted
arguments and the right alternative; 25 invented capability arguments
(`stroke_color`, `corner_radius`, `bold`, `z_order`, …) get a targeted pointer.
`additionalProperties: false` is stamped on every schema centrally, so a new
tool cannot forget it.

### Fixed

- **Document resolution (the report's highest-severity item).** Tools that
  omitted `doc_name` resolved to Keynote's `front document` INSIDE the
  AppleScript, so a call after `open_presentation` could land on whichever deck
  the user had clicked last, and no reply said which document was used.
  Resolution now happens in Python: `create_presentation` / `open_presentation`
  / `build_deck` set a session default, every reply echoes its target, and an
  ambiguous target is an error that NAMES the open documents. `front document`
  is gone from the tool layer entirely — asserted by a test. Build animations
  gained `doc_name` too, bringing the requested window forward and verifying it
  arrived rather than animating the wrong deck.
- **One element numbering.** `describe_deck` and `get_slide_content` numbered
  text items differently, and only on slides using the title placeholder — so
  the offset was not even constant, and edits planned from a `describe_deck`
  dump silently hit the wrong element on ~half a deck. Probing pinned why: a
  SHOWING placeholder takes a LEADING slot and shifts every real index, which
  corrects CLAUDE.md's "real items always come first". The placeholder
  predicate now lives in ONE place (`fragments.TEXT_ITEM_FILTER`), every
  element carries `element_class` + `index`, and placeholders are represented
  as flagged elements rather than hidden. See [docs/INDEX_CONTRACT.md].
- **Missing `exists` guards** on `edit_text_item`, `style_text_range`,
  `move_element`, `resize_element` and `set_element_opacity`. A stale index
  addresses a DIFFERENT object rather than none, so an unguarded write edited
  the wrong element and reported success.
- **`clear_slide` deleted shapes with no identity guard** while its text loop
  guarded. The sdef types theme placeholders as shapes, so this could destroy
  one.
- **Panels did not round-trip at all.** They rendered into a temp directory
  that no longer existed by read-back time, so any deck containing a panel
  rebuilt to `image file does not exist`.

### Added

- **`styled_line`** — connectors whose colour, width, dash and arrowheads carry
  meaning. Keynote has no stroke API whatsoever, so the stroke is rendered to a
  transparent PNG. Available as a tool and as a `build_deck` element type,
  since the point is authoring 165 connectors in one call.
- **Round-trippable rendered elements.** Panel and stroke parameters are
  encoded in the FILENAME, the one piece of metadata Keynote keeps once a
  bitmap is embedded. `describe_deck` decodes them back into
  `{"type": "panel", "color": "#EFA3A0"}` and `build_deck` re-renders — so the
  round trip needs no durable file.
- **`export_assets`** — extracts a saved bundle's `Data/` folder, because
  `describe_deck` can only report an embedded image's basename once its source
  is gone (the report saw 61 elements all named `pasted-movie.png`).
- **`describe_deck` at scale.** Profiled first: 31.2 s / 125,509 chars / 2,415
  trailing `.0` on a 35-slide deck, making one osascript call PER SLIDE. Now
  `detail="summary"` (0.47 s), `slide_range`, `element_types` (skipped classes
  are never READ), batched full reads, and integer coordinates.
- **Per-run text styling on the read side.** A title mixing three colours
  reported one. `color/font/size of every character` each return the whole list
  in ONE Apple event, so three events per text item buys full run fidelity.
- Shape/text/image/line `rotation`, `opacity`, `fill_type`, `reflection`,
  `locked`; image `description`; per-slide group counts.
- **A `not_reported` block** on every full description, so a caller can tell
  "no fill" from "fill not reported" — including z-order, called out as
  unrecoverable.
- **Hex colours** (`#830041`) alongside Keynote's raw 16-bit triples, and
  **font family/weight/style** beside the PostScript name.
- **Named style vocabularies** — type roles, palette, semantic connectors,
  canvas zones and grid modules — and the **`sdh` built-in style** generated
  from a real design system. See [docs/STYLE_SYSTEM.md].

### Documentation

- `build_deck`'s own description now carries every limitation that shapes a
  spec (no fill, no stroke, permanent z-order, no grouping, fixed placeholder
  geometry, no per-run colour), because a `build_deck`-first user previously
  met them only on `add_shape`.
- New: [docs/INDEX_CONTRACT.md], [docs/STYLE_SYSTEM.md],
  [docs/FIDELITY_REPORT.md] (the pixel comparison against the real deck).

## [3.0.0] - 2026-07-26

Capability expansion to the practical ceiling of what Keynote's AppleScript
dictionary allows. The dictionary was parsed programmatically and every
ambiguous item probed against a live Keynote 14.5 first
([docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)); what the dictionary
genuinely cannot do is stated in [docs/CEILING.md](docs/CEILING.md). 45 → 59
tools; 196 live verification checks, 0 failed.

### Hardened before merge — verification that looks at the render

All 155 live checks asserted counts, properties, or file existence; none
looked at what Keynote drew. That is how a pie chart shipped rendering as a
single 100% slice while `count of charts is 1` passed. The harness now
inspects the export (`screenshot_slide` + Pillow) or the exported file's
contents wherever it can — chart slice counts and areas, panel and table
header colors, image bitmaps, text ink/clipping/centering, opacity, line
paths, slide numbers, theme repaints, PDF page counts, pptx slide parts,
image dimensions — and the two classes no static export can show (build
animations, transitions) say so in TOOL_MATRIX.md instead of looking as
strong as the rest. 196 checks, 0 failed.

Four defects it found, each of which had passed every structural check:

- `build_deck`: an element that pinned only one coordinate fell through to
  fully-manual placement, which left the other coordinate unset. Two elements
  with `column: left`/`right` plus a `y` drew on top of each other at x=0,
  and a title with only a `y` drew flush against the slide edge — through a
  zero-error build and a clean `describe_deck` round-trip. Now only a fully
  placed element skips the flow.
- `screenshot_slide`: it marks every slide skipped to isolate one for export
  and restored them at the end of the *same* script, so an export that
  outlived its timeout left the whole deck skipped. Read, export and restore
  are now separate calls with the restore in a `finally`.
- `export_presentation(images, include_skipped=True)`: ignored by Keynote
  (probed at the raw-AppleScript level; the same property works for PDF). The
  reply and the schema now say so.
- A corrupt fixture PNG proved `replace_image` could set `file name` while
  the image vanished from the slide — the check asserted the property.

### Added — declarative deck building

- **`build_deck`**: an entire deck from one JSON spec or a small markdown
  dialect. Whole-spec validation BEFORE anything is created (all errors at
  once, with `slides[i].elements[j]` paths); per-element AppleScript `try`
  isolation (one bad element reports, the rest of the deck builds); slides
  batched 5 per osascript session; settled geometry for every element in the
  reply; auto-flow layout inside style margins with `column: left/right`
  two-column support; `on_exists: replace|error|unique` re-run semantics.
  Benchmark (20-slide deck, live): 81 primitive tool calls / 21.8 s → 1 call
  / 11.9 s / 6 osascript sessions. Read that as **81 fewer round trips and 81
  fewer places to fail**, not as a speed multiple: both paths serialize
  through the same Keynote GUI, so the wall-clock difference is modest
  (21.8 s → 11.9 s) and would shrink further on a slower machine. The reasons
  to prefer it are the call count, the whole-spec validation before anything
  is created, and authoring at the level of content instead of coordinates.
- **`describe_deck`**: reads an open presentation back into the same spec
  format (layouts, transitions, skipped, notes, placeholders, elements with
  settled geometry, table cell values with numbers and formulas preserved) —
  decks round-trip and become diffable in git. Documented limits: charts
  come back geometry-only (no data API) and embedded images keep only a
  basename once the source file is gone.

### Added — native objects (probed live first)

- **`add_table`**: native Keynote tables from a 2-D data array — cell
  values, live formulas (any string starting `=`), header styling from the
  resolved style, column widths. Keynote enforces a 2×2 minimum (probed).
- **`add_chart`**: native theme-styled charts via the Compatibility-Suite
  `add chart` command (bar/line/area/pie/scatter, stacked, 3-D — 17 types).
  The target slide is made the current slide first (otherwise Keynote
  silently creates nothing — probed). Write-once: no chart-editing API
  exists; update = delete + re-add. Pie slices come from the grouped axis;
  the tool auto-groups by the axis that has multiple entries.
- **`add_line`** (straight lines, rw endpoints), **`style_text_range`**
  (per-character/word/paragraph color/font/size; bold = the bold face name),
  **`replace_image`** (swap the file, keep geometry), **`set_element_style`**
  (rotation, reflection, lock).
- **`add_colored_panel`**: rounded-rect color panels rendered as PNG
  (pure-Python, no Pillow) and placed as images — the documented route
  around the read-only shape fill. Explicitly not recolorable in Keynote.

### Added — slides, document, export

- **`set_slide_transition`** (all 43 effects, duration/delay/automatic),
  **`set_slide_skipped`**, **`set_slide_size`** (live document resize),
  **`set_document_settings`** (slide numbers, auto loop/play/restart, idle).
- **`export_presentation`**: PPTX, QuickTime movie (360p–2160p/native),
  HTML bundle, per-slide images (PNG/JPEG/TIFF), Keynote 09. `export_pdf`
  gained `layout` (slides / slides_with_notes / handouts), `image_quality`,
  and `include_skipped`. `add_image` gained width/height/description
  (VoiceOver alt text).

### Added — styles

- `.keynote-mcp.toml` style config (or a `style` argument: built-in name or
  TOML path) defining fonts, palette, margins, table header styling; four
  built-ins (`plain`, `boardroom`, `midnight`, `editorial`) with `extends`
  support. Consulted by `build_deck`, `add_table`, `add_colored_panel`.
  `parse_color` accepts `#RRGGBB` everywhere colors are accepted.

### Changed

- The element-creation AppleScript now has a single source
  (`tools/fragments.py`) consumed by both the per-element tools and
  `build_deck` — the verified invariants (argv-only user strings,
  position-after-sizing, identity-located indices, settled-geometry
  readback) hold everywhere by construction.

### Fixed

- Styles: TOML type validation now uses the dataclass annotations, so
  `title_size = 70.5` is accepted (the float field's whole-number default
  had made it demand an int).

### Facts learned (recorded so nobody re-litigates)

- `st` is a reserved AppleScript token (the ordinal suffix in `1st`) —
  `set st to ""` is a syntax error. So are `before`, `nd`, `rd`, `th`.
- Pie charts slice along the grouped axis; grouping by a single-entry axis
  renders one 100% slice.
- `make new group` is a complete silent no-op; element `duplicate` raises
  "can not be copied"; z-order is creation order, unchangeable.
- Movie/audio insertion silently creates nothing (or errors) — impossible.
- While the **Animate inspector is open** (as the UI-scripting build tools
  leave it), `make new line` fails DETERMINISTICALLY with -10000 "AppleEvent
  handler failed" (other make-new classes keep working). The build tools now
  restore the Format pane when they finish. First misdiagnosed as a
  transient; the live harness caught it because it runs builds before lines.

## [2.2.0] - 2026-07-26

Geometry honesty. A field build showed every add_* placed at y=Y settling at
a different y (deterministic, proportional to font size). Live step-traces
(12–96pt × 1/4-line text) pinned the cause: text items are created at the
theme default 48pt and auto-fit their box around its vertical CENTER when
the font size is applied, moving the top edge by (h_before−h_after)/2 — not
an anchor-point mismatch (position reads back exactly as set) and not a
deferred layout pass (the move is synchronous with `set size of object
text`). Horizontal auto-fit is left-anchored, so x never drifted. Explicit
`set height` on a text item snaps back to auto-fit with the same center-math
side effect.

### Changed — behavior

- **add_* coordinates now land exactly.** `_add_text_element` applies
  `set position` AFTER all font/size/text mutations (re-asserted positions
  stick; verified across sizes), so the caller's x/y is the settled
  top-left. 48pt callers see no change; other sizes no longer drift.
- **Every add_* returns the element's final geometry.** add_text_box /
  add_title / add_subtitle / add_bullet_list / add_numbered_list /
  add_code_block / add_quote / add_image / add_shape read back the settled
  position and size in the same osascript call and report
  `at (x, y), size WxH` (same AppleScript coercion as `get_slide_content`,
  so the strings match verbatim). add_image and add_shape now also return
  the element's index (located by object identity), usable with
  move_element / delete_element.

### Added

- `scripts/verify_tools.py` geometry-honesty section: places elements at
  known coordinates across 12/24/36/48/96pt (single- and multi-line, plus
  shape and image), asserts exact landing and reply == `get_slide_content`.
  Full harness: 109 live checks, 0 failed.
- Unit tests pinning the mutation order (position after font sizing) and
  the geometry-bearing reply format.

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
