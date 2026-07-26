# STYLE_SYSTEM.md — `.keynote-mcp.toml`, and what a real design system exposed

Written 2026-07-26 (Phase 9 Task 9). The style system had only ever been tested
with input invented for it. This file records what happened when it was handed
a **real** one: `tokens.json` from a 35-slide technical architecture deck,
reverse-engineered by someone who had never seen this code.

**Verdict up front.** The flat 27-scalar schema could express **3** of that
system's ~60 concepts. Five named vocabularies were added, and the shipped
`sdh` built-in now carries **22 type roles, 24 palette colours, 8 semantic
connectors, 4 canvas zones and 8 grid modules**. What remains unexpressable is
listed at the bottom, with the reason for each — most are Keynote's ceiling,
not the schema's.

---

## The schema

A style is a TOML file (`.keynote-mcp.toml`) or a built-in name. Scalars are
unchanged from 3.0.0. Five keys take **tables**:

```toml
[style]
name = "sdh"
keynote_theme = "Basic White"
width = 1920
height = 1080

# 1. TYPE ROLES — named text styles, referenced by `role` on an element.
[style.type."label.service"]
font = "HoeflerText-Regular"
size = 22
color = "#000000"

# 2. PALETTE — colour as a referent. Reference it as "@name".
[style.palette]
"zone.private" = "#98C1DA"
"accent.deep"  = "#830041"

# 3. CONNECTORS — semantic strokes, referenced by `connector` on a styled_line.
[style.connectors.data]
color = "#8A2052"
width = 5
dash = "solid"
meaning = "Retrieve / Update"

# 4. ZONES — named canvas bands, referenced by `zone` on an element.
[style.zones.legend]
x = 0
y = 1016
width = 1920
height = 44

# 5. MODULES — an n-up grid with a real gutter (pitch != width).
[style.modules.accountColumn3up]
width = 351
height = 540
pitch = 356
origin_x = 27
origin_y = 119
```

Using them in a spec:

```json
{"type": "text",        "text": "Lambda", "role": "label.service"}
{"type": "panel",       "module": "accountColumn3up", "index": 2, "color": "@zone.private"}
{"type": "styled_line", "x1": 400, "y1": 820, "x2": 900, "y2": 820, "connector": "data"}
{"type": "text",        "text": "Account Isolation", "zone": "title", "role": "title.canvas"}
```

`index: 2` on that module resolves to `x = 27 + 356 = 383` — the coordinate a
spec previously had to hand-compute for every column of every diagram.

**Unknown names fail up front**, with the whole spec, listing what the style
*does* define. The style is resolved **before** `validate_spec` for exactly
this reason: a misspelt `@zone.privte` must not surface on slide 23 mid-build.

## What this bought, measured

Every value below came from the style, not the spec:

| The spec said | The style supplied |
|---|---|
| `role: "title.canvas"` | LibreCaslonCondensed-Medium, 69pt, `#000000` |
| `role: "chip.badge"` | HoeflerText-Black, 15pt |
| `module: accountColumn3up`, `index: 1,2,3` | x = 27, 383, 739; 351×540 |
| `color: "@zone.private"` | `#98C1DA` |
| `connector: "data"` | `#8A2052`, 5pt, solid |
| `connector: "denied"` | `#AAAAAA`, 3pt, dotted |
| `connector: "logStream"` | `#F19AC8`, 4pt, dotted |

The connector rows only became possible in this same phase: before
`styled_line` existed there was nothing to apply a stroke style *to*, so a
connector vocabulary would have been documentation pretending to be a feature.

## Still not expressable, and why

Split by whose limitation it is. **Nothing here is silently dropped** — a style
file that tries to express one of these gets a loud unknown-key error.

### Keynote's ceiling (no schema change would help — see CEILING.md)

| Concept | Why |
|---|---|
| Gradients (`surface.panel`, `stepBadge`) | The renderer draws flat colour; Keynote cannot fill anything at all |
| Paper texture on the concept palette | Same — and it is called the deck's most distinctive material property |
| Drop shadows (`notePanel`) | No shadow term on any iWork class |
| Underline (`card.title`, `heading.diagram`, the title convention) | Rich text exposes only font, size, colour |
| `transform: uppercase` (`chip.badge`) | No text-transform; author the capitals in the string |
| Circles (`stepBadge`, circular personas) | No `shape type`; non-rectangles are images |
| Dotted `boundary` rectangles, `dataObjectChip` outlines | No stroke on shapes; bake it into the PNG |
| Table gridlines / `highlightStroke` | No cell-border term |
| Orthogonal connector **routing** | `line` has fixed endpoints; no routing terms |
| Per-slide backgrounds (`color.dark.bg`) | No background term on `slide` |
| `layerOrder` as a *guarantee* | Z-order is creation order and cannot be changed. The style cannot enforce it; spec order IS paint order |

### Schema gaps deliberately left open

| Concept | Why not now |
|---|---|
| **Component macros** (`accountChip` = panel + text, `notePanel`, `stepBadge`) | The clear next step. Each is currently 2-3 hand-placed elements. Needs a macro-expansion pass in `_element_fragment` that emits several elements in paint order; deferred rather than half-built |
| **Per-slide furniture** (signature mark, legend rail "required on every diagram slide") | Needs an array-of-elements field appended per slide, plus a rule for which slides. Same expansion machinery as macros |
| **Per-slide style override** (the dark evidence archetype) | `resolve_style` runs once per deck. One slide of 35 needs it; not worth a second resolution path yet |
| **Icon size classes** | Trivial to add (`[style.icons] architecture = 85`), but only meaningful once images can be placed by role |
| **Conditional rules** (`highlightRule`: white on a gray panel, accent on white) | The schema is declarative; a rule engine is a different thing |
| **`title.deck` `color: "multi"`** | Per-word colour is authorable via `style_text_range` and now READABLE via text runs, but it is a property of one string, not of a style |
| **`motion.rule`** (magic move needs ≥80% shared geometry) | Not checkable without comparing rendered slides |

### Fixed in passing

`accent_color` was a dead key — defined on `DeckStyle`, referenced by no code
path. The palette supersedes it: a design system has 9 named accents, not one.

## Rules for extending this

1. A new vocabulary is a **table**, and its entry keys are declared in
   `_MAP_ENTRY_KEYS`. Unknown keys must be rejected — a silently ignored
   `colour` is the same failure class as a silently dropped tool argument.
2. Validate colours **at load**, including `@` references, so a typo surfaces
   when the style is read and not on slide 23.
3. If a token cannot be applied, do not add a key for it. A style key that
   loads and does nothing is worse than an honest gap — it manufactures a
   capability, which is the exact failure this phase started by fixing.
