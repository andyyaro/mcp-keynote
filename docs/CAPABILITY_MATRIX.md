# Capability matrix — Keynote 14.5 scriptable surface vs. this server

Produced 2026-07-26 on the `capability-expansion` branch, at v2.3.0 (45
tools). The scripting dictionary (`docs/keynote-14.5.sdef`, byte-identical to
the installed Keynote 14.5 — re-diffed today) was parsed programmatically
(`.scratch/sdef_inventory.py`: 5 suites, 31 classes/extensions, 39 commands,
19 enumerations, 3 record types), then every ambiguous item was **executed
against a live Keynote 14.5** in three probe rounds
(`.scratch/probe_phase_a*.py`, results in `.scratch/probe_results_phase_a*.md`).
Nothing below is asserted from documentation alone unless explicitly marked
*unprobed*.

Verdict shorthand: **probe** = ran live today; **matrix** = already verified
by `scripts/verify_tools.py` (see `TOOL_MATRIX.md`).

---

## 1. COVERED — sdef surface the 45 tools already expose

| sdef surface | Tool(s) | Evidence |
|---|---|---|
| `make new document with properties {document theme:…}`; `save … in POSIX file` | `create_presentation` | matrix |
| LaunchServices open + document poll (AppleScript `open` deliberately unused — wedges the queue) | `open_presentation` | matrix |
| `save`, `close saving yes/no` | `save_presentation`, `close_presentation` | matrix |
| `name of every document` | `list_presentations` | matrix |
| `document theme` (rw), `name of every theme` | `set_presentation_theme`, `get_available_themes` | matrix |
| document `name`/`count of slides`/`document theme` | `get_presentation_info` | matrix |
| document `width`/`height` (read) | `get_slide_size` | matrix |
| `make new slide at …`, `delete slide` (exists-guarded), `duplicate slide to …`, `move slide to before/after …` | `add_slide`, `delete_slide`, `duplicate_slide`, `move_slide` | matrix |
| `count of slides`, `current slide` (set), `base layout` (rw), `name of every slide layout` | `get_slide_count`, `select_slide`, `set_slide_layout`, `get_available_layouts`, `get_slide_info` | matrix |
| `make new text item with properties {object text:…}` + rich-text whole-item `font`/`size`/`color` | `add_text_box/title/subtitle/bullet_list/numbered_list/code_block/quote` | matrix |
| `title showing`/`body showing`, `default title item`/`default body item` (identity-filtered) | `set_slide_content`, `get_slide_content`, `get_slide_info`, `clear_slide` | matrix |
| `make new image with properties {file:…}` | `add_image`, Unsplash tools | matrix |
| `make new shape with properties {position,width,height}` + `opacity` | `add_shape`, `set_element_opacity` | matrix |
| iWork item `position`/`width`/`height` (rw), `delete <element>` (exists-guarded), `object text` set | `move_element`, `resize_element`, `delete_element`, `edit_text_item` | matrix |
| `presenter notes` (rw) | `get_speaker_notes`, `set_speaker_notes` | matrix |
| `export … as PDF` (bare), `export … as slide images` (fixed PNG, skipped-state save/restore) | `export_pdf`, `screenshot_slide` | matrix |
| Build animations via System Events UI scripting (no sdef surface exists) | `add_build_in`, `remove_build_in`, `add_builds_to_slide` | matrix |

## 2. AVAILABLE BUT UNEXPOSED — scriptable, useful, probed live today

> **Status update (3.0.0, same day):** everything in this section except the
> "Small/unprobed remainder" table was implemented and live-verified —
> tables/charts (`add_table`/`add_chart`), transitions
> (`set_slide_transition`), exports (`export_presentation`, `export_pdf`
> options), per-range styling (`style_text_range`), document
> settings/geometry (`set_document_settings`/`set_slide_size`), skipped
> slides (`set_slide_skipped`), lines (`add_line`), image properties
> (`replace_image`, `add_image` width/height/description,
> `set_element_style`). Deliberately left unexposed (low value for a model
> building decks — revisit here if that judgment changes): playback control,
> document passwords, `make image slides`, `.kth` via make-with-data,
> `print`. Per-tool verification: [TOOL_MATRIX.md](TOOL_MATRIX.md); the
> impossibility list with workarounds: [CEILING.md](CEILING.md).

