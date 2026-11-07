"""PHASE 9 Task 3 — describe_deck at real-deck scale.

The field report: 137,091 characters and >120 s on a 35-slide deck, blowing
both the tool-output limit and the timeout, with no way to page. Profiled here
on a generated 35-slide/735-element deck before changing anything: 31.2 s of
which ~4.5 s was pure process overhead (0.125 s x 36 calls, one per slide), and
2,415 trailing '.0' carrying no information.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from keynote_mcp.tools import deck as deck_mod
from keynote_mcp.tools.deck import (
    _ALL_ELEMENT_CLASSES,
    DeckTools,
    _chunks,
    _parse_element_types,
    _parse_slide_range,
    _props_read,
    _round_slide_numbers,
    _soft_class_read,
)
from keynote_mcp.tools.fragments import (
    _TEXT_ITEM_PREDICATE,
    TEXT_ITEM_CLASSIFY,
    TEXT_ITEM_FILTER,
)
from keynote_mcp.utils.error_handler import AppleScriptError, AppleScriptTimeout, ParameterError


class TestSlideRange:
    def test_empty_means_every_slide(self) -> None:
        assert _parse_slide_range("", 5) == [1, 2, 3, 4, 5]
        assert _parse_slide_range("   ", 3) == [1, 2, 3]

    def test_single_slide(self) -> None:
        assert _parse_slide_range("3", 10) == [3]

    def test_span(self) -> None:
        assert _parse_slide_range("2-5", 10) == [2, 3, 4, 5]

    def test_mixed_list(self) -> None:
        assert _parse_slide_range("1-3,7,9-10", 12) == [1, 2, 3, 7, 9, 10]

    def test_overlaps_are_deduplicated_and_sorted(self) -> None:
        assert _parse_slide_range("5,1-3,2-6", 10) == [1, 2, 3, 4, 5, 6]

    def test_bounds_are_clamped_to_the_deck(self) -> None:
        assert _parse_slide_range("1-999", 4) == [1, 2, 3, 4]
        assert _parse_slide_range("0-2", 4) == [1, 2]

    def test_out_of_range_selection_is_an_error_not_an_empty_description(self) -> None:
        with pytest.raises(ParameterError, match="selects no slides"):
            _parse_slide_range("50-60", 10)

    def test_backwards_span_is_rejected(self) -> None:
        with pytest.raises(ParameterError, match="backwards"):
            _parse_slide_range("9-2", 10)

    @pytest.mark.parametrize("bad", ["abc", "1-x", "-", "3-"])
    def test_garbage_is_rejected_with_examples(self, bad: str) -> None:
        with pytest.raises(ParameterError, match="Invalid slide_range"):
            _parse_slide_range(bad, 10)


class TestElementTypes:
    def test_none_means_every_class(self) -> None:
        assert _parse_element_types(None) == _ALL_ELEMENT_CLASSES
        assert _parse_element_types([]) == _ALL_ELEMENT_CLASSES

    def test_subset(self) -> None:
        assert _parse_element_types(["text", "line"]) == frozenset({"text", "line"})

    def test_bare_string_is_tolerated(self) -> None:
        assert _parse_element_types("line") == frozenset({"line"})

    def test_unknown_class_is_rejected_and_lists_the_valid_ones(self) -> None:
        with pytest.raises(ParameterError) as excinfo:
            _parse_element_types(["text", "sparkle"])
        assert "sparkle" in str(excinfo.value)
        assert "chart" in str(excinfo.value)


class TestRounding:
    def test_whole_floats_become_ints(self) -> None:
        node = {"x": 679.0, "y": 12.0}
        _round_slide_numbers(node)
        assert node == {"x": 679, "y": 12}
        assert isinstance(node["x"], int)

    def test_fractional_values_are_preserved(self) -> None:
        node = {"x": 679.5, "duration": 1.5}
        _round_slide_numbers(node)
        assert node == {"x": 679.5, "duration": 1.5}

    def test_recurses_through_lists_and_nested_dicts(self) -> None:
        node = {"elements": [{"x": 1.0, "data": [[2.0, 3.5]]}], "t": {"delay": 0.0}}
        _round_slide_numbers(node)
        assert node == {"elements": [{"x": 1, "data": [[2, 3.5]]}], "t": {"delay": 0}}

    def test_booleans_are_not_mangled(self) -> None:
        node = {"skipped": True, "automatic": False}
        _round_slide_numbers(node)
        assert node["skipped"] is True
        assert node["automatic"] is False


class TestChunking:
    def test_batches_preserve_order_and_cover_everything(self) -> None:
        got = _chunks(list(range(1, 36)), 10)
        assert [len(c) for c in got] == [10, 10, 10, 5]
        assert [n for c in got for n in c] == list(range(1, 36))

    def test_empty(self) -> None:
        assert _chunks([], 10) == []


class TestDetailValidation:
    async def test_unknown_detail_is_rejected(self, deck_tools, mock_subprocess_run) -> None:
        result = await deck_tools.describe_deck(doc_name="D.key", detail="medium")
        assert "detail must be" in result[0].text


FS, RS, GS = "\x1f", "\x1e", "\x1d"


def _record(
    slide: int,
    texts: list[str],
    counts: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0),
    skipped: bool = False,
    title_shown: bool = False,
    default_title: str | None = "",
    has_body: bool = True,
) -> str:
    """One slide as the batched summary script emits it."""
    fields = [
        str(slide),
        str(len(texts)),
        *(str(c) for c in counts),
        str(skipped).lower(),
        str(title_shown).lower(),
        "" if default_title is None else default_title,
        str(has_body).lower(),
        str(default_title is not None).lower(),
        "".join(t + GS for t in texts),
    ]
    return FS.join(fields) + RS


class TestBatchedSummary:
    """The summary reads a class at a time: ~10 Apple events for any deck.

    On macOS 27 each Apple event costs ~17 ms, so the old per-slide loop took
    12 s on the 35-slide profiling deck; batched it takes 0.35 s, with output
    identical to the per-slide path on every deck in the live harness.
    """

    def _tools(self, raw: str) -> tuple[Any, MagicMock]:
        tools = DeckTools()
        runner = MagicMock()
        runner.run.return_value = raw.strip()  # the real runner strips stdout
        tools.runner = runner
        return tools, runner

    def test_one_phantom_per_existing_default_item_is_subtracted(self) -> None:
        # 2 real items + hidden title + hidden body placeholders
        raw = _record(1, ["Hello", "World", "", ""], counts=(1, 0, 0, 0, 2))
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert entry["counts"] == {"text": 2, "image": 1, "line": 2}
        assert entry["elements"] == 5

    def test_a_showing_title_is_the_title(self) -> None:
        raw = _record(
            1, ["Big idea", "body", "Big idea", ""], title_shown=True, default_title="Big idea"
        )
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert entry["title"] == "Big idea"
        assert entry["counts"] == {"text": 2}

    def test_a_hidden_title_falls_back_to_the_first_non_empty_real_text(self) -> None:
        raw = _record(1, ["", "Second", "ghost", ""], default_title="ghost")
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert entry["title"] == "Second"

    def test_phantom_text_is_never_the_title(self) -> None:
        raw = _record(1, ["", "", "phantom title text", ""], default_title="phantom title text")
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert "title" not in entry

    def test_trailing_empty_texts_stripped_by_the_runner_are_restored(self) -> None:
        # The last record ends in separators that str.strip() eats.
        raw = _record(1, ["A", "", ""]) + _record(2, ["Only", "", ""])
        tools, _ = self._tools(raw)
        entries = tools._summarize_slides("d.key", [1, 2])
        assert [e["counts"] for e in entries] == [{"text": 1}, {"text": 1}]

    def test_missing_default_items_add_no_phantoms(self) -> None:
        raw = _record(1, ["A", "B"], default_title=None, has_body=False)
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert entry["counts"] == {"text": 2}

    def test_a_title_that_reads_none_is_still_a_title(self) -> None:
        # The has-title flag is its own field: a marker value in the title
        # field once made a title of "none" read as "no title placeholder",
        # counting the phantom as a real item and its text as the title.
        # 2 real (empty) items, then the hidden title and body phantoms.
        raw = _record(1, ["", "", "none", ""], default_title="none")
        tools, _ = self._tools(raw)
        [entry] = tools._summarize_slides("d.key", [1])
        assert entry["counts"] == {"text": 2}  # was 3: the phantom counted as real
        assert "title" not in entry  # was "none": the phantom's text

    def test_skipped_and_slide_subset(self) -> None:
        raw = (
            _record(1, ["a", "", ""])
            + _record(2, ["b", "", ""], skipped=True)
            + _record(3, ["c", "", ""])
        )
        tools, _ = self._tools(raw)
        entries = tools._summarize_slides("d.key", [2, 3])
        assert [e["slide"] for e in entries] == [2, 3]
        assert entries[0]["skipped"] is True
        assert "skipped" not in entries[1]

    def test_the_whole_deck_is_one_osascript_call(self) -> None:
        raw = "".join(_record(n, ["t", "", ""]) for n in range(1, 36))
        tools, runner = self._tools(raw)
        assert len(tools._summarize_slides("d.key", list(range(1, 36)))) == 35
        assert runner.run.call_count == 1
        script = runner.run.call_args.args[0]
        assert "of every slide of targetDoc" in script
        assert "repeat with slideNum" not in script

    def test_inconsistent_counts_fall_back_to_the_per_slide_path(self) -> None:
        # fewer text items than default items: the count rule does not hold
        bad = _record(1, [""])
        per_slide = (
            "1"
            + FS
            + "1"
            + FS
            + "0" * 1
            + FS
            + "0"
            + FS
            + "0"
            + FS
            + "0"
            + FS
            + "0"
            + FS
            + "false"
            + FS
            + "Fallback"
            + RS
        )
        tools, runner = self._tools(bad)
        runner.run.side_effect = [bad.strip(), per_slide.strip()]
        [entry] = tools._summarize_slides("d.key", [1])
        assert runner.run.call_count == 2
        assert entry["title"] == "Fallback"


def _rec(*fields: object) -> str:
    return FS.join(str(f) for f in fields) + RS


def _slide_records(slide: int, *elements: str, groups: int = 0) -> str:
    return (
        _rec("D", slide)
        + _rec("L", "Blank")
        + _rec("K", "false")
        + "".join(elements)
        + _rec("GRP", groups)
    )


_TEXT = _rec("T", "Hello", 10, 20, 300, 40, "Helvetica", 24, "0,0,0", 1, "", 0, 100, "no fill", "")


class TestBatchedDescribe:
    """The full read, a class at a time: one event per property, not per element.

    The per-element path sent ~200 Apple events per slide, which at ~17 ms each
    on macOS 27 took 17.3 s for five slides of the profiling deck. The batched
    path emits the same records, so both share one parser.
    """

    def _tools(self, *raws: str) -> tuple[Any, MagicMock]:
        tools = DeckTools()
        runner = MagicMock()
        runner.run.side_effect = [r.strip() for r in raws]  # the real runner strips stdout
        tools.runner = runner
        return tools, runner

    def test_one_osascript_call_reads_the_span_a_class_at_a_time(self) -> None:
        raw = _slide_records(2, _TEXT) + _slide_records(4)
        tools, runner = self._tools(raw)
        slides = tools._describe_slides("d.key", [2, 4])
        assert [s["slide"] for s in slides] == [2, 4]
        assert slides[0]["elements"][0]["text"] == "Hello"
        assert runner.run.call_count == 1
        script = runner.run.call_args.args[0]
        assert "every text item of slides 2 thru 4 of targetDoc" in script
        assert "repeat with slideRef in {2, 4}" in script
        # the per-element path's app-side identity loop is gone
        assert "set ti to text item i" not in script

    def test_the_document_name_is_argv_not_source(self) -> None:
        tools, runner = self._tools(_slide_records(1))
        tools._describe_slides('evil" & quit & "', [1])
        assert "evil" not in runner.run.call_args.args[0]
        assert runner.run.call_args.args[1] == 'evil" & quit & "'

    def test_element_types_skip_whole_class_reads(self) -> None:
        tools, runner = self._tools(_slide_records(1))
        tools._describe_slides("d.key", [1], frozenset({"line"}))
        script = runner.run.call_args.args[0]
        assert "start point of every line" in script
        for absent in ("every text item", "every image", "every shape", "every table"):
            assert absent not in script

    def test_text_runs_off_skips_the_character_reads(self) -> None:
        tools, runner = self._tools(_slide_records(1))
        tools._describe_slides("d.key", [1], include_text_runs=False)
        assert "every character" not in runner.run.call_args.args[0]

    def test_trailing_empty_fields_stripped_by_the_runner_are_restored(self) -> None:
        # A stream ending in a text record whose optional fields are all empty:
        # str.strip() eats the trailing separators.
        raw = (
            _rec("D", 1)
            + _rec("L", "Blank")
            + _rec("T", "Hi", 0, 0, 10, 10, "", "", "", 1, "", "", "", "", "")
        )
        tools, _ = self._tools(raw)
        [slide] = tools._describe_slides("d.key", [1])
        el = slide["elements"][0]
        assert el["text"] == "Hi"
        assert "font_size" not in el and "fill_type" not in el and "runs" not in el

    def test_a_failed_batched_read_falls_back_to_the_per_element_path(self) -> None:
        tools = DeckTools()
        runner = MagicMock()
        runner.run.side_effect = [
            AppleScriptError("AppleEvent handler failed. (-10000)"),
            _slide_records(1, _TEXT).strip(),
        ]
        tools.runner = runner
        [slide] = tools._describe_slides("d.key", [1])
        assert runner.run.call_count == 2
        assert "set ti to text item i" in runner.run.call_args_list[1].args[0]
        assert slide["elements"][0]["index"] == 1

    def test_a_timed_out_batched_read_does_not_fall_back(self) -> None:
        # Keynote is wedged or still busy with the batched event: a second,
        # longer per-element read would double the wait or land on the wedge.
        tools = DeckTools()
        runner = MagicMock()
        runner.run.side_effect = AppleScriptTimeout("osascript timed out after 120s.")
        tools.runner = runner
        with pytest.raises(AppleScriptTimeout):
            tools._describe_slides("d.key", [1])
        assert runner.run.call_count == 1
        runner.run.reset_mock()
        with pytest.raises(AppleScriptTimeout):
            tools._summarize_slides("d.key", [1])
        assert runner.run.call_count == 1

    def test_a_sparse_range_is_read_in_bounded_spans(self) -> None:
        # The batched read covers `slides lo thru hi`; chunking "1-10,290-300"
        # by count alone read 290 slides in one session.
        wanted = list(range(1, 11)) + list(range(290, 301))
        chunks = deck_mod._span_chunks(wanted, deck_mod._DESCRIBE_BATCH_SLIDES)
        assert [c[-1] - c[0] + 1 <= deck_mod._DESCRIBE_BATCH_SLIDES for c in chunks] == [
            True
        ] * len(chunks)
        assert [n for c in chunks for n in c] == wanted
        assert chunks == [list(range(1, 11)), list(range(290, 301))]
        dense = list(range(1, 36))
        assert deck_mod._span_chunks(dense, 20) == [dense[:20], dense[20:]]

    def test_records_for_the_wrong_slides_fall_back(self) -> None:
        tools, runner = self._tools(_slide_records(1), _slide_records(1) + _slide_records(2))
        slides = tools._describe_slides("d.key", [1, 2])
        assert runner.run.call_count == 2
        assert [s["slide"] for s in slides] == [1, 2]

    def test_line_endpoints_are_read_after_the_slides_line_positions(self) -> None:
        # Keynote 15.3.1 reads endpoints as 0,0 unless the slide's line
        # positions were read just before, so both paths read them first.
        tools, runner = self._tools(_slide_records(1), _slide_records(1))
        tools._describe_slides("d.key", [1], frozenset({"line"}))
        batched = runner.run.call_args.args[0]
        warm = batched.index("position of every line of slide n of targetDoc")
        assert warm < batched.index("start point of every line of slide n of targetDoc")
        assert "start point of every line of slides" not in batched
        tools._describe_slides_per_element("d.key", [1], frozenset({"line"}))
        per_element = runner.run.call_args.args[0]
        assert per_element.index("position of every line") < per_element.index("start point")

    def test_no_other_module_reads_line_endpoints(self) -> None:
        # Probed live: get_slide_content lists no lines, move/resize reject
        # them, and add_line/build_deck read back position and size, which
        # read correctly cold. A new endpoint reader needs _LINE_WARM_UP.
        package = Path(deck_mod.__file__).parents[1]
        readers = sorted(
            p.name
            for p in package.rglob("*.py")
            if re.search(r"(start|end) point of", p.read_text())
        )
        assert readers == ["deck.py"]

    def test_geometry_comes_from_one_properties_read_with_a_fallback(self) -> None:
        # Keynote 15.3.1 charges every geometry read per slide, so position,
        # width, height and rotation come from one `properties` read; the
        # per-property reads stay in its `on error` branch.
        block = _props_read("table", "SPAN", [("tbW", "width")], ["\nFALLBACK"])
        assert "set propsAll to properties of every table of SPAN" in block
        assert "set end of tbWOne to width of rec" in block
        assert block.index("on error") < block.index("FALLBACK")
        tools, runner = self._tools(_slide_records(1))
        tools._describe_slides("d.key", [1])
        script = runner.run.call_args.args[0]
        for cls in ("text item", "shape", "table", "chart"):
            assert f"properties of every {cls} of slides 1 thru 1" in script
        # images cannot use it: `properties of every image` fails (-10000)
        assert "properties of every image" not in script

    def test_soft_reads_degrade_per_slide_then_per_element(self) -> None:
        block = _soft_class_read("v", "rotation", "image", "slides 1 thru 3 of targetDoc", 1, 3)
        assert "set v to rotation of every image of slides 1 thru 3 of targetDoc" in block
        assert "(rotation of every image of slide n of targetDoc)" in block
        assert "set x to rotation of image i of slide n of targetDoc" in block
        direct = _soft_class_read("v", "file", "image", "s", 1, 3, per_slide=False)
        assert "(file of every image of slide n of targetDoc)" not in direct
        assert "set x to file of image i of slide n of targetDoc" in direct

    def test_both_text_item_walks_share_one_predicate(self) -> None:
        assert _TEXT_ITEM_PREDICATE in TEXT_ITEM_FILTER
        assert _TEXT_ITEM_PREDICATE in TEXT_ITEM_CLASSIFY
        assert "set ti to item i of tRefs" in TEXT_ITEM_CLASSIFY
