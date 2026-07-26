"""Phase 3 live verification: run every tool against a real Keynote.

Creates documents only under .scratch/, closes them without saving user data,
and prints one PASS/FAIL line per check.

WARNING: this drives Keynote's UI - it takes window focus, and during the
build-animation checks anything you type lands in the test presentation.
Don't touch the keyboard while it runs (~1 minute).

Usage:  uv run python scripts/verify_tools.py
"""

import asyncio
import base64
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
from keynote_mcp.tools.export import ExportTools  # noqa: E402
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

    # --- export tools ---
    shot = SCRATCH / "slide2.png"
    check("screenshot_slide(2)", await export.screenshot_slide(2, str(shot)), "Captured")
    record("screenshot file exists", shot.exists() and shot.stat().st_size > 1000, str(shot))
    pdf = SCRATCH / "deck.pdf"
    check("export_pdf", await export.export_pdf(str(pdf)), "Exported PDF")
    record("pdf file exists", pdf.exists() and pdf.stat().st_size > 1000, str(pdf))

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
    check("close again", await pres.close_presentation(should_save=False))

    # open from ~/Desktop, the other outside-sandbox location the field test hit
    desktop_key = Path.home() / "Desktop" / "keynote-mcp-verify-tmp.key"
    try:
        shutil.copyfile(test_key, desktop_key)
        check(
            "open_presentation(outside sandbox, ~/Desktop)",
            await pres.open_presentation(str(desktop_key)),
            "Opened",
        )
        check("close desktop copy", await pres.close_presentation(should_save=False))
    finally:
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

    # error paths against reality
    bad = text_of(await slides.delete_slide(99))
    record("delete_slide(99) actionable", "-1728" in bad or "does not exist" in bad, bad[:140])

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    for name, _, message in failed:
        print(f"  FAILED: {name}: {message[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
