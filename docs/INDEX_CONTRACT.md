# INDEX_CONTRACT.md — one numbering for every element index

Written 2026-07-26 (Phase 9 Task 2) after an exhaustive audit of every tool
that emits or consumes an element index, plus a live probe of how Keynote
actually numbers text items.

This file exists because the same class of bug has now shipped twice. Phase 8.2
fixed it per-instance for the `add_*` tools; it came back in `describe_deck`.
The rule below is the fix, and the cross-tool round-trip checks in
`scripts/verify_tools.py` are what keep it fixed.

---

## The contract, in one paragraph

**Every element index in this server is Keynote's raw, 1-based, PER-CLASS
AppleScript index** — `text item i`, `image i`, `shape i`, `table i`,
`chart i`, `line i` of a slide. Indices are per class, so `text item 1` and
`image 1` both exist and mean different objects. An index emitted by ANY tool
addresses the same object when passed to ANY tool that accepts one for that
class. Theme placeholders are **represented, not hidden**: a showing
placeholder is a real, addressable element that carries a `placeholder`
role, and only its phantom repeat is suppressed.

---

## What Keynote actually does (probed, Keynote 14.5)

`count of text items` is untruthful: the slide's `default title item` and
`default body item` occupy slots in the text-item space. Three configurations
were probed directly (`.scratch/probe_task0_*`, and the probe reproduced in
`fragments.TEXT_ITEM_FILTER`'s comment):

| Slide state | `text item` enumeration |
|---|---|
| both placeholders hidden | `real-A(1)`, `real-B(2)`, `[hidden title](3)`, `[hidden body](4)` |
| title showing | **`TITLE(1)`**, `real-C(2)`, `TITLE-again(3)`, `[hidden body](4)` |
| both showing | **`TITLE(1)`, `BODY(2)`**, `real-D(3)`, `TITLE-again(4)`, `BODY-again(5)` |

Two facts follow, and one previously documented invariant is **wrong**:

1. A **hidden** placeholder trails (0×0, empty text, position 0,0).
2. A **showing** placeholder takes a LEADING slot *and* appears again trailing.
3. Therefore CLAUDE.md's "real items always come first, so real indices are
   stable" holds **only while both placeholders are hidden**. With a showing
   title, every real index shifts by one. This is exactly why the offset the
   field report saw was not constant.

`count of iWork items` IS truthful (showing placeholders + real items), and
placeholders were **not** observed among `shapes` on Keynote 14.5 — though the
sdef types them as `shape`, so both readers guard the shape loop by identity
anyway.

## The canonical filter

Defined once, in `fragments.TEXT_ITEM_FILTER`, and consumed by every reader so
they cannot drift apart:

| Occurrence | Verdict |
|---|---|
| first occurrence of a **showing** placeholder | **REAL**, flagged `role = "title"` / `"body"` |
| repeat occurrence of a showing placeholder | PHANTOM — skipped |
| any occurrence while **hidden** | PHANTOM — skipped |
| anything else | REAL, `role = ""` |

---

## Emitters

Every one of these reports the per-class index defined above.

| Tool | Emits | Class |
|---|---|---|
| `add_text_box` / `add_title` / `add_subtitle` / `add_bullet_list` / `add_numbered_list` / `add_code_block` / `add_quote` | `text item index N` | text item |
| `add_image`, `add_colored_panel` | `image index N` | image |
| `add_shape` | `shape index N` | shape |
| `add_table` | `table index N` | table |
| `add_line` | `line index N` | line |
| `add_chart` | `chart index N` | chart |
| `get_slide_content` | `TEXT:i`, `IMAGE:i`, `SHAPE:i`, `TABLE:i` (+ `role:` on text) | per class |
| `describe_deck` | `element_class` + `index` on **every** element (+ `placeholder` role) | per class |
| `build_deck` | `elements[].index` in its report | per class |

`add_*` tools locate their index by **object identity**, never by a count —
`make new text item` does not append last in the text-item index space, so
reporting the count as the index would be wrong whenever a phantom trails.
The one exception is `add_chart` (`fragments.py`), which uses `count of charts`
because the Compatibility-Suite `add chart` command returns nothing to compare
identity against; charts have no phantoms, and the call is count-guarded.

## Consumers

| Tool | Argument | Classes accepted |
|---|---|---|
| `edit_text_item` | `item_index` | text item |
| `style_text_range` | `item_index` | text item |
| `delete_element`, `move_element`, `resize_element`, `set_element_opacity` | `element_index` | text, image, shape, table |
| `set_element_style` | `element_index` | text, image, shape, line |
| `replace_image` | `image_index` | image |
| `add_build_in`, `remove_build_in`, `add_builds_to_slide` | `element_index(es)` | text, image, shape |

> `add_unsplash_image_to_slide`'s `image_index` is **not** an element index —
> it is a 0-based ordinal into an HTTP search result. Different universe,
> different base. Do not confuse it with `replace_image`'s `image_index`.

## How placeholders are represented

- `describe_deck` emits a showing placeholder as an ordinary element carrying
  `"placeholder": "title"` or `"body"`, with its real per-class `index`. It is
  addressable: passing that index to `edit_text_item` edits the placeholder.
- `slide.title` / `slide.body` remain in the spec, carrying the same text, so
  a described deck still rebuilds through `build_deck`'s placeholder path.
  They are a **derived convenience**, not a second numbering.
- `get_slide_content` emits the same element with `role:title` / `role:body`.
- Hidden placeholders appear in neither reader, and occupy no reported index.

## Array position is NOT an address

`describe_deck`'s `elements[]` is built by walking each class in turn (text,
image, shape, table, chart, line), so **array position is not an element
index and is not slide z-order**. Use the `index` + `element_class` fields to
address an element. This is why every element now carries them explicitly.

## Guards

An index that is merely *stale* addresses a different object rather than none,
so a caller working from an out-of-date listing edits the wrong element and is
told it succeeded. Every index-consuming tool now checks `exists` first and
raises -1719 otherwise (`fragments.exists_guard`). Before Phase 9 only
`delete_element`, `replace_image` and `set_element_style` did.

## Rules for new code

1. A new tool that emits an index reports the **per-class AppleScript index**,
   located by identity, and says which class it belongs to.
2. A new reader uses `fragments.TEXT_ITEM_FILTER`. Do not hand-roll the
   placeholder predicate — two hand-rolled copies is exactly how this broke.
3. A new tool that consumes an index guards with `fragments.exists_guard`.
4. Add the emit→consume pair to the round-trip checks in
   `scripts/verify_tools.py`, **on a slide with `title showing`**. The Phase 3
   and Phase 8 harnesses only ever tested Blank slides, where both
   placeholders are hidden — the one configuration in which the bug cannot
   appear. That is why both tools were marked "verified" while disagreeing.

## Known remaining asymmetries (documented, not fixed)

- `add_chart` emits `chart index N`, but no tool consumes a chart index and
  `get_slide_content` does not list charts. The index is real but currently
  only useful to `describe_deck`.
- `add_line` emits `line index N`; only `set_element_style` accepts a line.
  Lines cannot be deleted/moved/resized by index.
- `set_element_style` rejects `table`/`chart` because the sdef has no
  rotation/reflection on them, not because of an index problem.
