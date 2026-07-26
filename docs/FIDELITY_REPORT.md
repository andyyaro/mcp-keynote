# FIDELITY_REPORT.md — the server against a real deck, measured in pixels

Phase 9 Task 8. The source material is a real 35-slide technical architecture
deck (`.scratch/SDH-Visual-Identity/`), its 18 exported reference slides, and
the `build_deck` starter template someone wrote from it after
reverse-engineering the design system. The source deck and its BACKUP sibling
were opened by nothing in this exercise; the reference PNGs are the baseline.

Artifacts: `.scratch/phase9_task8_pixels.py`, `.scratch/phase9_task8_hardest.py`,
exports and side-by-side comparisons under `.scratch/phase9-task8*/`.

---

## First: the template's own header is now half wrong

`templates/starter-deck.json` opens with a CRITICAL CONSTRAINT block. Three
claims, and Phase 9 settled each:

| Template claim | Verdict |
|---|---|
| "shape fill color READ-ONLY … every colored zone MUST be built as `type:'panel'`" | **Correct.** Re-probed at v3.1.0: 12 write routes × 5 themes, all -10006/-2740, raw four-char-code chevrons included, render byte-identical. The PNG panel really is the only way. |
| "z-order follows creation order and cannot be changed — emit panels BEFORE the icons and text" | **Correct**, and still the rule. |
| **"CONNECTORS CANNOT BE STYLED PROGRAMMATICALLY … has to be applied by hand in Keynote"** | **No longer true.** `styled_line` renders the stroke (colour, width, dash, arrowheads) and places it, and the parameters survive a `describe_deck` round trip. A template telling users to hand-style 165 connectors is now sending them to do work the server does. |

**That block should be updated.** It is the single most load-bearing paragraph
in the template, and a third of it now misleads.

## Build 1 — the template, as written

`./templates/build.sh | build_deck` → **3 slides, 0 element errors.** The
template is valid and builds clean.

Scoping stated up front rather than discovered in the numbers: the template's
**7 image assets do not exist** (`assets/hero-3d.png`, three AWS service icons,
persona, signature) — they are placeholders for a real project. Neutral grey
stand-ins were generated so the build could proceed, so icon pixels cannot
match and the raw-difference percentages below are dominated by that.

### Slide 1 — A1 deck title

| | |
|---|---|
| Mean per-band ink difference | 0.060 |
| Raw pixels differing >24/255 | 67.3% |

**Matches:** presenter name (italic Libre Caslon, same position and size), the
"View GitHub Repository:" line, both contact lines, and the copyright — all
land where the original has them.

**Does not match, and why:**

1. **The title is in the wrong place.** The original centres
   "Building A Secure Client Data Hub" at y≈817. The template sets the slide's
   `title:`, which fills the *theme placeholder*, and the theme puts it at the
   top. **Placeholder geometry is not readable or settable** — layouts are
   opaque (CEILING.md). The fix is to author the title as a positioned text
   element instead of a placeholder; the template's choice is the problem, but
   the API gives no way to move a placeholder.
2. **The title is monochrome.** The original mixes three colours in one line.
   See "the run-authoring gap" below.
3. The 3-D cloud hero and the theme's gradient background are absent
   (placeholder asset; per-slide backgrounds have no API).

### Slide 2 — A2 section divider

| | |
|---|---|
| Mean per-band ink difference | 0.041 |
| Raw pixels differing >24/255 | **13.0%** |

The closest match of the three, which makes sense: it is mostly type and one
panel, and both reproduce well.

### Slide 3 — A4 request flow (the diagram archetype)

| | |
|---|---|
| Mean per-band ink difference | 0.047 |
| Raw pixels differing >24/255 | 55.0% |

**The colour evidence is the point here.** Dominant colours, built vs the
original deck's own export:

| Zone | Built | Reference | Δ |
|---|---|---|---|
| control / slate | `(113,127,143)` | `(110,128,145)` | (3,1,2) |
| public / mint | `(229,245,223)` | `(225,246,221)` | (4,1,2) |
| private / blue | `(160,192,215)` | `(152,193,218)` | (8,1,3) |

