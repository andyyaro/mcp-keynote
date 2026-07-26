# Tool matrix — every tool verified against Keynote 14.5

First verified 2026-07-25/26 on macOS 26.5.1, Keynote 14.5 (see
`docs/ENVIRONMENT.md`); re-verified 2026-07-26 after the Phase 8 field-test
fixes, extended 2026-07-26 for the 3.0.0 capability expansion, and hardened
2026-07-26 with rendered assertions. Every AppleScript verb/property was
checked against the Keynote scripting dictionary (tracked at
`docs/keynote-14.5.sdef`), then executed against a live Keynote via
`scripts/verify_tools.py` — **196 live checks, 0 failed** (last full run
2026-07-26). "Verified" below means the tool ran against a real document and
its effect was confirmed by reading state back, not just a non-error exit.

**Lesson from the field test (Phase 8):** the Phase 3 harness only exercised
documents it created itself with an explicit `save_path`, so several tools
were marked "verified" while failing on the paths real callers take (the
untitled-document save, opening a foreign file from outside Keynote's sandbox
container, trusting the returned element index). Each row now states what its
verification actually exercises; rows whose original status was happy-path
only are marked *(re-verified P8)*.

**Lesson from the pre-merge hardening pass (rendered vs structural):** all
155 checks of the 3.0.0 harness asserted counts, properties, or file
existence — **none looked at what Keynote drew**. That is how a pie chart
shipped rendering as a single 100% slice with `count of charts is 1` passing.
On a tool that draws something, a structural check proves an object exists,
never that it looks like anything. The harness now inspects the render
(`screenshot_slide` + Pillow) or the exported file's contents wherever that
is possible, and the first run of those checks found three defects that every
structural check had passed: `build_deck`'s `column: left/right` silently
losing its column when a `y` was also given (both columns drawn on top of
each other at x=0), `replace_image` pointed at a corrupt fixture PNG setting
`file name` while the image vanished from the slide, and
`export_presentation(images, include_skipped=True)` being ignored by Keynote.
Rows below say **RENDERED** where pixels or file contents are asserted, and
say plainly where they cannot be.

## Presentation tools

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `create_presentation` | title, theme?, save_path? | verified *(re-verified P8)* | `make new document with properties {document theme:theme X}`; `set base layout of slide 1 to slide layout "Blank"`; `save … in POSIX file` (unconditional) | Explicit save_path AND the defaulted path (`$KEYNOTE_MCP_SAVE_DIR`/`~/Documents`), file existence, Blank first slide via `get_slide_info`. Filename uniquify/sanitize is unit-tested only. |
| `open_presentation` | file_path | verified *(re-verified P8)* | `/usr/bin/open -a Keynote` (LaunchServices) + AppleScript poll for the document by `file` path — the AppleScript `open` verb WEDGES the AppleEvent queue for files outside Keynote's sandbox container and is never used | Opens from ~/Downloads and ~/Desktop (both outside the container), then proves the queue is still alive with a follow-up query. Phase 3's check passed only because Keynote itself had just saved the file, which leaves a sandbox extension behind. |
| `save_presentation` | doc_name?, save_path? | verified *(re-verified P8)* | `file of targetDoc` guard; `save targetDoc` / `save … in POSIX file` (two-step `POSIX path` read — inline coercion fails -1700) | Plain save on a saved doc; REFUSAL (fast, actionable) on a never-saved doc without save_path — plain save there opens a modal sheet, blocks the queue, then lands in iCloud as Untitled.key; rescue-save of an unsaved doc with save_path. Re-pathing refusal is unit-tested only. |
| `close_presentation` | doc_name?, should_save? | verified | `close … saving yes/no` (Standard Suite) | Close-without-save on saved, unsaved, and reopened docs. |
| `list_presentations` | — | verified | `name of every document` | Name appears after create. |
| `set_presentation_theme` | theme_name, doc_name? | verified | `set document theme of doc to theme X` | Theme switch on a populated deck; not-found path returns guidance. |
| `get_presentation_info` | doc_name? | verified | `name` / `count of slides` / `name of document theme` | Read-back on live doc. |
| `get_available_themes` | — | verified (53 themes) | `name of every theme` | Listing feeds the create/theme checks. |
| `get_slide_size` | doc_name? | verified | `width` / `height` of document | Read-back; feeds the centering check. |

