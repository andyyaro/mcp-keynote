---
name: keynote-presentation
description: Creates polished Keynote presentations via keynote-mcp MCP tools. Use when user says "create a presentation", "make slides", "build a deck", or mentions Keynote. Handles font clipping bugs, theme pitfalls, coordinate math, build animations, and landing-page-style slide design. Do NOT use for PowerPoint or Google Slides.
license: MIT
metadata:
    author: ByAxe
    version: 3.0.0
    mcp-server: keynote-mcp
    category: productivity
    tags: [keynote, presentations, slides, mcp]
---

# Keynote Presentation Builder

Build polished Keynote presentations using keynote-mcp MCP tools. This skill encodes domain expertise about Keynote's AppleScript quirks, layout math, and design patterns.

## Multi-slide decks: use build_deck first (server 3.x)

For any deck of more than ~2 slides, call **`build_deck`** with one JSON
spec (or its markdown dialect) instead of issuing per-element calls: the
whole spec is validated before anything is created, each element failure is
reported individually, and the reply carries every element's settled
geometry. Pass `style` (`plain`/`boardroom`/`midnight`/`editorial`, or a
`.keynote-mcp.toml` path) so fonts/colors/margins come from one place.
Two-column layouts: give elements `"column": "left"` / `"right"`.
Element order in the spec is z-order (put `panel` elements before the text
that sits on them). `describe_deck` reads any open deck back as the same
JSON. Native `add_table` (live `=SUM(…)` formulas, min 2×2) and `add_chart`
(17 native types; data is write-once — delete and re-add to change it) beat
drawing tables/charts out of text boxes. Colored panels are RENDERED
IMAGES (fill color is not scriptable) — not recolorable in Keynote after
placement. What the server cannot do at all is listed in docs/CEILING.md —
don't attempt hyperlinks, grouping, z-reordering, movie/audio insertion, or
per-text alignment.

The per-element workflow below remains correct for touch-ups of existing
decks.

## Font Sizes (server 2.x absorbs the clipping bug)

Since keynote-mcp 2.0 large fonts just work — pass `font_size=96` and the
server lets Keynote's auto-fit box hug the rendered text and restores any
truncated text itself. For horizontally centered titles/subtitles pass
`centered=true` (visually exact, pixel-verified at 24/48/96pt) instead of
computing x yourself — and don't combine centering with a manual `width`,
which would offset the left-aligned text inside the wider box. You can still
pass explicit `width`/`height` to `add_text_box` to control wrapping. Verify
with a screenshot as usual.

(On server 1.x the old manual workaround was: add → `get_slide_content` →
`resize_element` → `edit_text_item`; see `references/font-size-workaround.md`.)

## Workflow

### Step 1: Setup
```
get_slide_size()
get_available_themes()
create_presentation(title="...", theme="Slate")
set_slide_layout(slide_number=1, layout="Blank")
```
- Use **Slate** theme by default (dark gradient, works on Blank layout)
- Always set slides to **Blank** layout — themed layouts inject invisible placeholders
- See `references/theme-reference.md` for full compatibility table

### Step 2: Batch-create slides
Add all slides before content to avoid index confusion:
```
add_slide(position=2)
add_slide(position=3)
```

### Step 3: Add content
- Center text manually: `x = 960 - (char_count * px_per_char / 2)`
- See `references/coordinate-reference.md` for width estimates per font size
- See `references/slide-templates.md` for hero, statement, bullets, code, and closing patterns
- Use `references/shape-and-styling.md` for containers, colors, and two-column layouts

### Step 4: Verify every slide
CRITICAL: Always screenshot and visually inspect after building each slide.
```
screenshot_slide(slide_number=N, output_path="/tmp/slideN.png")
```
Read the image. Check for:
- Text clipping (only 1-2 characters visible)
- Element overlaps (compare y + height vs next element y)
- Content overflowing slide edges
- Alignment issues

Fix with `move_element`, `resize_element`, or `edit_text_item`.

### Step 5: Build animations (optional)
Add click-to-reveal effects so content appears incrementally during presentation:
```
get_slide_content(slide_number=N)
add_builds_to_slide(slide_number=N, element_indices="5,7,9,11,13")
```
- **Never build shapes** — container shapes are structural, always visible
- Auto-skips bullet dot items ("•")
- Requires Keynote frontmost + Accessibility permissions
- ~6 seconds per element (UI scripting)
- See `references/build-animation-reference.md` for details

## Design Principles

Treat each slide as one section of a landing page. **One idea per slide.**

Maximum content per slide:
- 1 title + 1 subtitle + 3-5 bullets, OR
- 1 title + 1 code block (6 lines max), OR
- 1 centered quote/statement

### Font hierarchy
| Size | Use |
|------|-----|
| 96pt | Hero title only (needs resize workaround) |
| 64-72pt | Section titles |
| 48pt | Large statements/quotes |
| 28-32pt | Subtitles |
| 24-26pt | Body text, bullets |
| 20pt | Code blocks |
| 18pt | Footnotes, captions |

### Recommended fonts
- Titles: "Helvetica Neue Bold"
- Subtitles: "Helvetica Neue Light"
- Code: "Menlo"

## Working with Existing Presentations

When adding to an existing deck:
1. `duplicate_slide(slide_number=N)` — preserves theme/background
2. `clear_slide(slide_number=M)` — removes content, keeps background
3. Build new content on the cleared slide

See `references/existing-presentation-guide.md` for patterns.

## Element Management

- Always `get_slide_content` before modifying elements
- Delete from **highest index to lowest** to avoid index shifting
- Theme placeholder ghosts at (0,0) cannot be deleted — ignore them
- Calculate overlaps: if element at y=300 has height=638, it extends to y=938

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Text shows 1-2 chars | Server 2.x prevents this; on old servers: resize_element + edit_text_item |
| No background visible | Use Slate, Bold Colour, or Basic Black |
| Elements overlap | get_slide_content → check heights → move_element |
| MCP old behavior | Restart server (/mcp) |
| add_build_in popover error | Server 2.x selects the slide itself; retry once, then check Accessibility permission |

See `references/troubleshooting-and-limitations.md` for detailed limitations and known issues.

## Performance Notes
- Take your time with each slide. Quality is more important than speed.
- Do not skip the screenshot verification step.
- When in doubt about coordinates, use get_slide_content to check actual positions.

## Quick Reference Checklist
1. `get_slide_size` → confirm dimensions
2. `get_available_themes` → pick theme (Slate recommended)
3. `create_presentation` with theme
4. Add all slides, set to Blank layout
5. Build content using templates from `references/slide-templates.md`
6. For large or centered titles: pass `font_size`/`centered=true` directly (server 2.x needs no resize/edit follow-up)
7. Screenshot each slide → Read image → verify
8. Fix overlaps: get_slide_content → calculate → move_element
9. Add build animations if needed
10. Final screenshot pass of all slides
