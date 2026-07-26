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

## Fill color: re-probed at v3.1.0 and still impossible (Phase 9 Task 0)

An external field report asserted that `set_element_style` **can** write shape
fill, which would have made `add_colored_panel`'s PNG workaround obsolete —
this repo has twice shipped a workaround that outlived its cause, so the claim
was treated as probably true until probed. It is false. Evidence
(`.scratch/probe_task0_fill.py`, `.scratch/probe_task0_results.json`):

- **12 write routes × 5 themes** (White, Black, Gradient, Slate, Bold Color),
  including raw four-char-code chevrons that bypass the dictionary's access
  flags: every one fails. `set background fill type … to color fill` → -10006;
  `set background color` → -10006; `set color` → -10006; `set «class bkft» to
  «constant ****fico»` → -10006; `set fill color` / `set background fill` are
  not even terms (-2740 compile errors).
- **Nothing is hidden.** `properties of shape 1` returns the complete record,
  and it is exactly the sdef's: `opacity, parent, class, reflection showing,
  background fill type, position, object text, width, rotation, reflection
  value, height, locked`. No fill color, no `shape type`, no `corner radius`,
  no stroke. The `line` record is equally bare: `start point, end point,
  position, width, height, rotation, reflection showing, reflection value,
  locked, parent, class` — **no stroke color, width, dash, or arrowheads**,
  which is why `styled_line` must render a PNG.
- **The pixels agree.** A shape's rendered interior is byte-identical before
  and after all five write attempts.
- **The read side works** and is worth exposing: `background fill type` returns
  one of `no fill / color fill / gradient fill / advanced gradient fill /
  image fill / advanced image fill`. So `describe_deck` can honestly report
  *that* a shape is filled and with what KIND of fill — never with what color.

**Where the false belief came from, and the real defect it exposed.** Every
tool schema accepted unknown arguments and `_dispatch` read only the names it
knew, so `set_element_style(fill_color="#EFA3A0")` was **dropped and reported
as success** — indistinguishable from working. That is now a hard error naming
the accepted arguments and the right alternative
(`server._reject_unknown_arguments`, `additionalProperties: false` stamped on
every schema centrally in `all_tools()`). A silently ignored argument is worse
than a rejected one; it manufactures capabilities.

### The one native filled rectangle that does exist (and why it isn't the default)

Table **cell** `background color` is rw (it is a `range` property, not an
iWork-item one). A 3×3 table with header/footer counts zeroed and
`merge selection range` over `A1:C3` collapses to a single cell and renders as
a **perfectly uniform, borderless colored rectangle** (measured: 240,000 of
240,000 pixels one color). It is native, recolorable in Keynote's inspector,
and round-trippable — everything the PNG panel is not. It is still not the
default, for four measured reasons:

1. **The color is wrong by ~6%.** Requested `#EFA3A0`, rendered `(244,179,175)`
   after converting the export out of Display P3 — off by (+5,+16,+15). The
   same color through `add_colored_panel`'s renderer lands on `(239,163,160)`,
   i.e. **exactly** `#EFA3A0`. Reproduced on merged and unmerged cells, with
   and without header rows, so it is inherent to `background color`, not to
   `merge`. Cause not determined. *This also means `add_table`'s header/zebra
   colors do not render as the exact hex requested.*
2. No corner radius, so no rounded panels.
3. `merge` is rejected on a 2×2 (-10000); the working floor is 3×3.
4. It is semantically a table — it lands in `count of tables`, exports as a
   table, and a reader of the deck sees a table.

Recorded because it is a real option for a caller who needs a *recolorable*
zone and can accept an approximate color; `add_colored_panel` stays the
default because it is exact and supports radius.

## CANNOT — confirmed, do not re-attempt

Every item is (P) probed live with the recorded error, or (D) absent from
the dictionary (no term exists to even compile; representative compile
errors probed).

