# keynote-mcp — connector issues & improvement notes

Logged while reverse-engineering `Project Architecture Presentation.key` (35 slides, 1920×1080, ~800 elements).

---

## 🔴 Bugs / correctness risks

### 1. "front document" default silently targets the wrong presentation
**Severity: high — produces confidently wrong output.**

`open_presentation` opened the target deck, but several later calls that omit `doc_name`
resolved to a *different* deck that happened to be frontmost in Keynote
(`platform-review-q3.key`). `screenshot_slide` cheerfully returned
`"No unfilled placeholders; the export matches the editor view."` for slides that belonged
to another presentation entirely. Nothing in the response indicated which document was used.

Repro:
1. Have 2+ presentations open in Keynote.
2. `open_presentation("A.key")`
3. `screenshot_slide(slide_number=1)` → may render slide 1 of `B.key`.

**Fix suggestions**
- Echo the resolved document name in *every* tool response
  (`"…of slide 1 of 'Project Architecture Presentation.key'"`). Cheap, and makes the bug self-evident.
- Make `open_presentation` return a stable handle/`doc_name` and have the server remember it as
  the session default, instead of re-resolving "front document" per call.
- Or: warn when >1 document is open and `doc_name` was omitted.

### 2. `describe_deck` blows the tool-output token limit with no way to page
137,091 characters / 7,189 lines for a 35-slide deck — hard-failed and got spilled to a file.
There is no `slides="1-10"`, no `include=[...]`, no `detail=summary|full`.

**Fix suggestions**
- Add `slide_range` (e.g. `"1-10"`) and/or `element_types=["text","line"]` filters.
- Add `detail: "summary"` mode returning per-slide counts + titles only.
- Round floats to ints by default (every coordinate is `679.0`, not `679`) — ~8% of the payload is `.0`.

---

## 🟡 Missing data — blocks real design-system work

`describe_deck` returns these keys and nothing more:

| type  | keys returned |
|-------|---------------|
| text  | `x y width height text font_name font_size color` |
| shape | `x y width height opacity text` |
| line  | `x1 y1 x2 y2` |
| image | `x y width height path` |
| table | `x y width height data header_row header_column` |

Gaps that mattered for this task:

1. **Shape fill / stroke / corner radius / rotation are not exposed.** This deck's entire visual
   language is colored account containers (pink `#EFA3A0`, blue `#A8C6DE`, mint `#D8EDD2`,
   slate `#5C6E80`, maroon `#8E1F55`). I had to recover every one of those colors by
   screenshotting and eyeballing pixels. `set_element_style` can *write* fills — but there is no
   read path, so a describe→edit→build round-trip loses all fill information.
2. **Line color / width / dash pattern / arrowheads are not exposed.** This deck encodes meaning
   in stroke style (dotted black = logical/API call, solid grey = federation, dotted pink =
   denied/blocked, thick black = human action). `describe_deck` returns only endpoints, so the
   semantics are invisible.
3. **Shape *type* is not exposed** — a rounded rect, an arrow, a callout and a circle all come back
   as `"shape"`. Can't tell a container from a connector-arrow.
4. **Z-order / layering is implicit** in array position but undocumented. Diagram slides layer
   container → icon → label → connector; without a documented ordering guarantee a rebuild
   scrambles the stack.
5. **Groups are flattened.** Slide 4 has 15 shapes + 19 images that are visually 4 account
   containers. No group ids, so grouping intent is unrecoverable.
6. **Text runs are flattened to one font/color per box.** Slide 1's title mixes three colors in one
   line ("Building A" black / "Secure" maroon / "Client Data Hub" salmon), and body panels
   highlight keywords in white mid-paragraph. `describe_deck` reports a single `color` per text
   item, so it under-reports the real palette. `style_text_range` can write ranges — again, no read path.
7. **Placeholder title text is separated from its styling.** `slide.title` returns the string but no
   font/size/color, while non-placeholder text items get full styling. Inconsistent, and it means
   the deck's most important type style (the H1) is undiscoverable via the API.
