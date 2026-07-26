# CEILING.md — what this server can and cannot do, and why

Written 2026-07-26 at v3.0.0, after parsing Keynote 14.5's complete scripting
dictionary programmatically and probing every ambiguous item against a live
Keynote (three probe rounds; evidence in
[CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md), method in the sdef itself —
`docs/keynote-14.5.sdef`). This file exists so nobody burns a day
re-attempting the items in the CANNOT list: each one is there because the
dictionary has no words for it, or because a live probe proved the words
don't work.

## CAN — and does, natively

- **Whole decks in one call**: `build_deck` (JSON or markdown), one
  osascript session per ~5 slides, whole-spec validation before any
  mutation, per-element error isolation, settled geometry reported.
  `describe_deck` reads a deck back to the same spec (diffable; round-trips
  except the two limits below).
- **Text**: boxes, titles, subtitles, bullets, numbered lists, code, quotes;
  font/size/color per item AND per character/word/paragraph range
  (`style_text_range`); exact placement (position applied after Keynote's
  center-anchored auto-fit); server-side horizontal centering.
- **Native tables**: creation with data, live formulas (`=SUM(...)`),
  header/zebra styling, per-range font/size/color/background/alignment/wrap,
  column widths, row heights, merge/unmerge, sort, growable counts.
- **Native charts**: 17 types (bar/line/area/pie/scatter, stacked, 3-D) via
  the legacy `add chart` command — theme-styled and user-editable afterwards.
- **Slides**: add/delete/duplicate/move/select, layouts, skipped flags,
  transitions (all 43 effects with timing), theme title/body placeholders.
- **Document**: create (always saved — the unsaved-doc save sheet is a
  trap), open (LaunchServices only — AppleScript `open` wedges the event
  queue), live slide-size changes, slide numbers, autoplay/loop/restart.
- **Media**: image insertion/replacement (geometry preserved), alt text,
  rotation, reflection, opacity, lock; straight lines with rw endpoints.
- **Export**: PDF (slides / with-notes / handouts, quality, skipped), PPTX,
  QuickTime movie (360p–2160p/native), HTML bundle, per-slide images
  (PNG/JPEG/TIFF), Keynote 09, single-slide screenshots (with placeholder-
  omission honesty).
- **Speaker notes**, styles from `.keynote-mcp.toml` (or built-ins), and —
  via System Events UI scripting only, fragile by nature — build-in
  animations.

## CAN — but only as rendered images (not native, not editable)

AppleScript cannot set any fill color (`background fill type` is read-only —
probed), so **colored panels/cards** are pure-Python-rendered rounded-rect
PNGs placed as images (`add_colored_panel`, and `panel` elements in
`build_deck`). They look native at 2 px/pt but are images: recolor by
replacing, not in Keynote's inspector. Diagram boxes are panels + text +
plain lines composed in z-order.

## CANNOT — confirmed, do not re-attempt

Every item is (P) probed live with the recorded error, or (D) absent from
the dictionary (no term exists to even compile; representative compile
errors probed).

| Wanted | Why it's impossible | Workaround shipped |
|---|---|---|
| Shape/text fill color | (P) `background fill type` read-only, no color property (-10006 both routes) | `add_colored_panel` rendered PNGs; opacity on the theme fill |
| Text alignment (center/right) on text items | (P) -10006; alignment exists only on table ranges | server-side `centered` box placement |
| Hyperlinks | (P) no class; `make new hyperlink` → -2753 | none — link text is inert |
| Grouping / ungrouping | (P) `make new group` silently creates nothing (iWork items 0→0); moving into a group → -1719 | build in paint order; move pieces together |
| Z-order control | (P) `move … to front` → -10024; z-order = creation order, forever | spec order IS z-order in `build_deck` |
| Duplicating elements across/within slides | (P) "Text items can not be copied" (-1717) | recreate from parameters; duplicate whole slides |
| Non-rectangle shapes (oval, arrow, star…) | (P) no `shape type` term (syntax error) | rendered images |
| Inserting movies / audio | (P) `{file:…}` coercion error; `{file name:…}` silent no-op (0 items) | none — hand-place in Keynote |
| Editing chart data after creation | (P) `chart` class exposes only geometry | delete + `add_chart` again |
| 1-row or 1-column tables | (P) "Invalid row/column count" (-10000); floor is 2×2 | 2×2 with blanks |
| Build animations / order / "With Previous" | (D) no terms | UI-scripting tools (fragile: English UI, Accessibility, unlocked screen, focus) |
| Connection lines (routed connectors) | (D) `line` has fixed endpoints only | straight `add_line` |
| Borders, strokes, shadows (incl. table cell borders) | (D) no terms | render into the panel PNG if essential |
| Per-slide backgrounds | (D) no term on `slide`; layouts are read-only | pick a theme/layout that has it; full-bleed panel image |
| Creating/editing layouts or themes | (D) `slide layout` exposes `name` only | author `.kth` themes in Keynote by hand |
| Line spacing, paragraph spacing, kerning, bullet glyphs/indents | (D) rich text has only color/font/size | accept theme defaults |
| Bold/italic as attributes | (D) no style attribute | switch `font` to the bold/italic face name (this IS shipped, per range) |
| Reading placeholder geometry from a layout | (D) layouts opaque | observe after a slide uses the layout |
| Reading chart data (for describe_deck) | (P/D) nothing readable | described charts are geometry-only |
| Skipped slides in an **image** export | (P) `skipped slides:true` is ignored by the slide-images export — identical file counts either way (probed at the raw-AppleScript level); the same property works for PDF | `export_pdf(include_skipped=true)`, or unskip first; `export_presentation` says so in its reply |
| Original file path of embedded images | (P) after the source file is gone, only the basename survives | describe_deck falls back to the basename and says so |

## Scriptable but deliberately unexposed

Judged low-value for a model building decks; the sdef surface is probed and
documented in CAPABILITY_MATRIX.md if someone later disagrees:
playback control (`start`/`stop`/slide switcher), document passwords
(`set password`/`remove password` — probed working), `make image slides`
(bulk photo decks; probed, adds surprising extra slides), `.kth` custom
themes via `make new document with data` (unprobed — no `.kth` can be
created by script), `print`.

## Operational limits (not API limits)

- One osascript call at a time; a modal Keynote dialog blocks everything
  (bounded timeouts + wedge detection ship in the runner).
- UI-scripting build tools need Keynote frontmost, an unlocked screen, an
  English UI, and tolerate occasional timing misses.
- With the Animate inspector open, `make new line` fails deterministically
  with -10000 "AppleEvent handler failed" (other creates keep working). The
  build tools restore the Format pane when they finish; if you drive the
  inspector by hand mid-session, switch back to Format before adding lines.
- Movie export renders in near-real time (minutes for real decks).
- TCC permissions attach to the app that launched the server.