Ordered roughly by expected value to a model building a real deck.

### Native tables — the largest single gap
`make new table with properties {position, width, height, row count, column
count, header row count, header column count}` **works** (probe), and so
does essentially the whole table object model:

| Surface | Probe result | Tool note |
|---|---|---|
| Cell values: `set value of cell N of row M` and `cell "B1"` | works (text and numbers) | `add_table` takes a 2-D data array |
| Formulas: `set value … to "=SUM(1,2)"`, read `formula`/`value` | works (`=SUM(1,2)` → 3.0) | pass-through: strings starting `=` become formulas |
| Range styling: `font name`, `font size`, `text color`, `background color`, `alignment` (left/center/right/justify), `vertical alignment`, `text wrap` — on any `range "A1:C1"` | all work (read back) | header styling, zebra stripes, per-column alignment |
| `width of column N` / `height of row N` | works | column-width control |
| `merge`/`unmerge range` | works | spanning header cells |
| `sort by column N direction ascending/descending` | works | data manipulation |
| `row count`/`column count` growable after creation | works (4×3 → 6×4) | resize existing tables |
| Bulk readback `value of every cell of row N` | works | cheap `describe_deck`/read tools |
| **Constraint:** row count and column count must each be ≥ 2 | 1×N and N×1 both raise `Invalid row/column count (-10000)` | validator must enforce |

### Native charts — via the Compatibility Suite `add chart` command
`add chart row names {…} column names {…} data {{…}} type X group by Y`
**works on Keynote 14.5** and creates a real, theme-styled Keynote chart
(probe: bar, stacked bar, horizontal bar, line, area, scatter, pie, 3-D bar).

- **Requires the target slide to be the `current slide`** — otherwise it
  silently creates nothing (probe round 1 vs round 2 comparison). The tool
  must `set current slide` first, like the build tools do.
- 17 types in the `legacy chart type` enum (2-D/3-D bar/column/stacked/line/
  area/pie/scatter), `group by chart row/column`.
- The created chart is addressable as `chart N` (geometry read/write works —
  probed `position`/`width`).
- **Post-creation limit:** the `chart` class exposes only iWork-item geometry;
  series data, colors, axis ranges are NOT readable or writable afterwards.
  Changing data = delete + re-add.

### Slide transitions
`set transition properties of slide N to {transition effect:…, transition
duration:…, transition delay:…, automatic transition:…}` works and reads
back (probe: push, 1.5 s). 43 effects in the `transition effects` enum
(magic move, dissolve, push, wipe, cube, confetti, …). Tool: `set_slide_transition`
/ readable via slide info.

### Export formats beyond bare PDF
All probed live; artifacts verified on disk:

| Format | Probe | Tool note |
|---|---|---|
| Microsoft PowerPoint (`.pptx`, 55 KB artifact) | works | `export_pptx` — the #1 interchange ask |
| PDF `with properties {export style:SlideWithNotes, PDF image quality:Best, skipped slides:true}` | works (84 KB, notes layout) | extend `export_pdf` with options; handout/notes layouts |
| Slide images `{image format:PNG/JPEG/TIFF, skipped slides, compression factor}` | works (8 PNGs) | extend `screenshot_slide`/new `export_images` |
| QuickTime movie `{movie format:format360p…format2160p/native, movie codec, movie framerate}` | works (360 KB `.m4v`) | `export_movie` (slow: bound by real playback/render time) |
| HTML | works (4.2 MB player bundle) | `export_html` |
| Keynote 09 | works (7.6 MB) | legacy interchange; low priority |