8. **Image `path` is a bare filename**, not a resolvable path — 61 elements are all
   `pasted-movie.png`. No dimensions-on-disk, no way to distinguish them, no extraction.
   An `export_assets` tool (dump the `.key` bundle's Data/ folder) would make asset inventory possible.
9. **`opacity` is returned for shapes but not for images or text.**

---

### 3. `describe_deck` exceeds the 120 s tool timeout on a 35-slide deck
Second invocation took >120 s and was pushed to a background task. Combined with issue 2, the
single most useful tool in the server is unusable on a real deck without two workarounds.
Likely fixable with the same paging/filtering as above.

### 4. Text-item indices disagree between `describe_deck` and `get_slide_content`
On slide 1, `get_slide_content` reports 6 text items (index 1 = the theme title placeholder);
`describe_deck` reports 5 elements of type `text` (placeholder excluded, surfaced as `slide.title`).
So the same text is item **2** in one tool and element **1** in the other — and this offset only
exists on slides that use the title placeholder, so it isn't even a constant. `style_text_range`
and `edit_text_item` take the `get_slide_content` numbering, which means anyone who plans edits
from a `describe_deck` dump will silently restyle the wrong element on ~half the deck.

**Fix:** use one numbering. Either include the placeholder as an element in `describe_deck`
(with a `placeholder: "title"` flag) or exclude it from `get_slide_content`. Whichever — document it.

---

## 🔴 Write-side gaps that block reproducing a real design system

The read gaps above are annoying. These are blocking.

### 5. Shape fill color cannot be set — and lines cannot be styled at all
`add_shape` documents it plainly: *"fill color cannot be set via AppleScript; use opacity over
themed backgrounds instead."* `add_line` takes `x1,y1,x2,y2` and nothing else — no color, no
width, no dash, no arrowhead.

For this deck that is fatal to programmatic reproduction. Its entire visual language is
(a) colored account zones and (b) **connector strokes whose color and dash pattern carry meaning**
— dotted black = invocation, solid maroon = data path, solid grey = auth, dotted pink = log stream.
None of that can be authored through the API. A `build_deck` run gets you correct *geometry* and
then a human has to open Keynote and style every one of 165 lines by hand.

`add_colored_panel` is a smart workaround for fills (render a PNG, place it as an image) and it
works — but it's one-way: the result is an image, not a recolorable shape, and `describe_deck`
reports it back as `type: "image"` with a generated filename, so the color is lost on round-trip.

**Fix suggestions**
- Apply the `add_colored_panel` trick to lines too: a `styled_line` tool that renders the stroke
  (color / width / dash / arrowheads) to a transparent PNG and places it. Ugly, but it would make
  the semantic stroke language authorable, which is the difference between "generates a layout"
  and "generates a deck".
- Have `add_colored_panel` stash its color in the image's filename or in a sidecar map so
  `describe_deck` can report `panel_color` and the round-trip survives.
- Document the fill/stroke limitation in `build_deck`'s description too — it's currently only
  mentioned on `add_shape`/`add_colored_panel`, so a `build_deck`-first user (which the tool
  description actively encourages: "START HERE") hits it late.

### 6. Z-order is creation-order and cannot be changed
Noted in `add_colored_panel`'s description. Correct and honest, but it means one mis-ordered
element requires rebuilding the slide. A `send_to_back` / `bring_to_front` would save a lot of
rework; if AppleScript genuinely can't, say so in `build_deck` too.

---

## 🟡 Color format

Colors come back as 16-bit-per-channel comma strings: `"65528,65535,65525"`, `"33665,0,16829"`.
Every consumer has to divide by 257 and hex-encode. Suggest returning `"#FFFFFF"` /
`"#830041"` (or adding a `hex` field alongside), and documenting the 0–65535 range where it is kept.

## 🟡 Font naming

`font_name` is the PostScript name (`LibreCaslonCondensed-Medium`, `HoeflerText-Black`,
`TimesNewRomanPSMT`). Useful for round-tripping, but a `family` + `weight` + `style` split would
make consistency auditing (the whole point of this task) far easier than string-munging
`sub("-.*";"")`.

---

## 🟢 Things that worked well

- `describe_deck` → edit → `build_deck` round-trip is genuinely the right primitive; the spec
  format is legible and diffable.
- `open_presentation` via LaunchServices handled `~/Downloads` with no sandbox friction.
- The `screenshot_slide` note about omitted unfilled placeholders is a thoughtful touch —
  exactly the kind of caveat that prevents a wrong conclusion.
- `get_slide_size` returning derived safe-area/margin/center is a nice affordance.

---

## 🟢 Things that worked well (continued)

- `style_text_range` operating on characters/words/paragraphs is exactly the right granularity,
  and the note that Keynote has no bold/italic attribute (pass the face name instead) saved a
  wasted attempt. All five font fixes in this session went through it cleanly on the first try.
- `add_colored_panel`'s description explains *why* it renders a PNG instead of pretending the
  limitation doesn't exist. More tools should do this.
- `build_deck`'s framing ("1 call vs 81") is the right argument and the markdown dialect is a nice
  on-ramp.

---

## Suggested priority

1. **Echo resolved `doc_name` in every response.** Cheap; prevents silently-wrong output. Highest
   value-to-effort ratio on this list by a wide margin.
2. **A `styled_line` that renders stroke color/dash/arrowheads.** Without it the server can lay out
   a technical diagram but cannot draw one, because in real architecture diagrams the stroke *is*
   the semantics.
3. Unify text-item indexing between `describe_deck` and `get_slide_content` *(silent wrong-element
   edits today)*.
4. Paging/filtering on `describe_deck` *(unblocks decks >20 slides; also fixes the 120 s timeout)*.
5. Expose shape fill + line stroke on read *(unblocks describe→build fidelity)*.
6. Hex colors + font family/weight split *(ergonomics)*.
7. Group ids and documented z-order *(diagram fidelity)*.