## Slide tools

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `add_slide` | doc_name?, position?, layout? | verified | `make new slide at end/before slide N`; `set base layout to slide layout X` | Append and positional insert; Blank default. |
| `delete_slide` | slide_number, doc_name? | verified | `delete slide N` (guarded by `exists` — Keynote silently no-ops otherwise) | Real delete + count read-back; invalid index (99) returns the actionable -1719/-1728 message, run while the harness's own doc is frontmost. |
| `duplicate_slide` | slide_number, doc_name?, new_position? | verified | `duplicate slide N to after/before …` | Duplicate + count read-back. |
| `move_slide` | from_position, to_position, doc_name? | verified | `move slide N to before/after slide M` (plain `move to slide M` REPLACES M — never used) | Move + count unchanged read-back. |
| `get_slide_count` | doc_name? | verified | `count of slides` | Read-back after every mutation. |
| `select_slide` | slide_number, doc_name? | verified | `set current slide` | Needed by build tools; exercised pre-build. |
| `set_slide_layout` | slide_number, layout, doc_name? | verified | `set base layout of slide N to slide layout X` | Layout switch + get_slide_info read-back; not-found path returns guidance. |
| `get_slide_info` | slide_number, doc_name? | verified *(re-verified P8)* | `slide number` / `name of base layout` / phantom-filtered text item count | Counts only real text items — Keynote's raw `count of text items` includes hidden default title/body placeholder objects (an empty Blank slide reports 0, not 2). |
| `get_available_layouts` | doc_name? | verified | `name of every slide layout` | Listing feeds layout checks. |