| Wanted | Why it's impossible | Workaround shipped |
|---|---|---|
| Shape/text fill color | (P) `background fill type` read-only, no color property; **re-probed Phase 9**: 12 routes × 5 themes all -10006/-2740, raw chevrons included, render unchanged, `properties` record has no fill key | `add_colored_panel` rendered PNGs (colorimetrically exact); opacity on the theme fill; merged-table cell for a recolorable-but-inexact zone |
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
| Borders, strokes, shadows (incl. table cell borders) | (D) no terms; **re-probed Phase 9**: a `line`'s COMPLETE property record is start/end point, position, width, height, rotation, reflection showing/value, locked, parent, class — no colour, thickness, dash or arrowheads | `styled_line` renders the stroke to a transparent PNG and round-trips via its filename; render into the panel PNG for shape borders |
| Per-slide backgrounds | (D) no term on `slide`; layouts are read-only | pick a theme/layout that has it; full-bleed panel image |
| Creating/editing layouts or themes | (D) `slide layout` exposes `name` only | author `.kth` themes in Keynote by hand |
| Line spacing, paragraph spacing, kerning, bullet glyphs/indents | (D) rich text has only color/font/size | accept theme defaults |
| Bold/italic as attributes | (D) no style attribute | switch `font` to the bold/italic face name (this IS shipped, per range) |
| Reading placeholder geometry from a layout | (D) layouts opaque | observe after a slide uses the layout |
| Reading chart data (for describe_deck) | (P/D) nothing readable | described charts are geometry-only |
| Skipped slides in an **image** export | (P) `skipped slides:true` is ignored by the slide-images export — identical file counts either way (probed at the raw-AppleScript level); the same property works for PDF | `export_pdf(include_skipped=true)`, or unskip first; `export_presentation` says so in its reply |
| Original file path of embedded images | (P) after the source file is gone, only the basename survives | describe_deck falls back to the basename and says so |

## Read-side limits (Phase 9 Task 4, probed)

`describe_deck` emits a `not_reported` block listing exactly these, with every
full description, so a caller can tell **"no fill"** from **"fill not
reported"** without guessing. What IS newly readable:

- **Per-run text styling.** `color of every character`, `font of every
  character` and `size of every character` each return the WHOLE list in ONE
  Apple event (probed). Three events per text item buys full run fidelity;
  the naive read would be one event per character. Runs are coalesced in
  AppleScript so the payload stays small. **Runs are now also AUTHORABLE** —
  see "Runs, which turned out not to be a ceiling at all" below.
- `background fill type` — the KIND of fill (`no fill` / `color fill` /
  `gradient fill` / `advanced gradient fill` / `image fill` /
  `advanced image fill`). Never the colour.
- `rotation`, `opacity`, `reflection showing`, `locked` on shapes, text items,
  images and lines; `description` (alt text) on images.
- `count of groups` per slide — so a group a user made BY HAND is reported
  rather than silently flattened. Its members remain unenumerable.

What is NOT readable, and is stated in the output rather than omitted: shape
fill colour, shape type, corner radius, any stroke, line stroke, text
alignment, underline, chart data, slide background, group membership, and
z-order.

**Z-order deserves its own note.** `describe_deck` enumerates class by class
(text, then image, then shape, table, chart, line), so **array position is
neither an element address nor paint order**. Every element therefore carries
an explicit `element_class` + `index` (see INDEX_CONTRACT.md). Keynote's real
z-order is creation order and AppleScript can neither read nor change it — a
described deck rebuilt from its own output will paint in class order, which
for a layered diagram means panels landing on top of their own labels unless
the spec is reordered by hand.

## Runs, which turned out not to be a ceiling at all (Phase 10)

`build_deck` used to state, in its own tool description, "NO PER-RUN COLOR
HERE. An element has one font/size/color." That was true of the code and false
of Keynote. It was never probed — it was inferred from the spec format not
having a field for it, which is not evidence about the application.

The write route always existed and `style_text_range` had been using it since
3.0.0: `set color of characters S thru E of object text of <item>`. Inside
`build_deck` the created item is still in scope, so a run costs **AppleScript
lines, not Apple events** — the tri-colour title below adds four lines to a
session that was already running. `runs` is now a field on every text-bearing
element, in the same shape `describe_deck` reports, so a mixed-colour heading
survives describe → build.

Two things worth keeping:

1. **Keynote renders text through a colour profile.** An authored `#830041`
   lands at ~(138,37,82) on the canvas, not (131,0,65). This is not a write
   error, and the way to know that is that the ORIGINAL hand-made deck renders
   the same maroon at (138,32,82) — five levels away on one channel. A rendered
   check comparing against the value it *sent* will fail on a correct write;
   compare against what the application actually paints.
2. **Runs must be written after the element's own text and colour, and before
   its position.** Re-setting `object text` discards every run, a box-level
   `set color of object text` flattens them, and a run that changes size
   re-triggers auto-fit — which keeps the box's vertical CENTRE fixed, so a
   position set earlier drifts. Same invariant the box-level sizing already
   obeyed, now with a third thing sequenced inside it.

