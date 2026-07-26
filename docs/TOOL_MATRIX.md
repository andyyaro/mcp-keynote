# Tool matrix — every tool verified against Keynote 14.5

Verified 2026-07-25/26 on macOS 26.5.1, Keynote 14.5 (see `docs/ENVIRONMENT.md`).
Every AppleScript verb/property was checked against `.scratch/keynote.sdef`
(the authoritative dictionary), then executed against a live Keynote via
`.scratch/verify_tools.py` — 57 live checks. "Verified" below means the tool
ran against a real document and its effect was confirmed by reading state back
(`get_slide_content`, file existence, round-trips), not just a non-error exit.

## Presentation tools

| Tool | Args | Status | AppleScript mapping |
|------|------|--------|--------------------|
| `create_presentation` | title, theme?, save_path? | verified | `make new document with properties {document theme:theme X}`; `save … in POSIX file` |
| `open_presentation` | file_path | verified | `open (POSIX file …)` (Standard Suite) |
| `save_presentation` | doc_name? | verified | `save targetDoc` (Standard Suite) |
| `close_presentation` | doc_name?, should_save? | verified | `close … saving yes/no` (Standard Suite) |
| `list_presentations` | — | verified | `name of every document` |
| `set_presentation_theme` | theme_name, doc_name? | verified | `set document theme of doc to theme X` |
| `get_presentation_info` | doc_name? | verified | `name` / `count of slides` / `name of document theme` |
| `get_available_themes` | — | verified (53 themes) | `name of every theme` |
| `get_slide_size` | doc_name? | verified | `width` / `height` of document |

## Slide tools

| Tool | Args | Status | AppleScript mapping |
|------|------|--------|--------------------|
| `add_slide` | doc_name?, position?, layout? | verified | `make new slide at end/before slide N`; `set base layout to slide layout X` |
| `delete_slide` | slide_number, doc_name? | verified | `delete slide N` |
| `duplicate_slide` | slide_number, doc_name?, new_position? | verified | `duplicate slide N to after/before …` |
| `move_slide` | from_position, to_position, doc_name? | verified | `move slide N to before/after slide M` (plain `move to slide M` REPLACES M — never used) |
| `get_slide_count` | doc_name? | verified | `count of slides` |
| `select_slide` | slide_number, doc_name? | verified | `set current slide` |
| `set_slide_layout` | slide_number, layout, doc_name? | verified | `set base layout of slide N to slide layout X` |
| `get_slide_info` | slide_number, doc_name? | verified | `slide number` / `name of base layout` / `count of text items` |
| `get_available_layouts` | doc_name? | verified | `name of every slide layout` |

## Content tools

| Tool | Args | Status | AppleScript mapping |
|------|------|--------|--------------------|
| `add_text_box` | slide_number, text, x?, y?, font_size?, font_name?, color?, width?, height?, doc_name? | verified (incl. adversarial-string round-trip) | `make new text item with properties {object text:…}`; `position`/`width`/`height`; `font`/`size`/`color of object text` |
| `add_title` | + color? | verified at 96pt — clipping bug absorbed | same helper |
| `add_subtitle` | + color? | verified | same helper |
| `add_bullet_list` | items[] | verified | same helper (joined with real newlines) |
| `add_numbered_list` | items[] | verified | same helper |
| `add_code_block` | + color? | verified (green color confirmed in render) | same helper (default Monaco) |
| `add_quote` | quote | verified | same helper (curly quotes) |
| `set_slide_content` | slide_number, title?, body?, doc_name? | verified (new tool) | `title showing` / `body showing`; `object text of default title item / default body item` |
| `add_image` | slide_number, image_path, x?, y?, doc_name? | verified | `make new image with properties {file:alias}` |
| `get_slide_content` | slide_number, doc_name? | verified | element counts + per-element `object text`/`position`/`width`/`height` (+ shape `opacity`) |
| `edit_text_item` | slide_number, item_index, new_text, doc_name? | verified | `set object text of text item N` |
| `delete_element` | slide_number, element_type, element_index, doc_name? | verified | `delete <class> N` |
| `move_element` | + x, y | verified | `set position` |
| `resize_element` | + width, height | verified | `set width` / `set height` |
| `get_speaker_notes` | slide_number, doc_name? | verified (unicode round-trip) | `presenter notes` |
| `set_speaker_notes` | + notes | verified | `set presenter notes` |
| `clear_slide` | slide_number, doc_name? | verified | delete shapes + non-placeholder text items (descending index) |
| `set_element_opacity` | + opacity | verified | `set opacity` (rw on shape/image/text item/movie per sdef) |
| `add_build_in` | slide_number, element_type, element_index, effect?, delivery? | verified live | System Events UI scripting (Animate inspector) — no AppleScript API exists |
| `remove_build_in` | same | verified live | UI scripting |
| `add_builds_to_slide` | slide_number, element_indices, element_type?, effect? | verified live (2 elements) | UI scripting loop, bullet-dot auto-skip |
| `add_shape` | slide_number, x?, y?, width?, height?, opacity?, doc_name? | verified | `make new shape with properties {position, width, height}`; `set opacity` |

## Export tools

| Tool | Args | Status | AppleScript mapping |
|------|------|--------|--------------------|
| `screenshot_slide` | slide_number, output_path, format?, doc_name? | verified (PNG produced, content confirmed visually) | `export … as slide images` with per-slide `skipped` save/restore |
| `export_pdf` | output_path, doc_name? | verified (PDF produced) | `export … to (POSIX file …) as PDF` |

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
| `create_presentation` implicit save-to-Desktop | Writing to `~/Desktop/<title>.key` as a side effect was surprising; replaced with an explicit optional `save_path`. Untitled docs stay unsaved. |
| `add_image` movie/clipboard fallbacks | `make new movie` for a PNG and a Finder-copy/paste fallback (which clobbered the user's clipboard) removed; `make new image with properties {file:…}` is verified working on Keynote 14.5. |
| Shape fill color | Never existed here as a tool, and cannot: `background fill type` is read-only in the sdef and there is no fill-color property. `add_shape`'s description documents the opacity workaround. |

## Skill guidance now absorbed by the server (redundant in SKILL.md)

| Skill workaround | Where absorbed |
|------------------|----------------|
| Font clipping (>48pt): add → get index → `resize_element` → `edit_text_item` | `_add_text_element` auto-sizes the box from text length (~0.58 px/pt per char + buffer) before applying the font size, then re-sets the text to undo any truncation. Verified: 96pt title survives intact. Callers may still pass explicit `width`/`height`. |
| "Call `select_slide` before `add_build_in` or the popover fails (-2700)" | `add_build_in` / `remove_build_in` issue the slide selection as a separate osascript call internally (`_select_slide_for_ui`). |
| "add_builds_to_slide auto-skips bullet dots" | Already server-side; kept. |
| `color` on add_title/add_subtitle (skill documented it; server lacked it) | Parameter added to both tools. |

Still genuinely manual (no AppleScript or accessibility API): connection-line
routing, build-order reordering, "With Previous" build timing.