## Content tools

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `add_text_box` | slide_number, text, x?, y?, font_size?, font_name?, color?, width?, height?, doc_name? | verified *(re-verified P8)* | `make new text item with properties {object text:…}`; identity loop for the returned index; position applied AFTER sizing; settled geometry read back in the same call | Adversarial-string round-trip; index round-trip (create → move by returned index → read back the same element). Geometry honesty: placed x/y land exactly (position applied after font sizing; text boxes auto-fit around their vertical center when the font size changes from the 48pt default) and the reply's settled position/size matches `get_slide_content` verbatim. |
| `add_title` | + color?, centered? | verified at 96pt — natural auto-fit box, visually exact centering; **RENDERED** | same helper | Index round-trip; exact placement at 36/48/96pt with reply geometry == `get_slide_content`. RENDERED: ink is present inside the box; the 96pt title's rendered ink is ~2x the 48pt one's (the legacy ">48pt truncates" symptom is a render symptom, and the model text stays intact through it); `centered` measured from the ink, not the box — visual text center within 4pt of slide center (measured 511.0 vs 512 at 60pt), the same measurement that exposed the 112pt pre-widening error. |
| `add_subtitle` | + color?, centered? | verified *(re-verified P8)* | same helper | Index round-trip; centering; exact 24pt placement with reply geometry == `get_slide_content`. |
| `add_bullet_list` | items[] | verified *(re-verified P8)* | same helper (joined with real newlines) | Index round-trip; exact multiline placement (4 lines, 24pt) with reply geometry == `get_slide_content`. |
| `add_numbered_list` | items[] | verified *(re-verified P8)* | same helper | Index round-trip. |
| `add_code_block` | + color? | verified; **RENDERED** *(re-verified P8)* | same helper (default Monaco) | Index round-trip; exact placement with reply geometry == `get_slide_content`. RENDERED: a green-colored block renders green glyphs (pixels whose green channel leads red and blue by >25 inside the box) — the `color` argument reaching the drawn text, not just the property. |
| `add_quote` | quote | verified *(re-verified P8)* | same helper (curly quotes) | Index round-trip. |
| `set_slide_content` | slide_number, title?, body?, doc_name? | verified *(re-verified P8)* | `title showing` / `body showing`; `object text of default title item / default body item` | Fill on a **Blank** slide (the create default): enables the placeholder, fills it, read back via get_slide_content. |
| `add_image` | slide_number, image_path, x?, y?, width?, height?, description?, doc_name? | verified; **RENDERED** | `make new image with properties {file:alias}`; identity loop for the returned index | Insert + `images:1` read-back + delete; reply reports index and final geometry, matching `get_slide_content`. RENDERED: a solid-color test bitmap inserted at an explicit size is sampled in the export and must differ from the slide beside it, and must be the color it was given. (The old fixture was a 1x1 half-transparent PNG — sub-pixel on the slide and unverifiable; the harness now generates opaque 160x120 ones.) |
| `get_slide_content` | slide_number, doc_name? | verified *(re-verified P8)* | element counts + per-element details, **phantom-filtered by identity** against default title/body items and their visibility | Five adds report exactly five items, none empty; indices stay live for edit/move/resize/delete. Phase 3 accepted the raw enumeration, which surfaced hidden placeholders as 0x0 empties and showing ones twice. |
| `edit_text_item` | slide_number, item_index, new_text, doc_name? | verified | `set object text of text item N` | Edit + read-back, addressing indices returned by add_*. |
| `delete_element` | slide_number, element_type, element_index, doc_name? | verified | `delete <class> N` (guarded by `exists`) | Image delete + count read-back. |
| `move_element` | + x, y | verified *(re-verified P8)* | `set position` | Half of every index round-trip. |
| `resize_element` | + width, height | verified | `set width` / `set height` | Resize on live item. |
| `get_speaker_notes` | slide_number, doc_name? | verified (unicode round-trip) | `presenter notes` | Unicode round-trip. |
| `set_speaker_notes` | + notes | verified | `set presenter notes` | Unicode round-trip. |
| `clear_slide` | slide_number, doc_name? | verified *(re-verified P8)* | delete shapes + text items **not identical to** the default title/body items (descending index) | Clears five added items to zero; placeholder objects survive. The old empty-text-at-0,0 heuristic misfired both ways. |
| `set_element_opacity` | + opacity | verified; **RENDERED** | `set opacity` (rw on shape/image/text item/movie per sdef) | Opacity change on live shape. RENDERED: a shape drawn ON TOP of a known-color panel is sampled at full opacity and again at 20% — the sampled color must move measurably toward the panel's. Opacity means nothing except what it draws, so a property read-back proved nothing at all. |
| `add_build_in` | slide_number, element_type, element_index, effect?, delivery?, doc_name? | verified live — **NOT verifiable in a render** | System Events UI scripting (Animate inspector) — no AppleScript API exists | Add + remove on a real element; the check is that the tool reports success. **Limitation:** builds do not appear in ANY static export, so no rendered assertion is possible: a build that was never applied looks identical to one that was. The only read-back is UI-scripting the inspector again — verifying UI scripting with UI scripting. Movie export would show them but renders in near-real time. UI scripting is timing-sensitive; a popover can occasionally miss (seen once across runs) — the response reports per-element success. **Phase 10:** `doc_name` was implemented in 4.0.0 and announced in the CHANGELOG but never added to the schema, so the dispatcher rejected it and the capability was unreachable on all three build tools — fixed, and pinned by a schema/signature/dispatch agreement test. |
| `remove_build_in` | same, + doc_name? | verified live — **NOT verifiable in a render** | UI scripting | Paired with add; same limitation as `add_build_in`. |
| `add_builds_to_slide` | slide_number, element_indices, element_type?, effect?, doc_name? | verified live (2 elements) — **NOT verifiable in a render** | UI scripting loop, bullet-dot auto-skip | Batch apply; per-element OK/FAILED status in the response (UI timing flake possible per element). Same limitation as `add_build_in`. |
| `add_shape` | slide_number, x?, y?, width?, height?, opacity?, doc_name? | verified | `make new shape with properties {position, width, height}`; `set opacity`; identity loop for the returned index | Insert with opacity + read-back; reply reports index and final geometry, matching `get_slide_content`. |