The general lesson is the one this file exists for and got wrong in its own
pages: **a limit of the code is not a limit of the application**, and only the
CANNOT list here is probe-backed. Anything asserted as impossible without a
probe belongs in a TODO, not in a ceiling.

## Theme placeholder geometry (Phase 9 Task 8)

A slide's `title`/`body` fill the theme's placeholders **wherever the layout
puts them**. Their position and size cannot be read or set — layouts are
opaque. This produced the single largest visual difference when reproducing a
real deck: the design centres its H1 at **y≈543** — just past the vertical
middle of a 1080pt canvas — while the theme placeholder puts it at the top, and
on a diagram slide a title placeholder runs straight through the diagram. **If
a design places its heading at a specific point, author it as a positioned text
element, not as `title`.**

The 543 is measured, twice: the H1's ink occupies rows 480–607 of the reference
export (1920×1080, so 1px = 1pt), centre 543.5; `describe_deck` reports the box
as `y=461, h=158`, centre 540. The ~3pt gap is the box's internal leading, not
disagreement. (Earlier revisions of this file and FIDELITY_REPORT.md cited
y=817, which was never measured from anything.)

## Scriptable but deliberately unexposed

Judged low-value for a model building decks; the sdef surface is probed and
documented in CAPABILITY_MATRIX.md if someone later disagrees:
playback control (`start`/`stop`/slide switcher), document passwords
(`set password`/`remove password` — probed working), `make image slides`
(bulk photo decks; probed, adds surprising extra slides), `.kth` custom
themes via `make new document with data` (unprobed — no `.kth` can be
created by script), `print`.

## UI state affects scripting

Keynote's scripting layer is not independent of its window. What the app is
showing — which inspector pane is open, which slide is current, which slides
are flagged skipped, whether it is frontmost — changes what AppleScript
commands do, and **nothing in the dictionary lets a script read or set most
of it**. This is a class, not a single bug, and it has three properties worth
internalizing:

1. **The failure looks transient and is not.** The known instance below was
   first written off as a flake because an isolated repro passed — the repro
   never opened the inspector. It reproduced 100% of the time once the
   inspector was open, and 0% otherwise; the ordering of the full run was the
   whole variable.
2. **The blast radius crosses tools.** The tool that changes the state and
   the tool that then fails need have nothing to do with each other.
3. **A user with Keynote open is part of the system.** Anyone clicking around
   in Keynote while the server runs can put it in the failing state, and no
   amount of server-side care prevents that. The server can only avoid
   *causing* it and say so when it can't.

**Known instance (probed).** With the **Animate inspector** open,
`make new line` fails deterministically with -10000 "AppleEvent handler
failed". Other `make new …` classes keep working, which is what makes it so
misleading. The build tools (`add_build_in`, `remove_build_in`,
`add_builds_to_slide`) are the only things here that open that pane, and they
now switch the inspector back to Format when they finish
(`_restore_format_pane`, best-effort — UI state must never fail the call it
rides along with). If you drive the inspector by hand mid-session, switch
back to Format before adding lines.

**Mitigation pattern — for any tool that changes app or document state the
caller did not ask to change:**

- Restore it, and restore it in a `finally`, from state captured in **Python**
  rather than in an AppleScript variable. A single script that mutates and
  restores loses the restore entirely if the script is killed by a timeout or
  a modal dialog. `screenshot_slide` marks every slide skipped to isolate one
  slide for export; it reads the flags in one call, exports in another, and
  restores in a `finally` — because an export that outlives its timeout used
  to leave the user's deck with every slide skipped, after which exports
  produce nothing and playback shows nothing, with no hint why.
- Make the restore best-effort and log loudly if it fails; never let cleanup
  turn a working call into a failed one.
- Where the state change is the point (the `add_chart` / `build_deck` switch
  of `current slide`, which Keynote requires or it silently creates nothing;
  `select_slide`), leave it changed and say so in the tool description.

## Operational limits (not API limits)

- One osascript call at a time; a modal Keynote dialog blocks everything
  (bounded timeouts + wedge detection ship in the runner).
- UI-scripting build tools need Keynote frontmost, an unlocked screen, an
  English UI, and tolerate occasional timing misses.
- Scripting outcomes depend on Keynote's visible UI state, which no tool
  fully controls — see "UI state affects scripting" above for the class, the
  known `make new line` / Animate-inspector instance, and the restore pattern.
- Movie export renders in near-real time (minutes for real decks).
- TCC permissions attach to the app that launched the server.
