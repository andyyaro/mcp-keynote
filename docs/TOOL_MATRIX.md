# Tool matrix — every tool verified against Keynote 14.5

First verified 2026-07-25/26 on macOS 26.5.1, Keynote 14.5 (see
`docs/ENVIRONMENT.md`); re-verified 2026-07-26 after the Phase 8 field-test
fixes. Every AppleScript verb/property was checked against the Keynote
scripting dictionary (tracked at `docs/keynote-14.5.sdef`), then executed
against a live Keynote via `scripts/verify_tools.py` — **109 live checks, 0
failed** (last full run 2026-07-26, after the geometry-honesty fix).
"Verified" below means the tool ran against a real document and its
effect was confirmed by reading state back (`get_slide_content`, file
existence, round-trips), not just a non-error exit.

**Lesson from the field test (Phase 8):** the Phase 3 harness only exercised
documents it created itself with an explicit `save_path`, so several tools
were marked "verified" while failing on the paths real callers take (the
untitled-document save, opening a foreign file from outside Keynote's sandbox
container, trusting the returned element index). Each row now states what its
verification actually exercises; rows whose original status was happy-path
only are marked *(re-verified P8)*.

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
| `add_title` | + color?, centered? | verified at 96pt — natural auto-fit box, visually exact centering *(re-verified 2026-07)* | same helper | Index round-trip; text intact at 96pt with NO pre-widening (auto-fit probed live at 96/150/300/500pt); `centered` verified against rendered pixels: visual text center == slide center within 4pt at 24/48/96pt (live test); exact placement at 36/48/96pt with reply geometry == `get_slide_content`. |
| `add_subtitle` | + color?, centered? | verified *(re-verified P8)* | same helper | Index round-trip; centering; exact 24pt placement with reply geometry == `get_slide_content`. |
| `add_bullet_list` | items[] | verified *(re-verified P8)* | same helper (joined with real newlines) | Index round-trip; exact multiline placement (4 lines, 24pt) with reply geometry == `get_slide_content`. |
| `add_numbered_list` | items[] | verified *(re-verified P8)* | same helper | Index round-trip. |
| `add_code_block` | + color? | verified (green color confirmed in render) *(re-verified P8)* | same helper (default Monaco) | Index round-trip; color render; exact placement with reply geometry == `get_slide_content`. |
| `add_quote` | quote | verified *(re-verified P8)* | same helper (curly quotes) | Index round-trip. |
| `set_slide_content` | slide_number, title?, body?, doc_name? | verified *(re-verified P8)* | `title showing` / `body showing`; `object text of default title item / default body item` | Fill on a **Blank** slide (the create default): enables the placeholder, fills it, read back via get_slide_content. |
| `add_image` | slide_number, image_path, x?, y?, doc_name? | verified | `make new image with properties {file:alias}`; identity loop for the returned index | Insert + `images:1` read-back + delete; reply reports index and final geometry, matching `get_slide_content`. |
| `get_slide_content` | slide_number, doc_name? | verified *(re-verified P8)* | element counts + per-element details, **phantom-filtered by identity** against default title/body items and their visibility | Five adds report exactly five items, none empty; indices stay live for edit/move/resize/delete. Phase 3 accepted the raw enumeration, which surfaced hidden placeholders as 0x0 empties and showing ones twice. |
| `edit_text_item` | slide_number, item_index, new_text, doc_name? | verified | `set object text of text item N` | Edit + read-back, addressing indices returned by add_*. |
| `delete_element` | slide_number, element_type, element_index, doc_name? | verified | `delete <class> N` (guarded by `exists`) | Image delete + count read-back. |
| `move_element` | + x, y | verified *(re-verified P8)* | `set position` | Half of every index round-trip. |
| `resize_element` | + width, height | verified | `set width` / `set height` | Resize on live item. |
| `get_speaker_notes` | slide_number, doc_name? | verified (unicode round-trip) | `presenter notes` | Unicode round-trip. |
| `set_speaker_notes` | + notes | verified | `set presenter notes` | Unicode round-trip. |
| `clear_slide` | slide_number, doc_name? | verified *(re-verified P8)* | delete shapes + text items **not identical to** the default title/body items (descending index) | Clears five added items to zero; placeholder objects survive. The old empty-text-at-0,0 heuristic misfired both ways. |
| `set_element_opacity` | + opacity | verified | `set opacity` (rw on shape/image/text item/movie per sdef) | Opacity change on live shape. |
| `add_build_in` | slide_number, element_type, element_index, effect?, delivery? | verified live | System Events UI scripting (Animate inspector) — no AppleScript API exists | Add + remove on a real element. UI scripting is timing-sensitive; a popover can occasionally miss (seen once across runs) — the response reports per-element success. |
| `remove_build_in` | same | verified live | UI scripting | Paired with add. |
| `add_builds_to_slide` | slide_number, element_indices, element_type?, effect? | verified live (2 elements) | UI scripting loop, bullet-dot auto-skip | Batch apply; per-element OK/FAILED status in the response (UI timing flake possible per element). |
| `add_shape` | slide_number, x?, y?, width?, height?, opacity?, doc_name? | verified | `make new shape with properties {position, width, height}`; `set opacity`; identity loop for the returned index | Insert with opacity + read-back; reply reports index and final geometry, matching `get_slide_content`. |

## Export tools

| Tool | Args | Status | AppleScript mapping | Verification exercises |
|------|------|--------|--------------------|------------------------|
| `screenshot_slide` | slide_number, output_path, format?, doc_name? | verified *(re-verified P8)* | `export … as slide images` with per-slide `skipped` save/restore; phantom-aware unfilled-placeholder count | PNG produced AND honesty both ways: a slide with an unfilled placeholder reports "1 unfilled placeholder … NOT rendered"; a fully-filled slide reports "matches the editor view". The export is NOT a faithful editor view — Phase 3 treated a clean image as proof of a clean slide, which the field test showed is false. |
| `export_pdf` | output_path, doc_name? | verified (PDF produced) | `export … to (POSIX file …) as PDF` | File existence + size. |

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