**The rendered panels reproduce the deck's real zone colours to within 8/255**,
through Keynote's Display-P3 export. The three-column container layout, the
account chips, the service labels and the legend rail all land.

One real defect surfaced: the template's `layout: "Title"` on this slide puts a
**giant title placeholder straight through the diagram** ("Re…" at 150pt across
the persona). Same root cause as slide 1 — placeholder geometry is not
controllable, and a diagram slide should not use a title placeholder at all.

## Build 2 — the hardest archetype, with everything Phase 9 added

Layered account containers **+ semantic connector strokes + a mixed-colour
title**: the three things the template calls impossible. Built with the `sdh`
style, `styled_line` and `style_text_range`. **0 element errors.**

**All three now reproduce:**

1. **Layered containers** — same palette match as above, spec order giving
   correct paint order (containers, then chips, then labels, then strokes).
2. **Semantic strokes** — five distinct meanings, read back from the built deck:

   | Meaning | Read back |
   |---|---|
   | logical / invocation | `#000000` dotted 3pt |
   | data / retrieve-update | `#8A2052` solid 5pt |
   | dataReturn | `#8A2052` dotted 3pt |
   | denied | `#AAAAAA` dotted 3pt |
   | logStream | `#F19AC8` dotted 4pt |

   With arrowheads, plus a legend rail pairing each stroke with its label —
   the deck's own convention.
3. **Mixed-colour title** — `describe_deck` reads back runs at
   `#000000` / `#8A2052` / `#EFA3A0`, matching the original's
   black / maroon / salmon.

## What still cannot be reproduced through the API

Honestly separated into *Keynote's ceiling* and *this server's remaining gaps*.

### Keynote's ceiling (no amount of work here fixes these)

| | |
|---|---|
| **Theme placeholder geometry** | Cannot be read or set; layouts are opaque. A design that puts its H1 at y=817 must not use the title placeholder at all. This caused the single largest visual difference in the whole exercise. |
| **Per-slide backgrounds / gradients** | No term on `slide`. The original's soft grey gradient is the theme's. |
| **Icons, 3-D renders, illustrated glyphs** | Must be supplied as image files. Nothing generates them. |
| **Orthogonal connector routing** | `line` has fixed endpoints; `styled_line` draws straight. The original routes connectors around obstacles — every one of those is a hand edit or a pre-rendered PNG. |
| **Underline** | The deck underlines every slide title. Rich text exposes only font, size, colour. |
| **Grouping** | 15 shapes + 19 images that are visually 4 containers stay 34 loose elements. |
| **Textures, drop shadows, circles/badges** | No fill API, no shadow term, no `shape type`. |

### This server's remaining gaps (fixable, not fixed)

1. **`build_deck` cannot author text runs.** `style_text_range` can write them
   and `describe_deck` can now read them, but a spec cannot express them — so
   the deck's signature tri-colour title needs a build call plus three styling
   calls, and a described deck with runs does not rebuild with its runs. This
   is the clearest asymmetry left in the API and the obvious next task.
2. **No component macros.** The account chip (panel + inverse text) is two
   hand-aligned elements every time; the design system calls it one component.
   See docs/STYLE_SYSTEM.md.
3. **Connector endpoints are hand-computed.** `styled_line` takes coordinates,
   not "from element A to element B" — and since z-order is creation order,
   there is no element identity to attach to anyway.

## Summary

| Archetype | Layout | Colour | Type | Strokes |
|---|---|---|---|---|
| A1 deck title | placeholder misplaces the H1 | ✅ | ✅ (runs need extra calls) | n/a |
| A2 section divider | ✅ | ✅ | ✅ | n/a |
| A4 request flow | ✅ | ✅ within 8/255 | ✅ | ✅ all five meanings |

The server reproduces this deck's **geometry, palette, typography and stroke
semantics**. What it cannot reproduce is what Keynote will not expose:
placeholder positions, backgrounds, routing, underline, grouping, and the
artwork itself.