### Per-range rich text styling
The `object text` of any text item/shape exposes `character`, `word`, and
`paragraph` elements, each with rw `color`, `font`, `size` (probe: colored
characters 1–5 red while 9+ stayed black; word 1 set to `Helvetica-Bold`
while word 3 stayed `HelveticaNeue`; characters 7–12 at 60 pt inside a 30 pt
paragraph). Bold/italic = switching to the bold/italic PostScript font name —
there is no style attribute. Tool: `style_text_range(slide, item, start, end,
font/size/color)`.

### Document settings & geometry
- `width`/`height` of document are **rw on a live document** — probe resized
  an existing 1024×768 deck to 1920×1080. Tool: `set_slide_size`.
- Sizes can also be set at creation (`make new document with properties
  {width:1920, height:1080}` — probe).
- `slide numbers showing`, `auto loop`, `auto play`, `auto restart`,
  `maximum idle duration` all set/read correctly (probe). Tool:
  `set_document_settings`.

### Skipped slides
`skipped` of slide is rw (probe). Quirk: `skipped:true` inside `make new
slide with properties` is silently ignored — must be set after creation
(probe). Tool: `skip_slide`/`unskip_slide` or a boolean on slide info.

### Lines
`make new line with properties {start point:{x,y}, end point:{x,y}}` works;
endpoints are rw afterwards (probe). Rotation/reflection also rw. Tool:
`add_line` (dividers, connectors between fixed points — no connection-line
routing, see §3).

### Image properties beyond insertion
- `description` (VoiceOver alt text) rw — probe. Belongs in `add_image`.
- `file name` set with a `POSIX file` **replaces the image in place,
  preserving geometry** — probe (red → blue swap). The bare-text form raises
  -1703; must send `POSIX file`. Tool: `replace_image`.
- `rotation` (0–359) and `reflection showing`/`reflection value` rw — probe.

### Shape/text-item properties beyond opacity
`rotation`, `reflection showing`, `reflection value`, `locked` all rw
(probe); `object text` of a plain shape is settable (probe: "shape label").
Tool: extend `add_shape`/new `set_element_style` (rotation/reflection/lock).

### Bulk image slides
`make image slides files {…} set titles true/false [slide layout …]` works
(probe; the run added 4 slides for 2 files — behavior to pin down when the
tool is built). Tool: photo-deck bulk import.

### Playback control
`start <doc> from slide N` / `stop <doc>` work (probe; full-screen play
started and stopped cleanly). Also `show next`/`show previous`/slide-switcher
commands (unprobed but same family). Tool: `start_presentation`/
`stop_presentation` for rehearsal/kiosk automation.

### Document security
`set password "…" to <doc> hint "…"` / `remove password` / `password
protected` (r) all work (probe round-trip true→false). Tool: opt-in
`set_document_password`. The `export options` record also accepts `password`.

### Small/unprobed remainder

| Surface | Status | Note |
|---|---|---|
| `make new document with data POSIX file "theme.kth"` | unprobed (no `.kth` asset on this machine; `.kth` cannot be produced by script) | documented sdef path for custom-theme decks; accept as a `theme_file` arg and surface Keynote's error if it fails |
| `print` command + `print settings` | unprobed (modal-dialog risk — printing without a dialog needs a configured printer) | deliberately left unexposed |
| `document.id`, `theme.id` | trivially readable | expose in `get_presentation_info` |
| `modified` of document | trivially readable | expose in info tools |
| `iWork item.parent`, `locked` | probed (`locked` rw) | info/lock tooling |
| audio clip / movie `volume`, `repetition method` | moot | insertion is impossible (§3), so only relevant for user-placed media |
| `selection` (rw) on document | unprobed | of marginal MCP value; skip |
| Slide-switcher commands | unprobed | presenter-remote niche; skip |

## 3. IMPOSSIBLE — confirmed by live probe or absent from the dictionary

Each row is either **(P)** probed today with the recorded error, or **(D)**
absent from the dictionary — no term exists to compile, with representative
compile-error probes proving the class of failure.