## Native object tools (3.0.0)

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `add_table` | slide_number, data[][], x?, y?, width?, height?, header_row?, header_column?, font_name?, font_size?, column_widths?, style?, doc_name? | verified; **RENDERED** | `make new table with properties {row count, column count, header …}` + per-cell `set value` (numbers interpolated post-validation, strings via argv → `=`-strings become live formulas) + range styling from the resolved style; identity-located index | 4×3 table with `=SUM(B2:B3)`: raw cell readback confirms the number stayed numeric, the formula is live (`formula of cell` = `=SUM(B2:B3)`, value = 35), header styled. 2×2 minimum enforced server-side (Keynote raises -10000 below it — probed). RENDERED: the header row's drawn background is the style's header color and differs from a body row's — the styled half of the tool, which cell read-backs cannot see. |
| `add_chart` | slide_number, chart_type, row_names, column_names, data, group_by?, x?, y?, width?, height?, doc_name? | verified; **RENDERED** | Compatibility-Suite `add chart … type <legacy chart type> group by chart row/column`, after `set current slide` (REQUIRED — without it Keynote silently creates nothing, probed); chart located as `chart (count of charts)`; geometry applied after | Chart count read back; geometry read/write. RENDERED, and this is the check the whole hardening pass exists for: a pie built with the WRONG grouping axis (`group_by:"column"` on a single-column spec — the exact input that shipped one 100% slice) must render one distinct fill per slice, with the fill areas ordered by the data (45 > 30 > 25); a bar chart must render one fill per series. Slice fills are found by area against a background ring, NOT by saturation — Slate's second series color is neutral gray (172,172,172), and a saturation filter reports a healthy 3-slice pie as 2. Write-once documented: `chart` class exposes only geometry. |
| `add_line` | slide_number, x1, y1, x2, y2, doc_name? | verified; **RENDERED** | `make new line with properties {start point, end point}`; identity-located index; count-guarded in-script retry | Creation + endpoint semantics probed (endpoints rw). RENDERED: ink runs along the line's path for >85% of its requested length — a line drawn in the background color, zero-length, or off-slide passes every structural check. Root-caused: `make new line` fails DETERMINISTICALLY with -10000 while the Animate inspector is open (as the build tools left it) — the build tools now restore the Format pane, and the harness runs add_line after builds to pin the fix. |
| `add_colored_panel` | slide_number, x, y, width, height, color?, radius?, opacity?, style?, doc_name? | verified; **RENDERED** | Pure-Python rounded-rect PNG (2 px/pt, supersampled corners, no Pillow) placed via the verified image path | Corner transparency and color pinned by unit tests on the PNG bytes. RENDERED: the exported slide is sampled inside the panel (must be the requested RGB within 24/255 — P3 export shifts it by ~2) and just outside it (must not be). The check this replaced compared the reply to the request the harness itself had just sent. Documented as an image, NOT recolorable in Keynote. |
| `style_text_range` | slide_number, item_index, start, end, unit?, color?, font_name?, font_size?, doc_name? | verified | `set color/font/size of characters/words/paragraphs i thru j of object text of text item N` | Chars 1–5 set to #CC0000 + Helvetica-Bold; raw readback: char 2 red+bold, char 9 keeps the THEME color/font (assertion is relative — theme text isn't always dark). **Phase 10:** this remains the EDIT path; `build_deck`'s `runs` is the authoring path, and uses the same AppleScript range write. |
| `replace_image` | slide_number, image_index, image_path, doc_name? | verified; **RENDERED** | `set file name of image N to POSIX file …` (bare-text form raises -1703 — probed); exists-guarded | File name reads back as the new file; geometry preserved (re-probed here: a 200×150 insert stays 150×150 across the swap). RENDERED: the image's center pixel is red before the swap and blue after. The old check asserted only `file name` — metadata — and passed while the harness handed Keynote a CORRUPT PNG (Pillow: "broken data stream"): the property changed and the image vanished from the slide entirely. |
| `set_element_style` | slide_number, element_type (text/image/shape/line), element_index, rotation?, reflection_showing?, reflection_value?, locked?, doc_name? | verified | `set rotation / reflection showing / reflection value / locked` (all rw per sdef; NOT on tables/charts) | Rotation 15° read back exactly; reflection set; unlock exercised for cleanup. |

## New tools (3.1.0 / Phase 9)

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `styled_line` | slide_number, x1, y1, x2, y2, color?, stroke_width?, dash?, start_arrow?, end_arrow?, opacity?, doc_name? | verified; **RENDERED** | Pure-Python transparent-PNG stroke (`utils/stroke.py`, supersampled, dash measured along the segment, arrowhead triangles) placed via the verified image path. Keynote has NO stroke API: a `line`'s complete property record is its endpoints, geometry, rotation, reflection and locked | RENDERED, because a "dotted" line that draws solid passes every structural check: a solid stroke scans as ONE continuous run at 401/401 samples on-colour; a dotted one as 43 runs at 59% coverage; a dashed one as 22 longer runs. Arrowhead presence asserted. Parameters (including endpoint OFFSETS, since the box is padded by half a stroke width plus the arrowhead) are encoded in the filename, so `describe_deck` reports it back as a `styled_line` and `build_deck` re-renders it — the described deck is REBUILT and its panel re-sampled to the same colour. 52 unit tests on the renderer alone. |
| `export_assets` | output_dir, doc_name? | verified; **files inspected** | Reads the saved `.key` bundle directly (zip or directory) and extracts `Data/*`; requires a saved document | `describe_deck` can only report an embedded image's BASENAME once its source is gone (the field report saw 61 elements all named `pasted-movie.png`), so asset inventory needs the file itself. Check asserts the files really landed on disk with non-zero sizes (25 assets, 318,784 bytes), not just that the reply claimed so. Refuses politely on a never-saved document. |

