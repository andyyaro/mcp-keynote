"""PHASE 9 Task 3 — describe_deck at real-deck scale.

The field report: 137,091 characters and >120 s on a 35-slide deck, blowing
both the tool-output limit and the timeout, with no way to page. Profiled here
on a generated 35-slide/735-element deck before changing anything: 31.2 s of
which ~4.5 s was pure process overhead (0.125 s x 36 calls, one per slide), and
2,415 trailing '.0' carrying no information.
"""

from __future__ import annotations

import pytest

from keynote_mcp.tools.deck import (
    _ALL_ELEMENT_CLASSES,
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