| Capability | Verdict | Evidence |
|---|---|---|
| Shape/text-item **fill color** | (P) impossible | `background fill type` is read-only: `set … to color fill` → -10006; `set background color of shape` → -10006 (no such property). Only workarounds: opacity on the default fill, or a styled table cell (but see 2×2 floor), or a pre-colored image |
| **Text alignment** (left/center/right) on text items/shapes | (P) impossible | `set alignment of object text …` → -10006. Alignment exists **only** on table ranges (tAHT), where it works. Server-side `centered` box-placement remains the workaround |
| **Hyperlinks** | (P) impossible | no `hyperlink` class; `make new hyperlink` → "variable hyperlink is not defined" (-2753) |
| **Grouping / ungrouping** | (P) impossible | `make new group` is a complete silent no-op (iWork items 0→0); `move shape … to group 1` → -1719. The `group` class exists only to *read* groups a user made by hand |
| **Z-order** (bring to front / send to back) | (P) impossible | `move text item 1 to front of slide 1` → "Can't make or move that element into that container" (-10024). Z-order is creation-order, period |
| **Duplicating elements** (copy a styled box between slides) | (P) impossible | `duplicate text item … to slide 2` → "Text items can not be copied" (-1717); same for shapes. Only whole slides duplicate |
| **Shape geometry types** (oval, star, arrow, polygon…) | (P) impossible | no `shape type` term — `make new shape with properties {shape type:oval}` is a syntax error (-2741). `make new shape` yields the default rectangle only |
| **Movie insertion** | (P) impossible | `{file:…}` → "Can't make {file:…} into type properties of movie" (-1700); `{file name:…}` silently creates nothing (movies 0, iWork items 0→0) |
| **Audio insertion** | (P) impossible | `make new audio clip {file name:…}` silently creates nothing (clips 0, items 0→0) |
| **1-row or 1-column tables** | (P) impossible | `Invalid row count` / `Invalid column count` (-10000); floor is 2×2 — also kills the "1×1 table as fill-colored rectangle" idea |
| **Chart data/series editing after creation** | (P) impossible | `chart` class exposes only iWork-item geometry; no data terms exist. Delete + re-add is the only update path |
| `skipped:true` inside `make new slide` properties | (P) quirk | silently ignored (probe read back false); set it in a second statement |
| **Build animations / build order / "With Previous"** | (D) no API | no terms anywhere in the dictionary; the existing UI-scripting tools remain the only route (fragile, English-UI, Accessibility-gated) |
| **Connection lines** (routed connectors) | (D) no API | `line` has only fixed start/end points; no attachment/routing terms |
| **Borders, strokes, shadows, line weight/color/style** | (D) no API | no stroke/shadow/border terms on any iWork class (table *cell* borders included) |
| **Slide background** (color/image per slide) | (D) no API | no background term on `slide`; backgrounds live in layouts, which are read-only (`slide layout` exposes only `name`) |
| **Creating/editing slide layouts or themes** | (D) no API | `slide layout` element of document is read-access; only `name` is exposed |
| **Bullet/list style control** (indent levels, bullet glyphs, spacing) | (D) no API | rich text exposes only color/font/size; no paragraph-style, line-spacing, or list terms |
| **Line spacing / paragraph spacing / kerning** | (D) no API | as above |
| **Text bold/italic as attributes** | (D) no API | no style attribute on rich text; the probe-verified workaround is switching `font` to the bold/italic face name per range |
| **Comments/presenter display options** | (D) no API | `include comments` exists only as an *export* option |
| **Reading theme placeholder geometry from layouts** | (D) no API | layouts are opaque; placeholder geometry is only observable after a slide uses it |

### Consequences accepted by this repo (do not re-litigate)

- Colored panels/cards must come from images (generated PNGs), opacity
  tricks, or styled table cells — never a native filled shape.
- Anything needing z-order (text over a colored panel) must be created in
  paint order: panel first, text after.
- "Editable native diagram with arrows and shapes" is out of reach; rendered
  images (Phase C) are the honest substitute, clearly labeled non-editable.
- Charts are native but **write-once**: `add_chart` documents that updating
  means replace.
