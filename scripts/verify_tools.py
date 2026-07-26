"""Live verification: run every tool against a real Keynote.

Phase 3 built the original happy-path coverage; Phase 8 added the regression
checks for what a field test showed that coverage missed: the untitled-
document save path, opening files from outside Keynote's sandbox container
(~/Downloads and ~/Desktop), index round-trips for every add_* tool, phantom
placeholder filtering, screenshot placeholder honesty, server-side centering,
and geometry honesty (placed coordinates land exactly despite Keynote's
center-anchored auto-fit; add_* replies match get_slide_content).

The pre-merge hardening pass added RENDERED checks. A pie chart once shipped
rendering as a single 100% slice while its live check (`count of charts is
1`) passed: on a tool that draws something, counts and property read-backs
prove an object exists, never that it looks like anything. Every visual tool
that CAN be checked in pixels now is - chart slice counts, panel and table
header colors, image bitmaps, text ink and clipping, opacity, slide numbers,
theme repaints - and the export artifacts are opened and inspected (PDF page
counts, pptx slide parts, image dimensions) instead of being weighed. The
two classes that no export can show (build animations, transitions) are
called out in docs/TOOL_MATRIX.md rather than dressed up.

Creates documents only under .scratch/ (plus one temporary copy on ~/Desktop
for the outside-sandbox open check, removed afterwards), closes them without
saving user data, and prints one PASS/FAIL line per check.

WARNING: this drives Keynote's UI - it takes window focus, and during the
build-animation checks anything you type lands in the test presentation.
Don't touch the keyboard while it runs (~2 minutes).

Usage:  uv run python scripts/verify_tools.py
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter  # dev dependency; rendered checks are not optional

REPO = Path(__file__).resolve().parents[1]
SCRATCH = REPO / ".scratch"
sys.path.insert(0, str(REPO / "src"))

# Default-save location for create_presentation without save_path: point it at
# .scratch so the harness never writes into the real ~/Documents.
os.environ["KEYNOTE_MCP_SAVE_DIR"] = str(SCRATCH)

from keynote_mcp.tools.content import ContentTools  # noqa: E402
from keynote_mcp.tools.deck import DeckTools  # noqa: E402
from keynote_mcp.tools.export import ExportTools  # noqa: E402
from keynote_mcp.tools.objects import ObjectTools  # noqa: E402
from keynote_mcp.tools.presentation import PresentationTools  # noqa: E402
from keynote_mcp.tools.slide import SlideTools  # noqa: E402

# Test bitmaps are generated, opaque and visibly sized. The base64 blobs
# they replace were a 1x1 half-transparent red and a 1x1 BROKEN PNG ("broken
# data stream" - Pillow will not decode it). replace_image happily pointed
# Keynote at the broken one and the image vanished from the slide, while the
# shipped check ("file name reads back verify-blue") passed.
TEST_IMAGE_PX = (160, 120)
RED = (220, 40, 40)
BLUE = (40, 70, 220)

RESULTS = []


def record(name, ok, message=""):
    RESULTS.append((name, ok, message))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {message[:160]}")


def text_of(result):
    return result[0].text


def check(name, result, expect_substring=None, forbid_failure=True):
    text = text_of(result)
    ok = True
    if forbid_failure and (text.startswith("Failed") or "error" in text[:40].lower()):
        ok = False
    if expect_substring is not None and expect_substring not in text:
        ok = False
    record(name, ok, text.replace("\n", " | "))
    return text


# --- rendered assertions -------------------------------------------------
# Everything below inspects what Keynote actually DREW (or what an exported
# file actually CONTAINS), not what it reports about itself. A pie chart once
# rendered as a single 100% slice while `count of charts is 1` passed: on a
# tool that produces something visual, a structural check proves only that an
# object exists, never that it looks like anything. Renders cost ~1-2 s each,
# so they are batched: one export, many assertions.

RENDER_DIR = SCRATCH / "render"


async def render_slide(export, slide_number, tag, slide_w, doc_name=""):
    """Export one slide and return (RGB image, pixels-per-point).

    Returns (None, 0.0) and records a FAIL if the export did not happen, so a
    missing render can never make a rendered check silently pass.
    """
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    path = RENDER_DIR / f"{tag}.png"
    path.unlink(missing_ok=True)
    reply = text_of(await export.screenshot_slide(slide_number, str(path), doc_name=doc_name))
    if "Captured screenshot" not in reply or not path.exists():
        record(f"render slide {slide_number} for '{tag}'", False, reply[:140])
        return None, 0.0
    image = Image.open(path).convert("RGB")
    return image, image.width / float(slide_w)


def at(image, scale, x, y):
    """Color of the rendered pixel at slide point (x, y)."""
    px = min(max(int(x * scale), 0), image.width - 1)
    py = min(max(int(y * scale), 0), image.height - 1)
    return image.getpixel((px, py))


def near(a, b, tol=8):
    return all(abs(int(p) - int(q)) <= tol for p, q in zip(a, b, strict=False))


def dominant(image):
    """The most common pixel color in an image (or crop)."""
    colors = image.getcolors(image.width * image.height)
    return max(colors, key=lambda c: c[0])[1]


def _crop(image, scale, box):
    x, y, w, h = box
    return image.crop(
        (int(x * scale), int(y * scale), int((x + w) * scale), int((y + h) * scale))
    )


def _ink_mask(image, tol=24, radius=6):
    """Pixels that differ from a blurred copy of themselves.

    Themes paint gradients (Slate's background spans ~60 shades), so
    "differs from the background color" flags the entire slide - it reported
    the 96pt title as 1024pt wide. A high-pass against the image's own blur
    sees only what has edges: glyphs, rules, chart segments, object borders.
    Flat interiors are invisible to it, so solid fills (panels, images,
    shapes) are checked by sampling their color instead.
    """
    diff = ImageChops.difference(image, image.filter(ImageFilter.GaussianBlur(radius)))
    r, g, b = diff.split()
    channel_max = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return channel_max.point(lambda v: 255 if v > tol else 0)


def ink_bbox(image, scale, box=None, tol=24):
    """Bounding box in SLIDE POINTS of the drawn detail in a region.

    ``box`` is (x, y, w, h) in points; the result is in slide coordinates.
    Returns None when nothing was drawn.
    """
    ox, oy = (box[0], box[1]) if box else (0.0, 0.0)
    region = _crop(image, scale, box) if box else image
    bb = _ink_mask(region, tol).getbbox()
    if not bb:
        return None
    return (ox + bb[0] / scale, oy + bb[1] / scale, ox + bb[2] / scale, oy + bb[3] / scale)


def ink_fraction(image, scale, box=None, tol=24):
    """Share of the region covered by drawn detail."""
    region = _crop(image, scale, box) if box else image
    total = region.width * region.height
    return (_ink_mask(region, tol).histogram()[-1] / total) if total else 0.0


def fill_areas(image, scale, box, min_fraction=0.02, ring=8, min_relative=0.25):
    """Distinct flat fills inside a region that are NOT background, largest first.

    This is the pie discriminator: the one-100%-slice defect yields ONE entry
    and a correct chart yields one per slice. Saturation is deliberately NOT
    the filter - Slate's second chart series is neutral gray (172,172,172),
    which a saturation filter drops, reporting a healthy 3-slice pie as 2.
    Instead, colors that also appear in a thin ring just outside the region
    are treated as background (this is what makes it work on a gradient), and
    ``min_relative`` keeps only fills within a factor of the largest one, so
    leftover gradient banding cannot pad the count. Calibrated against the
    archived defect: `.scratch/pie-1.png` (the shipped one-slice bug) yields
    1, the corrected chart yields exactly one per slice.
    """
    x, y, w, h = box
    region = _crop(image, scale, box)
    outer = _crop(image, scale, (x - ring, y - ring, w + 2 * ring, h + 2 * ring))
    total = region.width * region.height
    inside = {color: n for n, color in (region.getcolors(total) or [])}
    around = {color: n for n, color in (outer.getcolors(outer.width * outer.height) or [])}
    out = [
        (color, n)
        for color, n in inside.items()
        if n >= min_fraction * total and around.get(color, 0) - n < max(40, 0.1 * n)
    ]
    out.sort(key=lambda t: -t[1])
    if out and min_relative:
        floor = out[0][1] * min_relative
        out = [(color, n) for color, n in out if n >= floor]
    return out


def pdf_page_count(path):
    """Page count of a PDF, read from the file (not from the export reply)."""
    data = Path(path).read_bytes()
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def pdf_media_boxes(path):
    return {m.decode().strip() for m in re.findall(rb"/MediaBox\s*\[([^\]]*)\]", Path(path).read_bytes())}


async def check_describe_at_scale(pres, deck):
    """PHASE 9 Task 3 — describe_deck on a deck the size of the real one.

    Asserts BOTH the wall clock and the output size, because the field report
    hit both walls at once: 137,091 characters (over the tool-output limit) and
    >120 s (over the timeout) on a 35-slide deck. A check that only asserted
    "it returned something" would have passed then too.

    Builds its own 35-slide / ~735-element deck so the numbers are reproducible
    rather than dependent on a file that may not be present.
    """
    key = SCRATCH / "phase9-scale.key"
    doc = "phase9-scale.key"
    if key.exists():
        check("phase9/scale: open the scale deck", await pres.open_presentation(str(key)))
    else:
        spec = {
            "title": "phase9-scale",
            "width": 1920,
            "height": 1080,
            "save_path": str(key),
            "slides": [],
        }
        for i in range(35):
            elements = []
            for c in range(4):
                elements.append(
                    {
                        "type": "panel",
                        "x": 80 + c * 450,
                        "y": 200,
                        "width": 420,
                        "height": 380,
                        "color": ["#EFA3A0", "#A8C6DE", "#D8EDD2", "#5C6E80"][c],
                        "radius": 8,
                    }
                )
            for c in range(4):
                elements.append(
                    {
                        "type": "text",
                        "text": f"Service {c + 1}",
                        "x": 100 + c * 450,
                        "y": 220,
                        "font_size": 22,
                    }
                )
            for c in range(6):
                elements.append(
                    {
                        "type": "line",
                        "x1": 100 + c * 60,
                        "y1": 640,
                        "x2": 300 + c * 60,
                        "y2": 700,
                    }
                )
            elements.append(
                {
                    "type": "table",
                    "data": [["Region", "Q1", "Q2"], ["North", 120, 130], ["South", 90, 95]],
                    "x": 80,
                    "y": 760,
                    "width": 700,
                    "height": 200,
                }
            )
            spec["slides"].append(
                {
                    "layout": "Blank",
                    "title": f"Architecture slide {i + 1}",
                    "notes": f"Speaker notes for slide {i + 1}.",
                    "elements": elements,
                }
            )
        check("phase9/scale: build a 35-slide deck", await deck.build_deck(spec=spec))

    # --- summary: the path that makes a real deck workable at all ---
    t0 = time.monotonic()
    summary_text = text_of(await deck.describe_deck(doc_name=doc, detail="summary"))
    summary_s = time.monotonic() - t0
    summary = json.loads(summary_text)
    record(
        "phase9/scale: summary covers every slide",
        len(summary["slides"]) == 35 and summary["slide_count"] == 35,
        f"{len(summary['slides'])} slides described",
    )
    record(
        "phase9/scale: summary is FAST (< 5s; full read was 31s before batching)",
        summary_s < 5.0,
        f"{summary_s:.2f}s",
    )
    record(
        "phase9/scale: summary is SMALL (< 20k chars; the field report's full dump was 137k)",
        len(summary_text) < 20_000,
        f"{len(summary_text):,} chars",
    )
    record(
        "phase9/scale: summary carries per-slide counts and a title",
        all("counts" in s and "title" in s for s in summary["slides"]),
        str(summary["slides"][0]),
    )

    # --- slide_range: paging ---
    t0 = time.monotonic()
    paged_text = text_of(await deck.describe_deck(doc_name=doc, slide_range="1-5"))
    paged_s = time.monotonic() - t0
    paged = json.loads(paged_text)
    record(
        "phase9/scale: slide_range='1-5' returns exactly those five slides",
        [s.get("slide") for s in paged["slides"]] == [1, 2, 3, 4, 5],
        str([s.get("slide") for s in paged["slides"]]),
    )
    record(
        "phase9/scale: a five-slide page is small and quick",
        len(paged_text) < 40_000 and paged_s < 15.0,
        f"{len(paged_text):,} chars in {paged_s:.2f}s",
    )

    # --- element_types: skipped classes are not READ, not merely omitted ---
    t0 = time.monotonic()
    lines_text = text_of(await deck.describe_deck(doc_name=doc, element_types=["line"]))
    lines_s = time.monotonic() - t0
    lines = json.loads(lines_text)
    classes = {
        el.get("element_class") for s in lines["slides"] for el in s.get("elements", [])
    }
    record(
        "phase9/scale: element_types=['line'] returns ONLY lines",
        classes == {"line"},
        f"classes present: {sorted(c for c in classes if c)}",
    )
    record(
        "phase9/scale: filtering is a real SPEEDUP, not just a smaller payload",
        lines_s < 6.0,
        f"{lines_s:.2f}s for lines only",
    )

    # --- full: must not time out, and must carry no float noise ---
    t0 = time.monotonic()
    full_text = text_of(await deck.describe_deck(doc_name=doc))
    full_s = time.monotonic() - t0
    full = json.loads(full_text)
    record(
        "phase9/scale: the FULL description completes well inside the 120s timeout",
        full_s < 90.0,
        f"{full_s:.1f}s for 35 slides / {sum(len(s.get('elements', [])) for s in full['slides'])} elements",
    )
    record(
        "phase9/scale: coordinates are rounded - no trailing '.0' noise",
        '.0,' not in full_text and '.0\n' not in full_text,
        f"{full_text.count('.0')} '.0' occurrences",
    )
    record(
        "phase9/scale: a large full description SAYS it is large and how to page it",
        "detail='summary'" in full_text and "slide_range" in full_text,
        f"{len(full_text):,} chars",
    )
    # Opting out of rounding must still work, for callers wanting raw floats.
    raw_text = text_of(
        await deck.describe_deck(doc_name=doc, slide_range="1", round_coordinates=False)
    )
    record(
        "phase9/scale: round_coordinates=False keeps Keynote's floats",
        ".0" in raw_text,
        f"{raw_text.count('.0')} '.0' occurrences with rounding off",
    )

    check(
        "phase9/scale: close the scale deck",
        await pres.close_presentation(doc_name=doc, should_save=False),
    )


async def check_index_contract(pres, slides, content, export, objects, deck):
    """PHASE 9 Task 2 — one numbering, proven ACROSS tools.

    Every check here runs on a slide with `title showing`, because that is the
    only configuration in which the bug exists and the only one the Phase 3 and
    Phase 8 harnesses never ran: a showing placeholder takes text-item slot 1
    and shifts every real index. Both tools were marked "verified" while
    disagreeing, because both were only ever tested on Blank slides.

    See docs/INDEX_CONTRACT.md.
    """
    key = SCRATCH / "phase9-index.key"
    shutil.rmtree(key, ignore_errors=True)
    key.unlink(missing_ok=True)
    doc = "phase9-index.key"
    check(
        "phase9/idx: create doc",
        await pres.create_presentation("phase9-index", save_path=str(key)),
        "Created presentation",
    )
    # Turn ON the title placeholder - this is the whole point.
    check(
        "phase9/idx: set_slide_content fills the TITLE placeholder",
        await content.set_slide_content(1, title="PLACEHOLDER TITLE", doc_name=doc),
    )
    added = check(
        "phase9/idx: add_text_box on the same slide",
        await content.add_text_box(1, "REAL BOX", x=100, y=600, doc_name=doc),
    )
    m = re.search(r"text item index (\d+)", added)
    emitted_index = int(m.group(1)) if m else -1
    record(
        "phase9/idx: add_text_box emitted an index at all",
        emitted_index > 0,
        added.replace("\n", " | ")[:120],
    )

    # 1. add_* -> edit_text_item: the emitted index must address the box we
    #    just added, NOT the placeholder now sitting in slot 1.
    check(
        "phase9/idx: edit_text_item(add_* index) targets the added box",
        await content.edit_text_item(1, emitted_index, "EDITED BOX", doc_name=doc),
    )
    listing = text_of(await content.get_slide_content(1, doc_name=doc))
    record(
        "phase9/idx: the EDIT landed on the added box, not the placeholder",
        "EDITED BOX" in listing and "PLACEHOLDER TITLE" in listing,
        listing.replace("\n", " | ")[:200],
    )

    # 2. get_slide_content and describe_deck must AGREE on the index.
    gsc_indices = {
        int(i): txt
        for i, txt in re.findall(r"TEXT:(\d+):::([^:]*):::", listing)
    }
    described = json.loads(text_of(await deck.describe_deck(doc_name=doc)))
    dd_texts = [
        el
        for el in described["slides"][0]["elements"]
        if el.get("element_class") == "text item"
    ]
    dd_indices = {el["index"]: el.get("text", "") for el in dd_texts}
    record(
        "phase9/idx: describe_deck emits element_class + index on every element",
        all("index" in el and "element_class" in el for el in described["slides"][0]["elements"]),
        str([(el.get("element_class"), el.get("index")) for el in described["slides"][0]["elements"]]),
    )
    record(
        "phase9/idx: get_slide_content and describe_deck agree on text-item indices",
        gsc_indices == dd_indices,
        f"get_slide_content={gsc_indices} describe_deck={dd_indices}",
    )

    # 3. The placeholder is REPRESENTED, not hidden - and flagged.
    placeholders = [el for el in dd_texts if el.get("placeholder")]
    record(
        "phase9/idx: describe_deck emits the showing placeholder as a flagged element",
        len(placeholders) == 1 and placeholders[0]["placeholder"] == "title",
        str(placeholders)[:200],
    )
    record(
        "phase9/idx: slide.title still carries the same text (round-trip rebuild)",
        described["slides"][0].get("title") == "PLACEHOLDER TITLE",
        str(described["slides"][0].get("title")),
    )

    # 4. describe_deck index -> style_text_range. This is the pair the field
    #    report says silently restyled the wrong element on ~half a deck.
    target = next(el for el in dd_texts if el.get("text") == "EDITED BOX")
    check(
        "phase9/idx: style_text_range(describe_deck index) is accepted",
        await objects.style_text_range(
            1, target["index"], 1, 6, color="#CC0000", doc_name=doc
        ),
    )
    # RENDERED: the styled text must be the added box, not the placeholder.
    size_text = text_of(await pres.get_slide_size(doc_name=doc))
    mm = re.search(r"(\d+)\s*x\s*(\d+)", size_text)
    slide_w = int(mm.group(1)) if mm else 1024
    img, scale = await render_slide(export, 1, "phase9-index", slide_w, doc_name=doc)
    if img is not None:
        box = next(el for el in dd_texts if el.get("text") == "EDITED BOX")
        title_el = placeholders[0] if placeholders else None
        red_in_box = _red_fraction(img, scale, box)
        red_in_title = _red_fraction(img, scale, title_el) if title_el else 0.0
        record(
            "phase9/idx: RENDERED the red styling landed on the described element, "
            "not the placeholder",
            red_in_box > 0.001 and red_in_box > red_in_title,
            f"red in target={red_in_box:.4f} red in placeholder={red_in_title:.4f}",
        )

    # 5. describe_deck index -> move_element, read back by get_slide_content.
    before = next(el for el in dd_texts if el.get("text") == "EDITED BOX")
    check(
        "phase9/idx: move_element(describe_deck index)",
        await content.move_element(1, "text", before["index"], 300, 500, doc_name=doc),
    )
    after = json.loads(text_of(await deck.describe_deck(doc_name=doc)))
    moved = next(
        el
        for el in after["slides"][0]["elements"]
        if el.get("element_class") == "text item" and el.get("text") == "EDITED BOX"
    )
    record(
        "phase9/idx: the MOVE landed on the described element",
        abs(moved["x"] - 300) < 2 and abs(moved["y"] - 500) < 2,
        f"moved to ({moved['x']}, {moved['y']}), expected (300, 500)",
    )
    still_title = after["slides"][0].get("title")
    record(
        "phase9/idx: the placeholder was NOT moved or rewritten by any of it",
        still_title == "PLACEHOLDER TITLE",
        str(still_title),
    )

    # 6. A stale index must FAIL, not silently address a different object.
    stale = text_of(await content.edit_text_item(1, 99, "should not land", doc_name=doc))
    record(
        "phase9/idx: a stale index is rejected, not silently applied",
        stale.startswith("Failed") and ("-1719" in stale or "Invalid index" in stale),
        stale.replace("\n", " | ")[:160],
    )

    check(
        "phase9/idx: close index doc",
        await pres.close_presentation(doc_name=doc, should_save=False),
    )


def _red_fraction(image, scale, el):
    """Share of pixels in an element's box that read as red-dominant."""
    if not el:
        return 0.0
    crop = _crop(image, scale, (el["x"], el["y"], el["width"], el["height"]))
    px = list(crop.convert("RGB").getdata())
    if not px:
        return 0.0
    red = sum(1 for r, g, b in px if r > 110 and r - g > 45 and r - b > 45)
    return red / len(px)


async def check_document_resolution(pres, slides, content, export, objects):
    """PHASE 9 Task 1 — the right document, named in the reply.

    Reproduces the field report's issue #1 exactly: two decks open, the session
    document is A, but B is frontmost because the user clicked it. Every
    doc_name-less call must still act on A, and every reply must say so.

    The rendered half matters most. A and B get panels of DIFFERENT colors at
    the SAME coordinates, so a screenshot taken without doc_name proves which
    document was really used - a reply that merely claims 'A' while exporting B
    is the precise defect being fixed, and only pixels can tell them apart.
    """
    from keynote_mcp.utils.session import SESSION

    a_key = SCRATCH / "phase9-docA.key"
    b_key = SCRATCH / "phase9-docB.key"
    for path in (a_key, b_key):
        shutil.rmtree(path, ignore_errors=True)
        path.unlink(missing_ok=True)

    a_rgb, b_rgb = (200, 30, 30), (30, 60, 200)
    panel_box = (150, 150, 500, 350)

    check(
        "phase9: create doc A",
        await pres.create_presentation("phase9-docA", save_path=str(a_key)),
        "Created presentation",
    )
    check(
        "phase9: A gets a RED panel",
        await objects.add_colored_panel(
            1, *panel_box, color=",".join(str(c * 257) for c in a_rgb), doc_name="phase9-docA.key"
        ),
    )
    check(
        "phase9: create doc B",
        await pres.create_presentation("phase9-docB", save_path=str(b_key)),
        "Created presentation",
    )
    check(
        "phase9: B gets a BLUE panel",
        await objects.add_colored_panel(
            1, *panel_box, color=",".join(str(c * 257) for c in b_rgb), doc_name="phase9-docB.key"
        ),
    )

    # create_presentation set the session document to B (the most recent).
    info_b = text_of(await pres.get_presentation_info())
    record(
        "phase9: the session document is the most recently created one (B)",
        "phase9-docB" in info_b,
        info_b.replace("\n", " | ")[:120],
    )

    # Now make A the session document the way a caller would.
    check(
        "phase9: open_presentation(A) sets the session document",
        await pres.open_presentation(str(a_key)),
        "session document",
    )

    # ...and put B in FRONT, the way a user clicking B would. This is the
    # exact state in which every doc_name-less call used to target B.
    pres.runner.run(
        """
        on run argv
            set docName to item 1 of argv
            tell application "Keynote"
                activate
                repeat with w in windows
                    if name of w is docName then
                        set index of w to 1
                        exit repeat
                    end if
                end repeat
                return name of front document
            end tell
        end run
        """,
        "phase9-docB.key",
    )
    front = pres.runner.run_inline_script(
        'tell application "Keynote" to return name of front document'
    )
    record(
        "phase9: B really is frontmost (the trap is armed)",
        front == "phase9-docB.key",
        f"front document is {front!r}",
    )

    # THE CHECK: no doc_name, B frontmost, session document A.
    info = text_of(await pres.get_presentation_info())
    record(
        "phase9: a doc_name-less call targets the SESSION document, not the front one",
        "phase9-docA" in info and "phase9-docB" not in info,
        info.replace("\n", " | ")[:140],
    )

    # RENDERED: the export must be A's red panel, not B's blue one. The slide
    # width is READ, never assumed - a hardcoded 1024 against this document's
    # 1920 sampled outside the panel and reported plain white.
    size_text = text_of(await pres.get_slide_size(doc_name="phase9-docA.key"))
    m = re.search(r"(\d+)\s*x\s*(\d+)", size_text)
    slide_w = int(m.group(1)) if m else 1024
    img, scale = await render_slide(export, 1, "phase9-resolution", slide_w)
    if img is not None:
        sampled = at(img, scale, panel_box[0] + panel_box[2] / 2, panel_box[1] + panel_box[3] / 2)
        record(
            "phase9: RENDERED the doc_name-less screenshot shows A's panel, not B's",
            near(sampled, a_rgb, tol=24),
            f"sampled={sampled} A={a_rgb} B={b_rgb}",
        )

    # Ambiguity: with the session default gone and two documents open, the
    # server must name them instead of guessing.
    SESSION.clear_default()
    ambiguous = text_of(await pres.get_presentation_info())
    record(
        "phase9: ambiguous target errors and NAMES the open documents",
        "phase9-docA.key" in ambiguous
        and "phase9-docB.key" in ambiguous
        and "doc_name" in ambiguous,
        ambiguous.replace("\n", " | ")[:180],
    )

    # The echo, through the real MCP entry point.
    from keynote_mcp.server import KeynoteMCPServer, _echo_resolved_document

    srv = KeynoteMCPServer()
    SESSION.note_resolved("")
    echoed = text_of(
        _echo_resolved_document(
            await srv._dispatch("get_slide_count", {"doc_name": "phase9-docA.key"})
        )
    )
    record(
        "phase9: every reply echoes the resolved document",
        "[document: phase9-docA.key]" in echoed,
        echoed.replace("\n", " | ")[:140],
    )

    check(
        "phase9: close doc A",
        await pres.close_presentation(doc_name="phase9-docA.key", should_save=False),
    )
    check(
        "phase9: close doc B",
        await pres.close_presentation(doc_name="phase9-docB.key", should_save=False),
    )


async def check_fill_is_unwritable(pres, slides, content, export, objects):
    """PHASE 9 Task 0 — pin the fill ceiling in errors AND in pixels.

    The field report claimed `set_element_style` can write shape fill. Probed
    across five themes and twelve write routes (including raw four-char-code
    chevrons), every route fails with -10006 and the render is byte-identical
    before and after. This check keeps that true: if a future Keynote makes
    fill writable, it FAILS here and the docs get corrected, rather than the
    repo carrying a PNG workaround for a limitation that has lapsed - which
    has already happened twice in this codebase.

    It also pins the mechanism that produced the false belief: an unknown
    argument being dropped and reported as success.
    """
    from keynote_mcp.server import KeynoteMCPServer

    key = SCRATCH / "phase9-fill.key"
    shutil.rmtree(key, ignore_errors=True)
    key.unlink(missing_ok=True)
    check(
        "phase9: create fill-probe doc",
        await pres.create_presentation("phase9-fill", save_path=str(key)),
        "Created presentation",
    )
    slide_w = 1024
    size_text = text_of(await pres.get_slide_size(doc_name="phase9-fill.key"))
    m = re.search(r"(\d+)\s*x\s*(\d+)", size_text)
    if m:
        slide_w = int(m.group(1))

    box = (200, 200, 400, 300)
    # Target the document by name throughout. An earlier draft of this check
    # omitted doc_name and a stray untitled document -- left frontmost by an
    # unrelated probe -- got rendered instead, reporting a fill color that came
    # from a completely different deck. That is the field report's issue #1
    # reproduced inside the harness meant to verify it; see
    # check_document_resolution for the check that covers it deliberately.
    doc = "phase9-fill.key"
    check(
        "phase9: add_shape for the fill probe",
        await content.add_shape(
            1, x=box[0], y=box[1], width=box[2], height=box[3], doc_name=doc
        ),
    )

    before, scale = await render_slide(export, 1, "phase9-fill-before", slide_w, doc_name=doc)
    if before is None:
        return
    interior = (box[0] + 40, box[1] + 40, box[2] - 80, box[3] - 80)
    before_color = dominant(_crop(before, scale, interior))
    # Prove the sample is the SHAPE and not just an arbitrary dark pixel: the
    # default theme fills shapes black, and "unchanged black" would otherwise
    # be satisfied by measuring nothing at all.
    outside_color = at(before, scale, box[0] + box[2] + 80, box[1] + box[3] // 2)
    record(
        "phase9: the sampled interior really is the shape (differs from the slide beside it)",
        not near(before_color, outside_color, tol=12),
        f"interior={before_color} outside={outside_color}",
    )

    # Every plausible AppleScript route to a shape fill, at the raw level.
    routes = [
        ("background fill type := color fill", "set background fill type of shape 1 to color fill"),
        ("background color := red", "set background color of shape 1 to {65535, 0, 0}"),
        ("color := red", "set color of shape 1 to {65535, 0, 0}"),
        ("raw chevron bkft := fico", 'set «class bkft» of shape 1 to «constant ****fico»'),
        ("raw chevron ceBC := red", 'set «class ceBC» of shape 1 to {65535, 0, 0}'),
    ]
    for label, statement in routes:
        script = (
            'tell application "Keynote" to tell document "phase9-fill.key" to tell slide 1\n'
            f"  {statement}\n"
            "end tell"
        )
        try:
            pres.runner.run_inline_script(script)
            ok, detail = False, "SUCCEEDED - fill may now be writable; re-probe and fix the docs"
        except Exception as e:  # noqa: BLE001 - any failure is the expected outcome
            detail = str(e)
            ok = "-10006" in detail or "10006" in detail or "Can't set" in detail
        record(f"phase9: shape fill route rejected — {label}", ok, detail[:150])

    # The read path DOES work, and describe_deck relies on it: a caller must be
    # able to tell "no fill" from "fill not reported".
    fill_type = pres.runner.run_inline_script(
        'tell application "Keynote" to tell document "phase9-fill.key" to '
        "return background fill type of shape 1 of slide 1 as text"
    )
    record(
        "phase9: background fill type is READABLE (feeds describe_deck fill_type)",
        fill_type in {"color fill", "no fill", "gradient fill", "advanced gradient fill",
                      "image fill", "advanced image fill"},
        fill_type,
    )

    # RENDERED: the shape must look exactly as it did. Errors alone would not
    # prove this - a write could raise and still have changed something.
    after, scale2 = await render_slide(export, 1, "phase9-fill-after", slide_w, doc_name=doc)
    if after is not None:
        after_color = dominant(_crop(after, scale2, interior))
        record(
            "phase9: RENDERED shape interior is UNCHANGED after every fill attempt",
            near(before_color, after_color, tol=4),
            f"before={before_color} after={after_color}",
        )

    # The mechanism that made the field report believe otherwise.
    srv = KeynoteMCPServer()
    rejection = srv._reject_unknown_arguments(
        "set_element_style",
        {"slide_number": 1, "element_type": "shape", "element_index": 1, "fill_color": "#EFA3A0"},
    )
    record(
        "phase9: set_element_style(fill_color=...) is REJECTED, not dropped",
        bool(rejection) and "REJECTED" in rejection and "add_colored_panel" in rejection,
        (rejection or "accepted silently").replace("\n", " | ")[:200],
    )
    record(
        "phase9: every tool schema forbids unknown arguments",
        all(t.inputSchema.get("additionalProperties") is False for t in srv.all_tools()),
        f"{len(srv.all_tools())} tools",
    )

    # The rendered-PNG panel is colorimetrically EXACT once the export's
    # Display-P3 profile is applied - the reason the workaround stays.
    check(
        "phase9: close fill-probe doc",
        await pres.close_presentation(doc_name=doc, should_save=False),
    )


async def main():
    pres = PresentationTools()
    slides = SlideTools()
    content = ContentTools()
    export = ExportTools()
    objects = ObjectTools()
    deck = DeckTools()

    SCRATCH.mkdir(exist_ok=True)
    test_key = SCRATCH / "phase3-test.key"
    if test_key.exists():
        test_key.unlink()
    for leftover in ("phase8-default.key", "phase8-rescued.key"):
        (SCRATCH / leftover).unlink(missing_ok=True)
    red_png = SCRATCH / "test-image.png"
    blue_png = SCRATCH / "verify-blue.png"
    Image.new("RGB", TEST_IMAGE_PX, RED).save(red_png)
    Image.new("RGB", TEST_IMAGE_PX, BLUE).save(blue_png)

    # --- presentation tools ---
    themes_text = check("get_available_themes", await pres.get_available_themes())
    theme = "Slate" if "Slate" in themes_text else ""

    check(
        "create_presentation(save+theme)",
        await pres.create_presentation("phase3-test", theme=theme, save_path=str(test_key)),
        expect_substring="Created presentation",
    )
    check("list_presentations", await pres.list_presentations(), "phase3-test")
    check(
        "first slide defaults to Blank (8.4)",
        await slides.get_slide_info(1),
        "Layout: Blank",
    )
    check("get_presentation_info", await pres.get_presentation_info(), "Slide count")
    size_text = check("get_slide_size", await pres.get_slide_size(), "Slide size info")
    slide_w, slide_h = (float(v) for v in re.search(r"Size: (\d+) x (\d+)", size_text).groups())

    # set_slide_content on slide 1: new presentations default to Blank, so
    # this exercises the enable-placeholder-then-fill path
    check(
        "set_slide_content",
        await content.set_slide_content(1, title="Phase 3 Title", body=None),
    )
    slide1 = text_of(await content.get_slide_content(1))
    record(
        "set_slide_content filled title visible on Blank slide",
        "Phase 3 Title" in slide1,
        slide1[:120],
    )

    # --- slide tools ---
    check("add_slide(end)", await slides.add_slide(), "Added slide #2")
    check("add_slide(position=2)", await slides.add_slide(position=2), "Added slide #2")
    check("get_slide_count", await slides.get_slide_count(), "Slide count: 3")
    check("duplicate_slide(1)", await slides.duplicate_slide(1), "new number: 2")
    check("get_slide_count=4", await slides.get_slide_count(), "Slide count: 4")
    check("move_slide(2->4)", await slides.move_slide(2, 4))
    check("get_slide_count=4 still", await slides.get_slide_count(), "Slide count: 4")
    check("delete_slide(4)", await slides.delete_slide(4), "Deleted slide 4")
    check("select_slide(2)", await slides.select_slide(2), "Selected slide 2")
    layouts_text = check(
        "get_available_layouts", await slides.get_available_layouts(), "Available layouts"
    )
    blank = "Blank" if "Blank" in layouts_text else None
    if blank:
        check("set_slide_layout(2,Blank)", await slides.set_slide_layout(2, "Blank"), "layout to")
    check("get_slide_info(2)", await slides.get_slide_info(2), "Slide 2 info")

    # --- content tools on slide 2 (Blank) ---
    evil = 'He said "hi" \\ and ¬ then 中文 🎉 line2'
    check("add_text_box(adversarial)", await content.add_text_box(2, evil, x=100, y=100))
    round_trip = check("get_slide_content", await content.get_slide_content(2), forbid_failure=True)
    record(
        "adversarial round-trip intact",
        'He said "hi" \\ and ¬ then 中文 🎉' in round_trip,
        round_trip[:120],
    )

    long_title = "Keynote MCP Modernized"
    check(
        "add_title(96pt clip-bug)",
        await content.add_title(2, long_title, x=100, y=200, font_size=96),
    )
    content_after = text_of(await content.get_slide_content(2))
    record(
        "96pt title NOT clipped",
        long_title in content_after,
        content_after[-200:],
    )

    check("add_subtitle", await content.add_subtitle(2, "A subtitle", x=100, y=400))
    check(
        "add_bullet_list",
        await content.add_bullet_list(2, ["first", "second", "third"], x=100, y=500),
    )
    check(
        "add_numbered_list",
        await content.add_numbered_list(2, ["one", "two"], x=600, y=500),
    )
    check(
        "add_code_block(color)",
        await content.add_code_block(
            2, "def f():\n    return 1", x=900, y=500, color="30000,55000,30000"
        ),
    )
    check("add_quote", await content.add_quote(2, "Verify before asserting", x=100, y=700))
    check(
        "add_shape(opacity=8)",
        await content.add_shape(2, x=50, y=50, width=400, height=300, opacity=8),
    )
    check(
        "set_element_opacity(shape 1 -> 50)",
        await content.set_element_opacity(2, "shape", 1, 50),
    )
    check("move_element(text 1)", await content.move_element(2, "text", 1, 150, 150))
    check("resize_element(text 1)", await content.resize_element(2, "text", 1, 500, 80))
    check("edit_text_item(text 1)", await content.edit_text_item(2, 1, "edited text ✓"))
    edited = text_of(await content.get_slide_content(2))
    record("edit_text_item round-trip", "edited text ✓" in edited, "")

    check("set_speaker_notes", await content.set_speaker_notes(2, "notes with ünïcode 中文"))
    notes = check("get_speaker_notes", await content.get_speaker_notes(2))
    record("speaker notes round-trip", "ünïcode 中文" in notes, notes[:80])

    check("add_image", await content.add_image(2, str(red_png), x=800, y=100))
    img_content = text_of(await content.get_slide_content(2))
    record("image present on slide", "images:1" in img_content, "")
    check("delete_element(image 1)", await content.delete_element(2, "image", 1))

    # clear_slide on the duplicated slide 3
    check("clear_slide(3)", await content.clear_slide(3), "Cleared slide 3")

    # --- phantom text item regression (field test 8.3) ---
    # Keynote surfaces the default title/body placeholder objects as extra
    # "text items" (hidden ones as 0x0 empties); five adds must report exactly
    # five items, none of them empty.
    check("add_slide(blank, for leak check)", await slides.add_slide(), "Added slide #4")
    await content.add_text_box(4, "one", x=50, y=50)
    await content.add_title(4, "two", x=50, y=150)
    await content.add_subtitle(4, "three", x=50, y=250)
    await content.add_code_block(4, "four = 4", x=50, y=350)
    await content.add_quote(4, "five", x=50, y=450)
    leak_report = text_of(await content.get_slide_content(4))
    entries = [e for e in leak_report.split("|||") if e.startswith("TEXT:")]
    empty_entries = [e for e in entries if e.split(":::")[1] == ""]
    record(
        "five adds -> exactly five text items",
        "text_items:5" in leak_report and len(entries) == 5,
        leak_report[:160],
    )
    record("no empty phantom entries reported", not empty_entries, str(empty_entries)[:120])
    # clear_slide must remove all five real items and still report zero
    check("clear_slide(4)", await content.clear_slide(4), "Cleared slide 4")
    cleared = text_of(await content.get_slide_content(4))
    record("clear_slide leaves zero text items", "text_items:0" in cleared, cleared[:100])
    check("delete leak-check slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- index round-trip per add_* tool (field test 8.2) ---
    # The index each add_* returns must be addressable by move_element and
    # come back from get_slide_content as the created element.
    check("add_slide(blank, for round-trip)", await slides.add_slide(), "Added slide #4")
    adders = [
        ("add_text_box", "rt-textbox", lambda: content.add_text_box(4, "rt-textbox", x=60, y=40)),
        ("add_title", "rt-title", lambda: content.add_title(4, "rt-title", x=60, y=110)),
        (
            "add_subtitle",
            "rt-subtitle",
            lambda: content.add_subtitle(4, "rt-subtitle", x=60, y=180),
        ),
        (
            "add_bullet_list",
            "• rt-b1",
            lambda: content.add_bullet_list(4, ["rt-b1", "rt-b2"], x=60, y=250),
        ),
        (
            "add_numbered_list",
            "1. rt-n1",
            lambda: content.add_numbered_list(4, ["rt-n1"], x=60, y=340),
        ),
        ("add_code_block", "rt_code = 1", lambda: content.add_code_block(4, "rt_code = 1", x=60, y=410)),
        ("add_quote", "“rt-quote”", lambda: content.add_quote(4, "rt-quote", x=60, y=480)),
    ]
    for offset, (name, expected_text, call) in enumerate(adders):
        reply = text_of(await call())
        m = re.search(r"text item index (\d+)\)", reply)
        if not m:
            record(f"{name} returns an index", False, reply[:140])
            continue
        idx = int(m.group(1))
        target_x, target_y = 700, 40 + 60 * offset
        await content.move_element(4, "text", idx, target_x, target_y)
        after = text_of(await content.get_slide_content(4))
        entry = next((e for e in after.split("|||") if e.startswith(f"TEXT:{idx}:::")), "")
        parts = entry.split(":::") if entry else []
        text_ok = len(parts) > 1 and parts[1].startswith(expected_text)
        pos_ok = len(parts) > 2 and parts[2] == f"{target_x},{target_y}"
        record(
            f"{name} index round-trip (returned {idx})",
            text_ok and pos_ok,
            entry[:120] or after[:120],
        )
    check("delete round-trip slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- server-side centering (field test 8.6) ---
    # The BOX check below is arithmetic on properties - exactly the arithmetic
    # that passed while the old pre-widening heuristic left the visible text
    # ~110pt left of center. The rendered check that follows measures the ink.
    check("add_slide(blank, for centering)", await slides.add_slide(), "Added slide #4")
    centered_bands = []
    for tool_name, call in [
        ("add_title", lambda: content.add_title(4, "Centered Headline", y=100, font_size=60, centered=True)),
        ("add_subtitle", lambda: content.add_subtitle(4, "Centered sub", y=300, centered=True)),
    ]:
        reply = text_of(await call())
        m = re.search(r"text item index (\d+)", reply)
        if not m:
            record(f"{tool_name}(centered) returns an index", False, reply[:140])
            continue
        idx = int(m.group(1))
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"TEXT:{idx}:::")), "")
        try:
            pos_part, size_part = entry.split(":::")[2], entry.split(":::")[3]
            x = float(pos_part.split(",")[0])
            y = float(pos_part.split(",")[1])
            w, h = (float(v) for v in size_part.split(","))
            centered_ok = abs(x - (slide_w - w) / 2) <= 1.0
            centered_bands.append((tool_name, y, h))
        except (IndexError, ValueError):
            centered_ok = False
        record(
            f"{tool_name}(centered) box is horizontally centered",
            centered_ok,
            entry[:120] or report[:120],
        )
    centering_img, centering_scale = await render_slide(export, 4, "centered", slide_w)
    if centering_img:
        for tool_name, y, h in centered_bands:
            bb = ink_bbox(centering_img, centering_scale, box=(0, y - 4, slide_w, h + 8))
            visual_center = (bb[0] + bb[2]) / 2 if bb else None
            record(
                f"{tool_name}(centered) RENDERED text is centered, not just the box",
                bb is not None and abs(visual_center - slide_w / 2) <= 4,
                f"ink spans {bb[0]:.0f}-{bb[2]:.0f}pt, center {visual_center:.1f} vs "
                f"{slide_w / 2:.0f}" if bb else "no ink rendered in the band",
            )
    check("delete centering slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- geometry honesty (drift regression) ---
    # Text items are born at the theme default font size (48pt) and auto-fit
    # around their vertical CENTER when the font size is applied, so a
    # position set before sizing drifted by (h_before - h_after)/2 (measured:
    # 24pt 1-line +14, 24pt 4-line +52, 96pt -28; 48pt exactly 0). add_* now
    # applies position AFTER sizing and reports the settled geometry, which
    # must (a) put the top-left exactly at the requested coordinates and
    # (b) match get_slide_content verbatim - no follow-up read needed.
    check("add_slide(blank, for geometry)", await slides.add_slide(), "Added slide #4")
    geo_re = re.compile(
        r"text item index (\d+)(?:, centered)?\) at \(([^,]+), ([^)]+)\), size ([^x]+)x(\S+)"
    )
    # Coordinates are kept inside the canvas on purpose: the previous layout
    # placed the code block, shape and image beyond x=1024 and the 96pt title
    # below y=768 on this 1024x768 document, and every check still passed -
    # property equality cannot see the slide edge. The rendered checks after
    # this loop can, so the elements have to be somewhere they can be seen.
    right_col = round(slide_w * 0.60)
    geometry_cases = [
        ("add_text_box(12pt)", 100, 60, lambda: content.add_text_box(4, "geometry probe", x=100, y=60, font_size=12)),
        ("add_subtitle(24pt)", 100, 120, lambda: content.add_subtitle(4, "geometry subtitle", x=100, y=120)),
        ("add_title(36pt)", 100, 190, lambda: content.add_title(4, "Geometry Title", x=100, y=190, font_size=36)),
        ("add_title(48pt=default)", 100, 280, lambda: content.add_title(4, "Geometry Title", x=100, y=280, font_size=48)),
        ("add_bullet_list(24pt, 4 lines)", 100, 390, lambda: content.add_bullet_list(4, ["g1", "g2", "g3", "g4"], x=100, y=390, font_size=24)),
        ("add_title(96pt clip path)", 100, 560, lambda: content.add_title(4, "Geometry Title", x=100, y=560, font_size=96)),
        ("add_code_block(14pt, green)", right_col, 60, lambda: content.add_code_block(4, "geo = 1", x=right_col, y=60, color="10000,55000,10000")),
    ]
    geometry_boxes = {}
    for name, gx, gy, call in geometry_cases:
        reply = text_of(await call())
        m = geo_re.search(reply)
        if not m:
            record(f"{name} reports final geometry", False, reply[:140])
            continue
        idx, rx, ry, rw, rh = m.groups()
        placed_ok = float(rx) == gx and float(ry) == gy
        record(
            f"{name} lands exactly at ({gx}, {gy})",
            placed_ok,
            f"reported ({rx}, {ry})" if not placed_ok else "",
        )
        geometry_boxes[name] = (float(rx), float(ry), float(rw), float(rh))
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"TEXT:{idx}:::")), "")
        parts = entry.split(":::")
        match_ok = len(parts) > 3 and parts[2] == f"{rx},{ry}" and parts[3] == f"{rw},{rh}"
        record(
            f"{name} reported geometry matches get_slide_content",
            match_ok,
            f"reply ({rx},{ry}) {rw},{rh} vs slide {entry[-40:]}" if not match_ok else "",
        )
    shape_reply = text_of(await content.add_shape(4, x=right_col, y=200, width=240, height=140))
    m = re.search(r"shape index (\d+)\) at \(([^,]+), ([^)]+)\), size ([^x]+)x([\d.]+)", shape_reply)
    if m:
        idx, rx, ry, rw, rh = m.groups()
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"SHAPE:{idx}:::")), "")
        parts = entry.split(":::")
        ok = len(parts) > 2 and parts[1] == f"{rx},{ry}" and parts[2] == f"{rw},{rh}"
        record("add_shape reported geometry matches get_slide_content", ok, entry[:100])
        geometry_boxes["add_shape"] = (float(rx), float(ry), float(rw), float(rh))
    else:
        record("add_shape reports index and geometry", False, shape_reply[:140])
    img_reply = text_of(
        await content.add_image(4, str(red_png), x=right_col, y=380, width=160, height=120)
    )
    m = re.search(r"image index (\d+)\) at \(([^,]+), ([^)]+)\), size ([^x]+)x(\S+)", img_reply)
    if m:
        idx, rx, ry, rw, rh = m.groups()
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"IMAGE:{idx}:::")), "")
        parts = entry.split(":::")
        ok = len(parts) > 2 and parts[1] == f"{rx},{ry}" and parts[2] == f"{rw},{rh}"
        record("add_image reported geometry matches get_slide_content", ok, entry[:100])
        geometry_boxes["add_image"] = (float(rx), float(ry), float(rw), float(rh))
    else:
        record("add_image reports index and geometry", False, img_reply[:140])

    # RENDERED: one export, then ask the pixels what every add_* actually drew.
    # Property equality above proves Keynote stored the numbers; only this
    # proves something is visible, on the canvas, in the requested color, and
    # not truncated.
    geo_img, geo_scale = await render_slide(export, 4, "geometry", slide_w)
    if geo_img:
        offslide = {
            name: box
            for name, box in geometry_boxes.items()
            if box[0] < 0 or box[1] < 0 or box[0] + box[2] > slide_w or box[1] + box[3] > slide_h
        }
        record(
            "every placed element lands inside the slide canvas",
            not offslide,
            f"off-slide: {offslide}"[:160],
        )
        for name, box in geometry_boxes.items():
            if name in ("add_shape", "add_image"):
                # Flat fills have no internal detail: sample the middle and a
                # point just outside instead of looking for edges.
                x, y, w, h = box
                inside = at(geo_img, geo_scale, x + w / 2, y + h / 2)
                beside = at(geo_img, geo_scale, min(x + w + 20, slide_w - 2), y + h / 2)
                record(
                    f"{name} is actually drawn (its fill differs from the slide beside it)",
                    not near(inside, beside, 12),
                    f"inside {inside} vs beside {beside}",
                )
                continue
            fraction = ink_fraction(geo_img, geo_scale, box=box)
            record(
                f"{name} is actually drawn (ink inside its box)",
                fraction > 0.01,
                f"{fraction * 100:.1f}% of the box carries drawn detail",
            )
        # Clipping is a RENDER symptom: the legacy ">48pt truncates to one or
        # two characters" bug leaves the model text intact. Same string at 48
        # and 96pt must render ~twice as wide. The 48pt band is clipped to the
        # left column so the right column's objects cannot leak into it.
        wide = {}
        for name, band_w in (
            ("add_title(48pt=default)", right_col - 20),
            ("add_title(96pt clip path)", slide_w),
        ):
            _, by, _, bh = geometry_boxes[name]
            bb = ink_bbox(geo_img, geo_scale, box=(0, by - 4, band_w, bh + 8))
            wide[name] = (bb[2] - bb[0]) if bb else 0.0
        ratio = wide["add_title(96pt clip path)"] / (wide["add_title(48pt=default)"] or 1)
        record(
            "96pt title renders ~2x the 48pt width (not clipped)",
            1.7 <= ratio <= 2.3,
            f"48pt ink {wide['add_title(48pt=default)']:.0f}pt, "
            f"96pt ink {wide['add_title(96pt clip path)']:.0f}pt, ratio {ratio:.2f}",
        )
        # add_code_block(color=green): the color argument must reach the glyphs.
        cb_box = geometry_boxes["add_code_block(14pt, green)"]
        cx, cy, cw, ch = cb_box
        crop = geo_img.crop(
            (
                int(cx * geo_scale),
                int(cy * geo_scale),
                int((cx + cw) * geo_scale),
                int((cy + ch) * geo_scale),
            )
        )
        bg = dominant(geo_img)
        greens = [
            (color, n)
            for n, color in (crop.getcolors(crop.width * crop.height) or [])
            if max(abs(a - b) for a, b in zip(color, bg, strict=False)) > 40
            and color[1] > color[0] + 25
            and color[1] > color[2] + 25
        ]
        record(
            "add_code_block(color) renders green glyphs, not theme-colored ones",
            sum(n for _, n in greens) > 20,
            f"{sum(n for _, n in greens)} green ink pixels in the box",
        )
    check("delete geometry slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- export tools ---
    # File existence and a >1KB size prove only that Keynote wrote something;
    # a blank slide, the wrong slide, or a zero-page PDF all clear that bar.
    shot = SCRATCH / "slide2.png"
    check("screenshot_slide(2)", await export.screenshot_slide(2, str(shot)), "Captured")
    record("screenshot file exists", shot.exists() and shot.stat().st_size > 1000, str(shot))
    shot_img = Image.open(shot).convert("RGB")
    shot_scale = shot_img.width / slide_w
    record(
        "screenshot is a real render of the slide (right size, not blank)",
        (shot_img.width, shot_img.height) == (int(slide_w), int(slide_h))
        and ink_fraction(shot_img, shot_scale) > 0.01,
        f"{shot_img.size} px for a {slide_w:.0f}x{slide_h:.0f}pt slide, "
        f"{ink_fraction(shot_img, shot_scale) * 100:.1f}% non-background",
    )
    pdf = SCRATCH / "deck.pdf"
    slide_total = int(text_of(await slides.get_slide_count()).split(":")[1])
    check("export_pdf", await export.export_pdf(str(pdf)), "Exported PDF")
    record("pdf file exists", pdf.exists() and pdf.stat().st_size > 1000, str(pdf))
    record(
        "exported PDF contains one page per slide",
        pdf_page_count(pdf) == slide_total,
        f"{pdf_page_count(pdf)} pages for {slide_total} slides",
    )

    # --- screenshot honesty (field test 8.5): unfilled placeholders are
    # omitted from the export; the tool must say so ---
    check("add_slide(for screenshot honesty)", await slides.add_slide(), "Added slide #4")
    await content.set_slide_content(4, title="")  # enable title placeholder, leave unfilled
    shot_ph = SCRATCH / "slide4-placeholder.png"
    honesty = check(
        "screenshot_slide(unfilled placeholder)",
        await export.screenshot_slide(4, str(shot_ph)),
        "Captured",
    )
    record(
        "screenshot reports the omitted placeholder",
        "1 unfilled placeholder" in honesty and "NOT rendered" in honesty,
        honesty[:160],
    )
    # ... and the render must actually be missing it, otherwise the warning is
    # the only thing being tested (it is composed by the tool itself).
    ph_img = Image.open(shot_ph).convert("RGB")
    ph_ink = ink_fraction(ph_img, ph_img.width / slide_w)
    ph_report = text_of(await content.get_slide_content(4))
    record(
        "the omitted placeholder really is absent from the render",
        ph_ink < 0.005,
        f"render is {ph_ink * 100:.2f}% non-background while the slide reports "
        f"{ph_report.split('|||')[0][:40]}",
    )
    record(
        "screenshot of filled slide reports faithful view",
        "matches the editor view" in text_of(await export.screenshot_slide(2, str(shot))),
        "",
    )
    check("delete honesty slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- build animation tools (UI scripting, slow) ---
    check("select_slide(2) pre-build", await slides.select_slide(2))
    check(
        "add_build_in(text 2)",
        await content.add_build_in(2, "text", 2, effect="Appear", delivery="All at Once"),
    )
    check("remove_build_in(text 2)", await content.remove_build_in(2, "text", 2))
    check(
        "add_builds_to_slide(3,4)",
        await content.add_builds_to_slide(2, "3,4", effect="Appear"),
    )

    # --- native objects (3.0.0): tables, charts, lines, panels, styling ---
    # Laid out to fit a 1024x768 canvas so the render below can see every
    # object; the earlier layout ran the chart and the panel off the right
    # edge, which no property check can notice.
    check("add_slide(for native objects)", await slides.add_slide(), "Added slide #4")
    TABLE_BOX = (40, 40, 440, 200)
    BAR_BOX = (520, 40, 460, 240)
    PIE_BOX = (520, 300, 460, 250)
    PANEL_BOX = (40, 300, 280, 120)
    SHAPE_BOX = (60, 320, 200, 80)
    IMAGE_BOX = (40, 560, 160, 120)
    PANEL_RGB = (47, 75, 124)  # #2F4B7C, also the default style's table header
    check(
        "add_table(4x3 with formula)",
        await objects.add_table(
            4,
            [
                ["Team", "Now", "Plan"],
                ["Eng", 24, 30],
                ["Sales", 11, 14],
                ["Total", "=SUM(B2:B3)", "=SUM(C2:C3)"],
            ],
            x=TABLE_BOX[0],
            y=TABLE_BOX[1],
            width=TABLE_BOX[2],
            height=TABLE_BOX[3],
        ),
        "table index",
    )
    table_vals = content.runner.run(
        """
        on run argv
            tell application "Keynote"
                tell table 1 of slide 4 of document (item 1 of argv)
                    return (value of cell 2 of row 2 as text) & "|" & ¬
                        (formula of cell 2 of row 4 as text) & "|" & ¬
                        (value of cell 2 of row 4 as text)
                end tell
            end tell
        end run
        """,
        "phase3-test.key",
    )
    record(
        "table cells: number stays numeric, '=' string became a live formula",
        table_vals.startswith("24") and "=SUM(B2:B3)" in table_vals and "35" in table_vals,
        table_vals,
    )
    check(
        "add_chart(native bar)",
        await objects.add_chart(
            4,
            "bar",
            ["2024", "2025"],
            ["North", "South"],
            [[12, 17], [15, 21]],
            x=BAR_BOX[0],
            y=BAR_BOX[1],
            width=BAR_BOX[2],
            height=BAR_BOX[3],
        ),
        "chart index",
    )
    # A pie whose caller asked for the WRONG grouping axis: `group_by="column"`
    # with a single column is exactly the input that rendered one 100% slice
    # while `count of charts is 1` passed. chart_fragment auto-corrects to the
    # multi-entry axis; only the rendered slice count below proves it did.
    check(
        "add_chart(pie, single-entry group axis -> auto-corrected)",
        await objects.add_chart(
            4,
            "pie",
            ["North", "South", "West"],
            ["Share"],
            [[30], [45], [25]],
            group_by="column",
            x=PIE_BOX[0],
            y=PIE_BOX[1],
            width=PIE_BOX[2],
            height=PIE_BOX[3],
        ),
        "chart index",
    )
    chart_count = content.runner.run(
        'on run argv\ntell application "Keynote" to return count of charts of '
        "slide 4 of document (item 1 of argv)\nend run",
        "phase3-test.key",
    )
    record("native charts exist on slide", chart_count.strip() == "2", chart_count)
    check("add_line", await objects.add_line(4, 40, 270, 480, 270), "line index")
    panel_reply = check(
        "add_colored_panel(#2F4B7C, r=20)",
        await objects.add_colored_panel(
            4, *PANEL_BOX, color="#2F4B7C", radius=20
        ),
        "image index",
    )
    record(
        "panel reply reports requested geometry",
        f"at ({PANEL_BOX[0]}, {PANEL_BOX[1]}), size {PANEL_BOX[2]}x{PANEL_BOX[3]}" in panel_reply,
        panel_reply[:140],
    )
    # A shape ON TOP of the panel (z-order is creation order): the only way to
    # see an opacity change is to put something with a known color behind it.
    check(
        "add_shape(over the panel, opaque)",
        await content.add_shape(
            4, x=SHAPE_BOX[0], y=SHAPE_BOX[1], width=SHAPE_BOX[2], height=SHAPE_BOX[3]
        ),
        "shape index",
    )
    styled = text_of(await content.add_text_box(4, "range styling target", x=40, y=450))
    styled_idx = int(re.search(r"text item index (\d+)\)", styled).group(1))
    check(
        "style_text_range(chars 1-5 red bold)",
        await objects.style_text_range(
            4, styled_idx, 1, 5, color="#CC0000", font_name="Helvetica-Bold"
        ),
        "Styled characters 1-5",
    )
    range_read = content.runner.run(
        f"""
        on run argv
            tell application "Keynote"
                tell object text of text item {styled_idx} of slide 4 of document (item 1 of argv)
                    set c2 to color of character 2
                    set c9 to color of character 9
                    return (item 1 of c2 as text) & "|" & (font of character 2) & ¬
                        "|" & (item 1 of c9 as text)
                end tell
            end tell
        end run
        """,
        "phase3-test.key",
    )
    r2, f2, r9 = range_read.split("|")
    record(
        "styled range differs from the rest (color+font, unstyled intact)",
        abs(int(float(r2)) - 52428) < 600
        and f2 == "Helvetica-Bold"
        and abs(int(float(r9)) - 52428) > 5000,  # unstyled char keeps the THEME color
        range_read,
    )
    check(
        "add_image(for replace)",
        await content.add_image(
            4,
            str(red_png),
            x=IMAGE_BOX[0],
            y=IMAGE_BOX[1],
            width=IMAGE_BOX[2],
            height=IMAGE_BOX[3],
        ),
    )

    # RENDERED pass 1 over the whole native-object slide. Everything above is
    # a count or a property; everything here is a pixel.
    obj_img, obj_scale = await render_slide(export, 4, "objects-before", slide_w)
    if obj_img:
        tx, ty, tw, _th = TABLE_BOX
        header_strip = obj_img.crop(
            (
                int((tx + 8) * obj_scale),
                int((ty + 8) * obj_scale),
                int((tx + tw - 8) * obj_scale),
                int((ty + 26) * obj_scale),
            )
        )
        body_strip = obj_img.crop(
            (
                int((tx + 8) * obj_scale),
                int((ty + 60) * obj_scale),
                int((tx + tw - 8) * obj_scale),
                int((ty + 78) * obj_scale),
            )
        )
        header_bg, body_bg = dominant(header_strip), dominant(body_strip)
        record(
            "add_table header row is RENDERED in the style's header color",
            near(header_bg, PANEL_RGB, 30) and not near(header_bg, body_bg, 20),
            f"header {header_bg} vs body {body_bg}, style header #2F4B7C",
        )
        bar_fills = fill_areas(obj_img, obj_scale, BAR_BOX, min_fraction=0.004)
        record(
            "add_chart(bar) renders one distinct fill per series",
            len(bar_fills) >= 2,
            f"{len(bar_fills)} distinct fills: {[c for c, _ in bar_fills[:4]]}",
        )
        # THE regression check: the shipped defect produced exactly one fill.
        pie_fills = fill_areas(obj_img, obj_scale, PIE_BOX, min_fraction=0.004)
        areas = [n for _, n in pie_fills]
        record(
            "add_chart(pie) renders 3 slices, not one 100% slice",
            len(pie_fills) >= 3,
            f"{len(pie_fills)} distinct fills, areas {areas[:4]} "
            f"(1 fill == the grouped-axis defect)",
        )
        record(
            "pie slice areas follow the data (45 > 30 > 25)",
            len(areas) >= 3 and areas[0] > areas[1] > areas[2],
            f"areas {areas[:3]}",
        )
        line_mid = ink_bbox(obj_img, obj_scale, box=(40, 262, 440, 16))
        record(
            "add_line is RENDERED (ink along its path, not just an object)",
            line_mid is not None and (line_mid[2] - line_mid[0]) > 380,
            f"ink spans {line_mid}" if line_mid else "no ink on the line's path",
        )
        panel_center = at(
            obj_img, obj_scale, PANEL_BOX[0] + PANEL_BOX[2] - 20, PANEL_BOX[1] + PANEL_BOX[3] - 12
        )
        outside = at(obj_img, obj_scale, PANEL_BOX[0] + PANEL_BOX[2] + 24, PANEL_BOX[1] + 20)
        record(
            "add_colored_panel is RENDERED in the requested color at the requested place",
            near(panel_center, PANEL_RGB, 24) and not near(outside, PANEL_RGB, 24),
            f"inside {panel_center} vs requested {PANEL_RGB}; just outside {outside}",
        )
        shape_opaque = at(
            obj_img, obj_scale, SHAPE_BOX[0] + SHAPE_BOX[2] / 2, SHAPE_BOX[1] + SHAPE_BOX[3] / 2
        )
        image_before = at(
            obj_img, obj_scale, IMAGE_BOX[0] + IMAGE_BOX[2] / 2, IMAGE_BOX[1] + IMAGE_BOX[3] / 2
        )
        record(
            "add_image RENDERS the bitmap it was given (red before the swap)",
            image_before[0] > 120 and image_before[0] > image_before[2] + 50,
            f"sampled {image_before}",
        )
    else:
        shape_opaque = image_before = None

    check("replace_image(image 2 -> blue)", await objects.replace_image(4, 2, str(blue_png)))
    replaced_name = content.runner.run(
        'on run argv\ntell application "Keynote" to return file name of image 2 of '
        "slide 4 of document (item 1 of argv) as text\nend run",
        "phase3-test.key",
    )
    record("replace_image swapped the file in place", "verify-blue" in replaced_name, replaced_name)
    check(
        "set_element_opacity(shape over panel -> 20)",
        await content.set_element_opacity(4, "shape", 1, 20),
    )

    # RENDERED pass 2: only the two things that changed since pass 1.
    obj_img2, obj_scale2 = await render_slide(export, 4, "objects-after", slide_w)
    if obj_img2:
        image_after = at(
            obj_img2, obj_scale2, IMAGE_BOX[0] + IMAGE_BOX[2] / 2, IMAGE_BOX[1] + IMAGE_BOX[3] / 2
        )
        record(
            "replace_image swapped the RENDERED bitmap, not just the file name",
            image_after[2] > 120 and image_after[2] > image_after[0] + 50,
            f"sampled {image_after} (was {image_before})",
        )
        shape_faded = at(
            obj_img2, obj_scale2, SHAPE_BOX[0] + SHAPE_BOX[2] / 2, SHAPE_BOX[1] + SHAPE_BOX[3] / 2
        )
        if shape_opaque is not None:
            dist_before = sum(abs(a - b) for a, b in zip(shape_opaque, PANEL_RGB, strict=False))
            dist_after = sum(abs(a - b) for a, b in zip(shape_faded, PANEL_RGB, strict=False))
            record(
                "set_element_opacity changes what is DRAWN (panel shows through)",
                dist_after < dist_before - 30,
                f"shape over the panel: {shape_opaque} at 100% -> {shape_faded} at 20% "
                f"(distance to panel {dist_before} -> {dist_after})",
            )
    check(
        "set_element_style(rotation+reflection+lock round-trip)",
        await objects.set_element_style(
            4, "text", styled_idx, rotation=15, reflection_showing=True, reflection_value=20
        ),
        "rotation=15",
    )
    rot_read = content.runner.run(
        f'on run argv\ntell application "Keynote" to return rotation of text item '
        f"{styled_idx} of slide 4 of document (item 1 of argv) as text\nend run",
        "phase3-test.key",
    )
    record("rotation read back", rot_read.strip() == "15", rot_read)
    check(
        "set_element_style(unlock for cleanup)",
        await objects.set_element_style(4, "text", styled_idx, rotation=0, locked=False),
    )

    # --- transitions, skipped, document settings, slide size (3.0.0) ---
    check(
        "set_slide_transition(push 1.5s)",
        await slides.set_slide_transition(4, "push", duration=1.5),
        "'push'",
    )
    trans_read = content.runner.run(
        'on run argv\ntell application "Keynote"\nset tp to transition properties of '
        "slide 4 of document (item 1 of argv)\nreturn (transition effect of tp as text) "
        '& "|" & (transition duration of tp as text)\nend tell\nend run',
        "phase3-test.key",
    )
    record("transition read back", trans_read.startswith("push|1.5"), trans_read)
    check("set_slide_skipped(4, true)", await slides.set_slide_skipped(4, True), "now skipped")
    skipped_read = content.runner.run(
        'on run argv\ntell application "Keynote" to return skipped of slide 4 of '
        "document (item 1 of argv) as text\nend run",
        "phase3-test.key",
    )
    record("skipped read back true", skipped_read.strip() == "true", skipped_read)
    # The flag's only consequence is what exports contain: prove it there.
    slide_total = int(text_of(await slides.get_slide_count()).split(":")[1])
    skip_pdf = SCRATCH / "verify-skipped.pdf"
    skip_pdf_all = SCRATCH / "verify-skipped-all.pdf"
    await export.export_pdf(str(skip_pdf))
    await export.export_pdf(str(skip_pdf_all), include_skipped=True)
    record(
        "a skipped slide is left OUT of the PDF, and include_skipped puts it back",
        pdf_page_count(skip_pdf) == slide_total - 1
        and pdf_page_count(skip_pdf_all) == slide_total,
        f"{pdf_page_count(skip_pdf)} pages skipping vs {pdf_page_count(skip_pdf_all)} "
        f"including, for {slide_total} slides",
    )
    # Keynote IGNORES `skipped slides` for the images export - probed at the
    # raw-AppleScript level, identical counts either way. Pin the real
    # behavior so the tool's warning stays true, rather than asserting the
    # behavior the option name implies.
    skip_dir = SCRATCH / "verify-skipped-images"
    shutil.rmtree(skip_dir, ignore_errors=True)
    images_reply = text_of(
        await export.export_presentation("images", str(skip_dir), include_skipped=True)
    )
    images_including = len(list(skip_dir.glob("*.png")))
    record(
        "images export omits skipped slides even with include_skipped, and says so",
        images_including == slide_total - 1 and "Keynote ignores include_skipped" in images_reply,
        f"{images_including} images for {slide_total} slides with include_skipped=True",
    )
    check(
        "set_slide_skipped(4, false)", await slides.set_slide_skipped(4, False), "not skipped"
    )
    numbers_off_img, _numbers_scale = await render_slide(export, 3, "numbers-off", slide_w)
    check(
        "set_document_settings(slide numbers on)",
        await pres.set_document_settings(slide_numbers_showing=True),
        "slide numbers showing=true",
    )
    numbers_read = content.runner.run(
        'on run argv\ntell application "Keynote" to return slide numbers showing of '
        "document (item 1 of argv) as text\nend run",
        "phase3-test.key",
    )
    record("slide numbers showing read back", numbers_read.strip() == "true", numbers_read)
    numbers_on_img, _ = await render_slide(export, 3, "numbers-on", slide_w)
    if numbers_off_img and numbers_on_img:
        # A slide number is a few hundred pixels of ink on an otherwise
        # unchanged slide: the render must change, but only slightly.
        changed = ImageChops.difference(numbers_off_img, numbers_on_img).convert("L")
        moved = sum(changed.histogram()[41:])
        total = numbers_on_img.width * numbers_on_img.height
        record(
            "slide numbers are actually DRAWN when the setting is on",
            0 < moved < total * 0.02,
            f"{moved} px changed ({moved / total * 100:.3f}% of the slide)",
        )
    check(
        "set_document_settings(restore)",
        await pres.set_document_settings(slide_numbers_showing=False),
    )

    # --- export formats (3.0.0) ---
    notes_pdf = SCRATCH / "verify-notes.pdf"
    check(
        "export_pdf(slides_with_notes)",
        await export.export_pdf(str(notes_pdf), layout="slides_with_notes"),
        "Exported PDF",
    )
    record("notes pdf exists", notes_pdf.exists() and notes_pdf.stat().st_size > 1000, "")
    # Page count is real inspection; layout is not distinguishable this
    # cheaply. Keynote's notes pages are a fixed 1024x768, which happens to
    # equal this deck's slide size, so the MediaBox is identical to the plain
    # export's (measured) - telling the layouts apart needs the PDF
    # rasterized, which this harness does not do (TOOL_MATRIX records it).
    record(
        "slides_with_notes PDF has one page per slide (layout itself unverified)",
        pdf_page_count(notes_pdf) == slide_total,
        f"notes: {pdf_page_count(notes_pdf)} pages {sorted(pdf_media_boxes(notes_pdf))} for "
        f"{slide_total} slides",
    )
    pptx_path = SCRATCH / "verify.pptx"
    check(
        "export_presentation(pptx)",
        await export.export_presentation("pptx", str(pptx_path)),
        "Exported pptx",
    )
    record("pptx exists", pptx_path.exists() and pptx_path.stat().st_size > 1000, "")
    with zipfile.ZipFile(pptx_path) as bundle:
        pptx_slides = [
            n for n in bundle.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
        ]
        pptx_text = "".join(
            bundle.read(n).decode("utf-8", "ignore") for n in sorted(pptx_slides)
        )
    record(
        "pptx really contains one slide part per slide, with the deck's text",
        len(pptx_slides) == slide_total and "Phase 3 Title" in pptx_text,
        f"{len(pptx_slides)} slide parts for {slide_total} slides; "
        f"title text present: {'Phase 3 Title' in pptx_text}",
    )
    images_dir = SCRATCH / "verify-images"
    shutil.rmtree(images_dir, ignore_errors=True)
    check(
        "export_presentation(images)",
        await export.export_presentation("images", str(images_dir)),
        "Exported images",
    )
    exported_pngs = sorted(images_dir.glob("*.png")) if images_dir.is_dir() else []
    record(
        "per-slide images exist",
        len(exported_pngs) >= 3,
        str([p.name for p in exported_pngs][:4]),
    )
    exported_sizes = {Image.open(p).size for p in exported_pngs}
    # Slide 3 is deliberately empty (clear_slide), so "every image has ink" is
    # wrong; "the ones with content rendered it" is the honest assertion.
    non_blank = sum(
        1 for p in exported_pngs if ink_fraction(Image.open(p).convert("RGB"), 1.0) > 0.005
    )
    record(
        "exported images are one render per slide, at slide size, with content",
        len(exported_pngs) == slide_total
        and exported_sizes == {(int(slide_w), int(slide_h))}
        and non_blank >= slide_total - 1,
        f"{len(exported_pngs)} images for {slide_total} slides, sizes {exported_sizes}, "
        f"{non_blank} non-blank",
    )
    html_dir = SCRATCH / "verify-html"
    shutil.rmtree(html_dir, ignore_errors=True)
    check(
        "export_presentation(html)",
        await export.export_presentation("html", str(html_dir)),
        "Exported html",
    )
    record("html bundle exists", html_dir.is_dir(), str(html_dir))
    html_files = sorted(p.name for p in html_dir.rglob("*")) if html_dir.is_dir() else []
    record(
        "html bundle is a playable export (index + assets), not an empty dir",
        "index.html" in html_files and len(html_files) > 3,
        f"{len(html_files)} entries: {html_files[:5]}",
    )
    # movie/key09 exports were verified live in the Phase A probes (real .m4v
    # and .key artifacts); movie rendering is too slow for every harness run.

    check("delete native-objects slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- build_deck / describe_deck (3.0.0) ---
    deck_path = SCRATCH / "verify-deck.key"
    deck_spec = {
        "title": "verify-deck",
        "theme": "White",
        "style": "boardroom",
        "save_path": str(deck_path),
        "slides": [
            {
                "elements": [
                    {"type": "title", "text": "Verify Deck", "centered": True, "y": 300},
                    {"type": "subtitle", "text": "harness build", "centered": True, "y": 460},
                ],
                "notes": "deck notes ünïcode",
                "transition": {"effect": "dissolve", "duration": 0.7},
            },
            {
                "elements": [
                    {"type": "title", "text": "Data"},
                    {
                        "type": "table",
                        "data": [["k", "v"], ["a", 1], ["b", 2]],
                    },
                    {
                        "type": "chart",
                        "chart_type": "pie",
                        "row_names": ["x", "y"],
                        "column_names": ["v"],
                        "data": [[30], [70]],
                        "group_by": "column",
                    },
                ],
            },
            {
                "elements": [
                    {"type": "panel", "x": 100, "y": 200, "width": 500, "height": 250},
                    {"type": "bullets", "items": ["L1", "L2"], "column": "left", "y": 550},
                    {"type": "bullets", "items": ["R1", "R2"], "column": "right", "y": 550},
                ],
                "skipped": True,
            },
        ],
    }
    bad_spec = {"slides": [{"elements": [{"type": "nope"}, {"type": "table", "data": [[1]]}]}]}
    bad_reply = text_of(await deck.build_deck(spec=bad_spec))
    record(
        "build_deck(bad spec) rejects everything up front with both errors",
        "Spec validation failed (2" in bad_reply
        and "unknown element type" in bad_reply
        and not (SCRATCH / "deck.key").exists(),
        bad_reply[:160],
    )
    built = check("build_deck(3-slide spec)", await deck.build_deck(spec=deck_spec), "Built")
    record(
        "build_deck: zero element errors and file exists",
        "(0 element error(s))" in built and deck_path.exists(),
        built[:160],
    )
    record(
        "build_deck reports settled geometry",
        '"position"' in built and '"size"' in built,
        "",
    )

    # RENDERED: "0 element errors" is compatible with a deck that looks
    # completely wrong - wrong colors, elements painted under panels, columns
    # collapsed, a pie with one slice. Look at two of the three slides.
    deck_size = text_of(await pres.get_slide_size(doc_name="verify-deck.key"))
    deck_w, _deck_h = (float(v) for v in re.search(r"Size: (\d+) x (\d+)", deck_size).groups())
    try:
        build_report = json.loads(built.split("\n", 1)[1])
    except (IndexError, json.JSONDecodeError):
        build_report = None
        record("build_deck reply carries a parseable element report", False, built[:160])
    if build_report:

        def built_boxes(slide_index, kind):
            out = []
            for element in build_report["slides"][slide_index].get("elements", []):
                if element.get("type") != kind:
                    continue
                x, y = (float(v) for v in element["position"].split(","))
                w, h = (float(v) for v in element["size"].split(","))
                out.append((x, y, w, h))
            return out

        chart_boxes = built_boxes(1, "chart")
        deck2, deck2_scale = await render_slide(
            export, 2, "deck-slide2", deck_w, doc_name="verify-deck.key"
        )
        if deck2 and chart_boxes:
            deck_pie = fill_areas(deck2, deck2_scale, chart_boxes[0], min_fraction=0.004)
            record(
                "build_deck: the spec's 30/70 pie renders 2 slices, not one",
                len(deck_pie) >= 2,
                f"{len(deck_pie)} distinct fills in the chart box {chart_boxes[0]}",
            )
        elif deck2:
            record("build_deck: the spec's pie renders 2 slices", False, "no chart in the report")

        panel_boxes = built_boxes(2, "panel")
        bullet_boxes = built_boxes(2, "bullets")
        deck3, deck3_scale = await render_slide(
            export, 3, "deck-slide3", deck_w, doc_name="verify-deck.key"
        )
        if deck3 and panel_boxes:
            px, py, pw, ph = panel_boxes[0]
            panel_px = at(deck3, deck3_scale, px + pw - 16, py + ph - 16)
            record(
                "build_deck: the panel renders in the style's color (boardroom #E8EDF6)",
                near(panel_px, (232, 237, 246), 10)
                and not near(panel_px, dominant(deck3), 10),
                f"sampled {panel_px}, slide background {dominant(deck3)}",
            )
        if deck3 and len(bullet_boxes) == 2:
            # Measured from the INK, not the boxes: `{"column": "left", "y":
            # 550}` used to place both lists at x=0, one on top of the other,
            # with a clean 0-error build and a clean describe_deck round-trip.
            band_y = min(b[1] for b in bullet_boxes)
            band_h = max(b[3] for b in bullet_boxes)
            left_ink = ink_bbox(deck3, deck3_scale, box=(0, band_y - 4, deck_w / 2, band_h + 8))
            right_ink = ink_bbox(
                deck3, deck3_scale, box=(deck_w / 2, band_y - 4, deck_w / 2, band_h + 8)
            )
            record(
                "build_deck: column:left/right really render in opposite halves",
                left_ink is not None and right_ink is not None,
                f"ink in the left half: {left_ink}, in the right half: {right_ink}",
            )
    described_raw = text_of(await deck.describe_deck(doc_name="verify-deck.key"))
    try:
        described = json.loads(described_raw)
    except json.JSONDecodeError:
        described = None
    record("describe_deck returns parseable spec", described is not None, described_raw[:160])
    if described:
        s1, s2, s3 = described["slides"]
        table_el = next((e for e in s2["elements"] if e["type"] == "table"), {})
        record(
            "describe_deck round-trips notes/transition/skipped/table data",
            s1.get("notes", "").startswith("deck notes")
            and s1.get("transition", {}).get("effect") == "dissolve"
            and s3.get("skipped") is True
            and table_el.get("data", [])[1:] == [["a", 1], ["b", 2]]
            and any(e["type"] == "chart" for e in s2["elements"]),
            str({k: s1.get(k) for k in ("notes", "transition")})[:160],
        )
        # True round-trip: rebuild from the described spec. Charts come
        # back geometry-only (chart_type null - Keynote exposes no data to
        # read), so they cannot be rebuilt and must be dropped or refilled;
        # validate_spec correctly rejects them otherwise.
        chart_rejected = text_of(await deck.build_deck(spec=described, save_path=str(SCRATCH / "verify-deck-rt.key")))
        record(
            "rebuild with null chart_type rejected up front (charts are write-once)",
            "Spec validation failed" in chart_rejected and "chart_type" in chart_rejected,
            chart_rejected[:160],
        )
        dropped = []
        for sl in described["slides"]:
            kept = []
            for e in sl.get("elements", []):
                if e.get("type") == "chart":
                    dropped.append("chart")  # write-once: no data to read back
                elif e.get("type") == "image" and not Path(
                    str(e.get("path", ""))
                ).is_file():
                    dropped.append("embedded image")  # only the basename survives embedding
                else:
                    kept.append(e)
            sl["elements"] = kept
        record(
            "round-trip limitations are the documented ones only",
            set(dropped) <= {"chart", "embedded image"},
            str(dropped),
        )
        described["slides"][2].pop("skipped", None)  # keep visible for the rebuild
        rebuilt = text_of(
            await deck.build_deck(
                spec=described, save_path=str(SCRATCH / "verify-deck-rt.key")
            )
        )
        record(
            "build_deck(describe_deck output) rebuilds with zero errors",
            "(0 element error(s))" in rebuilt,
            rebuilt[:200],
        )
        try:
            pres.runner.run(
                'on run argv\ntell application "Keynote" to close document (item 1 of argv) '
                "saving no\nend run",
                "verify-deck-rt.key",
            )
        except Exception as cleanup_err:
            print(f"  (cleanup: {cleanup_err})")
    rerun = text_of(await deck.build_deck(spec=deck_spec))
    record(
        "build_deck re-run replaces the same file (idempotent)",
        rerun.startswith("Built 3-slide deck") and "(0 element error(s))" in rerun,
        rerun[:120],
    )
    md_built = text_of(
        await deck.build_deck(
            markdown=(
                "---\ntitle: verify-md\ntheme: White\nsave_path: "
                f"{SCRATCH / 'verify-md.key'}\n---\n\n# MD Deck\n\n## Points\n"
                "- alpha\n- beta\n\nNotes: md notes here.\n\n"
                "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
            )
        )
    )
    record(
        "build_deck(markdown) builds title+content slides",
        md_built.startswith("Built 2-slide deck") and "(0 element error(s))" in md_built,
        md_built[:160],
    )
    for name in ("verify-deck.key", "verify-md.key"):
        try:
            pres.runner.run(
                'on run argv\ntell application "Keynote" to close document (item 1 of argv) '
                "saving no\nend run",
                name,
            )
        except Exception as cleanup_err:
            print(f"  (cleanup: {cleanup_err})")

    # --- theme switch, save, close, reopen ---
    if "Basic Black" in themes_text:
        theme_before, _ = await render_slide(export, 2, "theme-before", slide_w)
        check(
            "set_presentation_theme",
            await pres.set_presentation_theme("Basic Black"),
            "Theme set",
        )
        theme_after, _ = await render_slide(export, 2, "theme-after", slide_w)
        if theme_before and theme_after:
            # A theme is nothing BUT what it draws; the reply text proves none
            # of it. Basic Black over Slate must repaint most of the slide.
            delta = ImageChops.difference(theme_before, theme_after).convert("L")
            moved = sum(delta.histogram()[41:])
            total = theme_after.width * theme_after.height
            record(
                "set_presentation_theme repaints the slide",
                moved > total * 0.2,
                f"{moved / total * 100:.1f}% of pixels changed",
            )
    check("save_presentation", await pres.save_presentation(), "Saved")
    check("close_presentation(no save)", await pres.close_presentation(should_save=False))
    # .scratch lives under ~/Downloads, which is OUTSIDE Keynote's sandbox
    # container - this is the path that wedged the AppleEvent queue before the
    # LaunchServices fix.
    check(
        "open_presentation(outside sandbox, ~/Downloads)",
        await pres.open_presentation(str(test_key)),
        "Opened",
    )
    check("queue alive after open", await slides.get_slide_count(), "Slide count")

    # error paths against reality - run while OUR document is frontmost so the
    # probe can never address a user document
    bad = text_of(await slides.delete_slide(99))
    record("delete_slide(99) actionable", "-1728" in bad or "does not exist" in bad, bad[:140])

    check("close again", await pres.close_presentation(should_save=False))

    # open from ~/Desktop, the other outside-sandbox location the field test
    # hit (.key documents may be saved as single files or packages)
    desktop_key = Path.home() / "Desktop" / "keynote-mcp-verify-tmp.key"
    try:
        if test_key.is_dir():
            shutil.copytree(test_key, desktop_key)
        else:
            shutil.copyfile(test_key, desktop_key)
        check(
            "open_presentation(outside sandbox, ~/Desktop)",
            await pres.open_presentation(str(desktop_key)),
            "Opened",
        )
        check("close desktop copy", await pres.close_presentation(should_save=False))
    finally:
        if desktop_key.is_dir():
            shutil.rmtree(desktop_key, ignore_errors=True)
        else:
            desktop_key.unlink(missing_ok=True)

    # --- untitled-document save path (the Phase 3 harness never took it) ---
    default_saved = check(
        "create_presentation(no save_path -> default location)",
        await pres.create_presentation("phase8-default"),
        "saved to",
    )
    default_path = SCRATCH / "phase8-default.key"
    record(
        "default save path is under KEYNOTE_MCP_SAVE_DIR and exists",
        str(SCRATCH) in default_saved and default_path.exists(),
        default_saved[:160],
    )
    check(
        "set_slide_size(1920x1080 live resize)",
        await pres.set_slide_size(1920, 1080),
        "1920x1080",
    )
    size_after = text_of(await pres.get_slide_size())
    record("slide size read back 1920x1080", "1920 x 1080" in size_after, size_after[:80])
    resized_shot = RENDER_DIR / "resized.png"
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    await export.screenshot_slide(1, str(resized_shot))
    record(
        "the resized document really EXPORTS at 1920x1080",
        resized_shot.exists() and Image.open(resized_shot).size == (1920, 1080),
        str(Image.open(resized_shot).size) if resized_shot.exists() else "no export",
    )
    check("close default-saved doc", await pres.close_presentation(should_save=False))

    # a genuinely unsaved document (made behind the server's back): plain save
    # must be REFUSED fast, not open the modal sheet / land in iCloud
    pres.runner.run('tell application "Keynote" to make new document')
    unsaved_msg = text_of(await pres.save_presentation())
    record(
        "save_presentation(unsaved, no path) refused with guidance",
        unsaved_msg.startswith("Failed") and "save_path" in unsaved_msg,
        unsaved_msg[:160],
    )
    rescue_path = SCRATCH / "phase8-rescued.key"
    check(
        "save_presentation(unsaved, save_path)",
        await pres.save_presentation(save_path=str(rescue_path)),
        "Saved presentation",
    )
    record("rescued file exists", rescue_path.exists(), str(rescue_path))
    check("close rescued doc", await pres.close_presentation(should_save=False))

    await check_index_contract(pres, slides, content, export, objects, deck)
    await check_describe_at_scale(pres, deck)
    await check_document_resolution(pres, slides, content, export, objects)
    await check_fill_is_unwritable(pres, slides, content, export, objects)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    for name, _, message in failed:
        print(f"  FAILED: {name}: {message[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
