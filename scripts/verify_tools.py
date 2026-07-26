"""Live verification: run every tool against a real Keynote.

Phase 3 built the original happy-path coverage; Phase 8 added the regression
checks for what a field test showed that coverage missed: the untitled-
document save path, opening files from outside Keynote's sandbox container
(~/Downloads and ~/Desktop), index round-trips for every add_* tool, phantom
placeholder filtering, screenshot placeholder honesty, server-side centering,
and geometry honesty (placed coordinates land exactly despite Keynote's
center-anchored auto-fit; add_* replies match get_slide_content).

Creates documents only under .scratch/ (plus one temporary copy on ~/Desktop
for the outside-sandbox open check, removed afterwards), closes them without
saving user data, and prints one PASS/FAIL line per check.

WARNING: this drives Keynote's UI - it takes window focus, and during the
build-animation checks anything you type lands in the test presentation.
Don't touch the keyboard while it runs (~2 minutes).

Usage:  uv run python scripts/verify_tools.py
"""

import asyncio
import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path

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

# 1x1 red PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)

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
    png_path = SCRATCH / "test-image.png"
    png_path.write_bytes(PNG_BYTES)

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
    check("get_slide_size", await pres.get_slide_size(), "Slide size info")

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

    check("add_image", await content.add_image(2, str(png_path), x=800, y=100))
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
    check("add_slide(blank, for centering)", await slides.add_slide(), "Added slide #4")
    size_text = text_of(await pres.get_slide_size())
    slide_w = float(re.search(r"Size: (\d+)", size_text).group(1))
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
            w = float(size_part.split(",")[0])
            centered_ok = abs(x - (slide_w - w) / 2) <= 1.0
        except (IndexError, ValueError):
            centered_ok = False
        record(
            f"{tool_name}(centered) box is horizontally centered",
            centered_ok,
            entry[:120] or report[:120],
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
    geometry_cases = [
        ("add_text_box(12pt)", 150, 120, lambda: content.add_text_box(4, "geometry probe", x=150, y=120, font_size=12)),
        ("add_subtitle(24pt)", 150, 200, lambda: content.add_subtitle(4, "geometry subtitle", x=150, y=200)),
        ("add_title(36pt)", 150, 280, lambda: content.add_title(4, "Geometry Title", x=150, y=280, font_size=36)),
        ("add_title(48pt=default)", 150, 380, lambda: content.add_title(4, "Geometry Title", x=150, y=380, font_size=48)),
        ("add_bullet_list(24pt, 4 lines)", 150, 480, lambda: content.add_bullet_list(4, ["g1", "g2", "g3", "g4"], x=150, y=480, font_size=24)),
        ("add_title(96pt clip path)", 150, 760, lambda: content.add_title(4, "Big Geometry", x=150, y=760, font_size=96)),
        ("add_code_block(14pt)", 900, 120, lambda: content.add_code_block(4, "geo = 1", x=900, y=120)),
    ]
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
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"TEXT:{idx}:::")), "")
        parts = entry.split(":::")
        match_ok = len(parts) > 3 and parts[2] == f"{rx},{ry}" and parts[3] == f"{rw},{rh}"
        record(
            f"{name} reported geometry matches get_slide_content",
            match_ok,
            f"reply ({rx},{ry}) {rw},{rh} vs slide {entry[-40:]}" if not match_ok else "",
        )
    shape_reply = text_of(await content.add_shape(4, x=1400, y=120, width=300, height=180))
    m = re.search(r"shape index (\d+)\) at \(([^,]+), ([^)]+)\), size ([^x]+)x([\d.]+)", shape_reply)
    if m:
        idx, rx, ry, rw, rh = m.groups()
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"SHAPE:{idx}:::")), "")
        parts = entry.split(":::")
        ok = len(parts) > 2 and parts[1] == f"{rx},{ry}" and parts[2] == f"{rw},{rh}"
        record("add_shape reported geometry matches get_slide_content", ok, entry[:100])
    else:
        record("add_shape reports index and geometry", False, shape_reply[:140])
    img_reply = text_of(await content.add_image(4, str(png_path), x=1400, y=400))
    m = re.search(r"image index (\d+)\) at \(([^,]+), ([^)]+)\), size ([^x]+)x(\S+)", img_reply)
    if m:
        idx, rx, ry, rw, rh = m.groups()
        report = text_of(await content.get_slide_content(4))
        entry = next((e for e in report.split("|||") if e.startswith(f"IMAGE:{idx}:::")), "")
        parts = entry.split(":::")
        ok = len(parts) > 2 and parts[1] == f"{rx},{ry}" and parts[2] == f"{rw},{rh}"
        record("add_image reported geometry matches get_slide_content", ok, entry[:100])
    else:
        record("add_image reports index and geometry", False, img_reply[:140])
    check("delete geometry slide", await slides.delete_slide(4), "Deleted slide 4")

    # --- export tools ---
    shot = SCRATCH / "slide2.png"
    check("screenshot_slide(2)", await export.screenshot_slide(2, str(shot)), "Captured")
    record("screenshot file exists", shot.exists() and shot.stat().st_size > 1000, str(shot))
    pdf = SCRATCH / "deck.pdf"
    check("export_pdf", await export.export_pdf(str(pdf)), "Exported PDF")
    record("pdf file exists", pdf.exists() and pdf.stat().st_size > 1000, str(pdf))

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
    check("add_slide(for native objects)", await slides.add_slide(), "Added slide #4")
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
            x=80,
            y=80,
            width=500,
            height=260,
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
            x=700,
            y=80,
            width=600,
            height=350,
        ),
        "chart index",
    )
    chart_count = content.runner.run(
        'on run argv\ntell application "Keynote" to return count of charts of '
        "slide 4 of document (item 1 of argv)\nend run",
        "phase3-test.key",
    )
    record("native chart exists on slide", chart_count.strip() == "1", chart_count)
    check("add_line", await objects.add_line(4, 80, 400, 580, 400), "line index")
    panel_reply = check(
        "add_colored_panel(#2F4B7C, r=20)",
        await objects.add_colored_panel(4, 80, 430, 300, 120, color="#2F4B7C", radius=20),
        "image index",
    )
    record(
        "panel reply reports requested geometry",
        "at (80, 430), size 300x120" in panel_reply,
        panel_reply[:140],
    )
    styled = text_of(await content.add_text_box(4, "range styling target", x=80, y=580))
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
    check("add_image(for replace)", await content.add_image(4, str(png_path), x=1500, y=430))
    blue_png = SCRATCH / "verify-blue.png"
    blue_png.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwAC"
            "hAGAWVzUTwAAAABJRU5ErkJggg=="
        )
    )
    check("replace_image(image 2 -> blue)", await objects.replace_image(4, 2, str(blue_png)))
    replaced_name = content.runner.run(
        'on run argv\ntell application "Keynote" to return file name of image 2 of '
        "slide 4 of document (item 1 of argv) as text\nend run",
        "phase3-test.key",
    )
    record("replace_image swapped the file in place", "verify-blue" in replaced_name, replaced_name)
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
    check(
        "set_slide_skipped(4, false)", await slides.set_slide_skipped(4, False), "not skipped"
    )
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
    pptx_path = SCRATCH / "verify.pptx"
    check(
        "export_presentation(pptx)",
        await export.export_presentation("pptx", str(pptx_path)),
        "Exported pptx",
    )
    record("pptx exists", pptx_path.exists() and pptx_path.stat().st_size > 1000, "")
    images_dir = SCRATCH / "verify-images"
    shutil.rmtree(images_dir, ignore_errors=True)
    check(
        "export_presentation(images)",
        await export.export_presentation("images", str(images_dir)),
        "Exported images",
    )
    record(
        "per-slide images exist",
        images_dir.is_dir() and len(list(images_dir.glob("*.png"))) >= 3,
        str(sorted(p.name for p in images_dir.glob("*"))[:4]),
    )
    html_dir = SCRATCH / "verify-html"
    shutil.rmtree(html_dir, ignore_errors=True)
    check(
        "export_presentation(html)",
        await export.export_presentation("html", str(html_dir)),
        "Exported html",
    )
    record("html bundle exists", html_dir.is_dir(), str(html_dir))
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
        check(
            "set_presentation_theme",
            await pres.set_presentation_theme("Basic Black"),
            "Theme set",
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

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    for name, _, message in failed:
        print(f"  FAILED: {name}: {message[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
