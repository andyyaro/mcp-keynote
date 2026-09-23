"""PHASE 9 Task 3 — describe_deck at real-deck scale.

The field report: 137,091 characters and >120 s on a 35-slide deck, blowing
both the tool-output limit and the timeout, with no way to page. Profiled here
on a generated 35-slide/735-element deck before changing anything: 31.2 s of
which ~4.5 s was pure process overhead (0.125 s x 36 calls, one per slide), and
2,415 trailing '.0' carrying no information.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from keynote_mcp.tools.deck import (
    _ALL_ELEMENT_CLASSES,
    DeckTools,
    _chunks,
    _parse_element_types,
    _parse_slide_range,
    _round_slide_numbers,
)
from keynote_mcp.utils.error_handler import ParameterError


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
        "none" if default_title is None else default_title,
        str(has_body).lower(),
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