## Declarative deck tools (3.0.0)

| Tool | Args | Status | Mapping | Verification exercises |
|------|------|--------|---------|------------------------|
| `build_deck` | spec? \| markdown?, save_path?, style? | verified; **RENDERED** | Same fragment builders as the per-element tools, batched ~5 slides per osascript session; whole-spec validation first; per-element AppleScript `try`; layout names validated against the live theme (failure deletes the fresh doc) | Bad spec rejected up front with BOTH errors and no document created; 3-slide spec (table+chart+panel+two-column+notes+transition+skipped) builds with 0 element errors; settled geometry in the reply; idempotent re-run replaces the same file; markdown dialect builds (frontmatter, #/##, bullets, GitHub table, Notes:). Benchmark: 20-slide deck = 81 primitive calls/21.8 s vs 1 call/11.9 s/6 sessions — a large call-count win (81 → 1) and a modest wall-clock one (both paths serialize through the same GUI); the claim is fewer round trips and fewer failure points, not speed. E2E: 16-slide deck, 6 sessions, 0 errors. RENDERED, because "0 element errors" is compatible with a deck that looks completely wrong: the built slides are exported and the pie must show one fill per slice, the panel must be the style's color at its coordinates, and `column: left`/`column: right` bullets must put ink in OPPOSITE halves of the slide. That last check found a real defect — a column element that also pinned `y` fell through to fully-manual placement, which set no x, so both columns were drawn on top of each other at x=0 through a clean build and a clean `describe_deck` round-trip (regression-tested in `tests/unit/test_deck_spec.py`). **Phase 10 — strict spec keys:** unknown keys at deck, slide, element AND run level are now rejected with the accepted set named, instead of silently ignored; a spec with a mistyped `layuot`, an invented `fill_color` and a plausible `font` previously built with zero errors, and the render was the only place it showed. Invented-capability keys share one hint table with the tool-argument boundary (`utils/unsupported.py`), so `fill_color` gets the same explanation in a spec as it does as an argument. Keys `describe_deck` emits but Keynote cannot write back (`rotation`, per-element `opacity`, shape `locked`/`reflection_showing`) are ACCEPTED so the round trip still works, and listed in the reply under `not_applied` so tolerating them is not itself a silent drop. **Phase 10 — `runs`:** a text element authors per-run colour/font/size in the same call; RENDERED, because "3 runs" and "describe_deck reports three colours" both pass against a monochrome title — the exported slide must carry three distinct ink colours, then the UNEDITED description is rebuilt and re-sampled with the original deck CLOSED first, so a mistargeted export cannot pass. |
| `describe_deck` | doc_name?, slide_range?, element_types?, detail?, round_coordinates?, include_text_runs? | verified; **PROFILED** | Batched readback (10 slides per osascript session), shared `TEXT_ITEM_FILTER`, per-run styling via `color/font/size of every character` (one Apple event each), `not_reported` block | **Phase 10:** `include_text_runs` was documented in this row, implemented in Python and MISSING FROM THE SCHEMA, so passing it was an error once 4.0.0 started rejecting unknown arguments — now in the schema and forwarded by the dispatcher, with `tests/unit/test_tool_schemas.py` comparing every schema against its method signature and its dispatch call so neither direction can drift again. The tool description was rewritten to the 4.0.0 return shape (hex + `color_65535`, font family/weight/style, `runs`, `placeholder`, rotation/opacity/fill_type, `not_reported`, the index contract); it had still been documenting v3's. **Phase 9.** Profiled on a generated 35-slide/735-element deck BEFORE changing anything: 31.2 s, 125,509 chars, 2,415 trailing `.0`, one osascript call PER SLIDE (~4.5 s of that pure process overhead at 0.125 s x 36). After: `detail='summary'` 0.47 s / 5,946 chars; `slide_range='1-5'` 3.5 s / 17,429 chars; `element_types=['line']` 0.93 s (skipped classes get a loop bound of 0, so their properties are never READ); full path 25.8 s / 0 float noise. 14 live checks assert BOTH wall clock and output size, because the field report hit both walls at once. Emits `element_class` + `index` on every element and the placeholder as a flagged element, so it agrees with `get_slide_content` — proven on a `title showing` slide, the only configuration where they used to disagree. **Limitation:** array position is neither an address nor z-order, and z-order is unrecoverable; both are stated in the output. |

## Slide/document setting tools (3.0.0)

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `set_slide_transition` | slide_number, effect, duration?, delay?, automatic?, doc_name? | verified — **NOT verifiable in a render** | `set transition properties to {transition effect:…, …}` — 43 effects in a trusted literal map | Set push/1.5 s, read back `push|1.5` from `transition properties`. **Limitation:** a transition exists only during playback and is absent from every export, so the property read-back is the ceiling. (PPTX carries an equivalent, but asserting it would test Keynote's converter, not this tool.) |
| `set_slide_skipped` | slide_number, skipped, doc_name? | verified; **RENDERED** | `set skipped` (exists-guarded). Quirk (probed): `skipped:true` inside `make new slide with properties` is silently ignored — must be its own statement | True and false both read back. RENDERED: the exported PDF loses exactly one page while the slide is skipped and regains it with `include_skipped` — the flag's only consequence, asserted where it happens. |
| `set_slide_size` | width, height, doc_name? | verified; **RENDERED** | `set width/height of document` (rw on a LIVE document — probed) | 1024×768 → 1920×1080 read back; reply warns that Keynote rescales layout content. RENDERED: the slide exported after the resize is a 1920×1080 PNG — the document property could change without the export following it. |
| `set_document_settings` | slide_numbers_showing?, auto_loop?, auto_play?, auto_restart?, maximum_idle_duration?, doc_name? | verified | `set slide numbers showing / auto loop / auto play / auto restart / maximum idle duration` | Slide numbers on → read back true → restored. All five probed rw in Phase A. RENDERED: the same slide exported with numbers off and on must differ, and by less than 2% of its pixels (a number appearing, not a layout change). The other four settings affect playback only and have no render to assert. |

## Export tools

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `screenshot_slide` | slide_number, output_path, format?, doc_name? | verified *(re-verified P8)* | `export … as slide images` with per-slide `skipped` save/restore; phantom-aware unfilled-placeholder count | PNG produced AND honesty both ways: a slide with an unfilled placeholder reports "1 unfilled placeholder … NOT rendered"; a fully-filled slide reports "matches the editor view". RENDERED: the PNG is opened — its dimensions equal the slide size and it carries drawn detail (not blank); and the unfilled-placeholder slide's export really is empty, so the warning describes the file rather than being the only thing tested. The export is NOT a faithful editor view — Phase 3 treated a clean image as proof of a clean slide, which the field test showed is false. |
| `export_pdf` | output_path, layout?, image_quality?, include_skipped?, doc_name? | verified (both layouts); **file inspected** | `export … as PDF with properties {export style, PDF image quality, skipped slides}` (trusted literal maps) | Bare PDF and slides_with_notes layout both produced; invalid layout/quality rejected in Python. FILE INSPECTED: page count is read out of the PDF and must equal the slide count, and `include_skipped` must change it by exactly the number of skipped slides (probed: 3 pages vs 4). **Limitation:** the notes LAYOUT itself is not asserted — Keynote's notes pages are a fixed 1024×768 MediaBox, identical to this deck's slide size, so the two layouts are indistinguishable without rasterizing the PDF, which the harness does not do. |
| `export_presentation` | format (pptx/movie/html/images/key09), output_path, movie_format?, image_format?, include_skipped?, doc_name? | verified (pptx/images/html per harness run; movie 360p `.m4v` and key09 produced in the Phase A probes — movie renders near-real-time, too slow for every run); **files inspected** | `export … as Microsoft PowerPoint / QuickTime movie / HTML / slide images / Keynote 09` with per-format options; extensions normalized | FILES INSPECTED, not weighed: the `.pptx` is opened as a zip and must contain one `ppt/slides/slideN.xml` per slide with the deck's title text inside; the images export must produce one PNG per slide at slide size, each carrying drawn detail; the HTML bundle must contain `index.html` plus assets. **Keynote limit (probed at the raw-AppleScript level): `include_skipped` does nothing for the `images` format** — skipped slides are omitted either way, so the tool's reply says so and the harness pins the real behavior instead of the implied one. Use `export_pdf` when skipped slides must appear. Movie timeout 600 s. |

## Runner-level behavior (no single tool)

| Behavior | Status | Verification exercises |
|----------|--------|------------------------|
| Wedged-queue detection | unit-tested only (deliberately not wedged live) | On any osascript timeout, a 3s probe distinguishes a modal dialog from a wedged AppleEvent queue; once wedged, every call fails fast with the `killall Keynote` recovery instead of burning its full timeout. Live wedging would require force-killing the user's Keynote, so this is pinned by `tests/unit/test_sandbox_trap.py`. |

## Unsplash tools (opt-in, `UNSPLASH_KEY`)

| Tool | Args | Status | Mapping |
|------|------|--------|---------|
| `search_unsplash_images` | query, per_page?, orientation?, order_by? | not verified live (no API key on the verification machine); HTTP path unchanged from upstream | Unsplash REST API |
| `add_unsplash_image_to_slide` | slide_number, query, image_index?, … | not verified live; its AppleScript insertion path is identical to the verified `add_image` | REST + `make new image` |
| `get_random_unsplash_image` | slide_number, query?, … | not verified live; same insertion path | REST + `make new image` |

## Removed in this fork (documented removals)

| Tool / behavior | Why |
|------|-----|
| `get_presentation_resolution` | Exact duplicate of `get_slide_size` (both read `width`/`height` of document). One tool, one job. |
| `create_presentation` `template` arg | Accepted but never used by the implementation — dead schema surface. |
| `create_presentation` unsaved-document mode | Phase 8: leaving the new document unsaved armed a trap — the first `save` opens a modal sheet that blocks the AppleEvent queue, after which Keynote completes a default save to iCloud as Untitled.key. Documents are now always saved to an explicit or documented-default path. |
| `open_presentation` via AppleScript `open` | Phase 8: wedges the AppleEvent queue for any file outside Keynote's sandbox container (zero windows, every subsequent event times out, -1712 even at 90s). Replaced with LaunchServices (`open -a Keynote`) + poll. |
| `add_image` movie/clipboard fallbacks | `make new movie` for a PNG and a Finder-copy/paste fallback (which clobbered the user's clipboard) removed; `make new image with properties {file:…}` is verified working on Keynote 14.5. |
| Shape fill color | Never existed here as a tool, and cannot: `background fill type` is read-only in the sdef and there is no fill-color property. `add_shape`'s description documents the opacity workaround. |

## Skill guidance now absorbed by the server (redundant in SKILL.md)

| Skill workaround | Where absorbed |
|------------------|----------------|
| Font clipping (>48pt): add → get index → `resize_element` → `edit_text_item` | Obsolete on Keynote 14.5 in `_add_text_element`'s single-call flow: auto-fit tracks the text at every size (probed 96/150/300/500pt, long/multiline/CJK) and Keynote wraps lines that would outgrow the slide. The earlier ~0.58 px/pt pre-widening (and its explicit height, which auto-fit discards instantly) was removed — it broke `centered` by ~110pt: the box centered while the left-aligned text inside did not. The post-size text re-set is kept as insurance. Callers may still pass explicit `width`/`height`. |
| "Call `select_slide` before `add_build_in` or the popover fails (-2700)" | `add_build_in` / `remove_build_in` issue the slide selection as a separate osascript call internally (`_select_slide_for_ui`). |
| "add_builds_to_slide auto-skips bullet dots" | Already server-side; kept. |
| `color` on add_title/add_subtitle (skill documented it; server lacked it) | Parameter added to both tools. |
| Read width, compute center, `move_element` to center a title | Phase 8: `centered: true` on `add_title`/`add_subtitle` does the math server-side after the final box width is known. |

Still genuinely manual (no AppleScript or accessibility API): connection-line
routing, build-order reordering, "With Previous" build timing.
