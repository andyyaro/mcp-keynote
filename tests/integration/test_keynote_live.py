"""Integration tests against a real Keynote.app.

Marked `keynote` and deselected by default (see pyproject addopts). Run
locally with:  uv run pytest -m keynote

The session fixture creates a scratch presentation in .scratch/, closes it
without saving in teardown, and quits Keynote only if the fixture started it.
"""

import asyncio
from pathlib import Path

import pytest

from keynote_mcp.tools.content import ContentTools
from keynote_mcp.tools.export import ExportTools
from keynote_mcp.tools.presentation import PresentationTools
from keynote_mcp.tools.slide import SlideTools
from keynote_mcp.utils.applescript_runner import AppleScriptRunner

pytestmark = pytest.mark.keynote

SCRATCH = Path(__file__).resolve().parents[2] / ".scratch"
DOC_NAME = "integration-test.key"


@pytest.fixture(scope="session")
def keynote_doc():
    """A scratch presentation; closed without saving on teardown."""
    SCRATCH.mkdir(exist_ok=True)
    key_path = SCRATCH / DOC_NAME
    if key_path.exists():
        key_path.unlink()

    runner = AppleScriptRunner()
    keynote_was_running = runner.check_keynote_running()

    presentation = PresentationTools()
    created = asyncio.run(
        presentation.create_presentation("integration-test", theme="", save_path=str(key_path))
    )
    assert "Created presentation" in created[0].text, created[0].text

    yield DOC_NAME

    asyncio.run(presentation.close_presentation(doc_name=DOC_NAME, should_save=False))
    if not keynote_was_running:
        runner.quit_keynote()
    key_path.unlink(missing_ok=True)
    for leftover in SCRATCH.glob("integration-*.png"):
        leftover.unlink()
    for leftover in SCRATCH.glob("integration-*.pdf"):
        leftover.unlink()


@pytest.fixture
def content():
    return ContentTools()


@pytest.fixture
def slides():
    return SlideTools()


async def test_adversarial_text_round_trips(keynote_doc, content, slides):
    await slides.add_slide(doc_name=keynote_doc)
    payload = 'He said "hi" \\ and ¬ then 中文 🎉 RTL שלום'
    result = await content.add_text_box(2, payload, x=50, y=50, doc_name=keynote_doc)
    assert "Added text box" in result[0].text
    state = (await content.get_slide_content(2, doc_name=keynote_doc))[0].text
    assert payload in state
    await slides.delete_slide(2, doc_name=keynote_doc)


async def test_large_font_title_is_not_clipped(keynote_doc, content, slides):
    await slides.add_slide(doc_name=keynote_doc)
    title = "Integration Title"
    await content.add_title(2, title, x=50, y=100, font_size=96, doc_name=keynote_doc)
    state = (await content.get_slide_content(2, doc_name=keynote_doc))[0].text
    assert title in state, f"96pt title was clipped: {state}"
    await slides.delete_slide(2, doc_name=keynote_doc)


async def test_slide_lifecycle(keynote_doc, slides):
    base = int((await slides.get_slide_count(doc_name=keynote_doc))[0].text.split(":")[1])
    await slides.add_slide(doc_name=keynote_doc)
    await slides.duplicate_slide(1, doc_name=keynote_doc)
    count = (await slides.get_slide_count(doc_name=keynote_doc))[0].text
    assert f"{base + 2}" in count
    moved = await slides.move_slide(1, 2, doc_name=keynote_doc)
    assert "Moved slide" in moved[0].text
    count = (await slides.get_slide_count(doc_name=keynote_doc))[0].text
    assert f"{base + 2}" in count, "move_slide must not destroy a slide"
    await slides.delete_slide(base + 2, doc_name=keynote_doc)
    await slides.delete_slide(base + 1, doc_name=keynote_doc)


async def test_speaker_notes_round_trip(keynote_doc, content):
    notes = "integration nötes 中文"
    await content.set_speaker_notes(1, notes, doc_name=keynote_doc)
    result = (await content.get_speaker_notes(1, doc_name=keynote_doc))[0].text
    assert notes in result


async def test_screenshot_and_pdf_export(keynote_doc):
    export = ExportTools()
    shot = SCRATCH / "integration-slide1.png"
    result = await export.screenshot_slide(1, str(shot), doc_name=keynote_doc)
    assert "Captured screenshot" in result[0].text
    assert shot.exists() and shot.stat().st_size > 1000

    pdf = SCRATCH / "integration-deck.pdf"
    result = await export.export_pdf(str(pdf), doc_name=keynote_doc)
    assert "Exported PDF" in result[0].text
    assert pdf.exists() and pdf.stat().st_size > 1000


async def test_invalid_index_error_is_actionable(keynote_doc, slides):
    result = await slides.delete_slide(999, doc_name=keynote_doc)
    text = result[0].text
    assert text.startswith("Failed to delete slide")
    assert "get_slide_count" in text


async def test_build_animation_add_and_remove(keynote_doc, content, slides):
    """UI-scripting path: needs Accessibility permission and Keynote frontmost."""
    await slides.add_slide(doc_name=keynote_doc)
    await content.add_text_box(2, "build me", x=100, y=100, doc_name=keynote_doc)
    added = await content.add_build_in(2, "text", 1, effect="Appear", delivery="All at Once")
    assert "Added Build In" in added[0].text, added[0].text
    removed = await content.remove_build_in(2, "text", 1)
    assert "Removed Build In" in removed[0].text, removed[0].text
    await slides.delete_slide(2, doc_name=keynote_doc)
