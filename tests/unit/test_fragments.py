"""Shared AppleScript fragment builders: argv allocation, validation error
paths, trusted literal maps, and single-fragment execution/parsing."""

import pytest

from keynote_mcp.tools.fragments import (
    CHART_TYPES,
    TRANSITION_EFFECTS,
    Argv,
    _column_letter,
    _fmt_num,
    chart_fragment,
    image_fragment,
    line_fragment,
    notes_fragment,
    placeholder_fragment,
    range_name,
    run_single_fragment,
    shape_fragment,
    skipped_fragment,
    table_fragment,
    text_item_fragment,
    transition_fragment,
)
from keynote_mcp.utils import ParameterError


class TestArgv:
    def test_ref_allocates_sequential_slots(self):
        argv = Argv()
        assert argv.ref("first") == "(item 1 of argv)"
        assert argv.ref("second") == "(item 2 of argv)"
        assert argv.values == ["first", "second"]

    def test_repeated_values_get_distinct_slots(self):
        argv = Argv()
        argv.ref("same")
        assert argv.ref("same") == "(item 2 of argv)"


class TestFmtNum:
    def test_whole_floats_become_ints(self):
        assert _fmt_num(2.0) == "2"
        assert _fmt_num(0) == "0"

    def test_fractions_keep_decimals(self):
        assert _fmt_num(1.5) == "1.5"
        assert _fmt_num(0.25) == "0.25"


class TestRangeNames:
    def test_column_letters(self):
        assert _column_letter(1) == "A"
        assert _column_letter(26) == "Z"
        assert _column_letter(27) == "AA"
        assert _column_letter(52) == "AZ"
        assert _column_letter(53) == "BA"
        assert _column_letter(703) == "AAA"

    def test_range_name(self):
        assert range_name(1, 1, 3, 2) == "A1:B3"
        assert range_name(1, 1, 1, 27) == "A1:AA1"


class TestLiteralMaps:
    def test_chart_types_contain_expected_entries(self):
        assert CHART_TYPES["bar"] == "vertical_bar_2d"
        assert CHART_TYPES["pie"] == "pie_2d"
        assert CHART_TYPES["scatter"] == "scatterplot_2d"
        assert CHART_TYPES["stacked_bar_3d"] == "stacked_vertical_bar_3d"

    def test_transition_effects_underscore_keys_map_to_spaced_names(self):
        assert TRANSITION_EFFECTS["magic_move"] == "magic move"
        assert TRANSITION_EFFECTS["fade_through_color"] == "fade through color"
        assert TRANSITION_EFFECTS["push"] == "push"
        assert TRANSITION_EFFECTS["no_transition_effect"] == "no transition effect"


class TestTextItemFragment:
    def test_user_text_goes_through_argv(self):
        argv = Argv()
        lines = text_item_fragment(argv, "T", 'evil "text"', font_name="Font")
        source = "\n".join(lines)
        assert 'evil "text"' not in source
        assert argv.values == ['evil "text"', "Font"]

    def test_font_size_out_of_range_raises(self):
        with pytest.raises(ParameterError):
            text_item_fragment(Argv(), "T", "t", font_size=501)

    def test_centered_adds_div2_math(self):
        lines = text_item_fragment(Argv(), "T", "t", centered=True)
        assert any("div 2" in line for line in lines)


class TestShapeAndLineFragments:
    def test_shape_opacity_out_of_range_raises(self):
        with pytest.raises(ParameterError):
            shape_fragment(Argv(), "S", opacity=101)

    def test_shape_text_via_argv(self):
        argv = Argv()
        lines = shape_fragment(argv, "S", text="label")
        source = "\n".join(lines)
        assert "label" not in source
        assert "label" in argv.values
        assert any("make new shape" in line for line in lines)

    def test_line_rejects_negative_coordinates(self):
        with pytest.raises(ParameterError):
            line_fragment("L", x1=-1, y1=0, x2=10, y2=10)

    def test_line_interpolates_validated_numbers(self):
        lines = line_fragment("L", x1=1, y1=2, x2=3.5, y2=4)
        script = "\n".join(lines)
        assert "start point:{1, 2}" in script
        assert "end point:{3.5, 4}" in script


class TestImageFragment:
    def test_path_and_description_via_argv(self):
        argv = Argv()
        lines = image_fragment(argv, "I", "/tmp/pic.png", description="desc")
        source = "\n".join(lines)
        assert "/tmp/pic.png" not in source
        assert "POSIX file (item 1 of argv)" in source
        assert argv.values == ["/tmp/pic.png", "desc"]


class TestTableFragment:
    def test_rejects_tables_smaller_than_2x2(self):
        with pytest.raises(ParameterError, match="at least 2 rows"):
            table_fragment(Argv(), "TB", [["only"]])
        with pytest.raises(ParameterError, match="at least 2 rows"):
            table_fragment(Argv(), "TB", [["a"], ["b"]])
        with pytest.raises(ParameterError, match="at least 2 rows"):
            table_fragment(Argv(), "TB", [["a", "b"]])

    def test_rejects_ragged_rows(self):
        with pytest.raises(ParameterError, match="same number of columns"):
            table_fragment(Argv(), "TB", [["a", "b"], ["c"]])

    def test_rejects_too_many_column_widths(self):
        with pytest.raises(ParameterError, match="column_widths"):
            table_fragment(Argv(), "TB", [["a", "b"], ["c", "d"]], column_widths=[1, 2, 3])

    def test_numbers_interpolated_strings_via_argv(self):
        argv = Argv()
        lines = table_fragment(argv, "TB", [["Region", "Q1"], ["North", 120]])
        source = "\n".join(lines)
        assert "set value of cell 2 of row 2 to 120" in source
        assert "Region" not in source
        assert "North" not in source
        assert "Region" in argv.values
        assert "North" in argv.values

    def test_empty_and_none_cells_are_skipped(self):
        lines = table_fragment(Argv(), "TB", [["", None], ["x", True]])
        source = "\n".join(lines)
        assert "cell 1 of row 1" not in source
        assert "cell 2 of row 1" not in source
        assert "set value of cell 2 of row 2 to true" in source

    def test_header_styling_targets_header_range(self):
        lines = table_fragment(
            Argv(),
            "TB",
            [["a", "b", "c"], ["d", "e", "f"]],
            header_bg=(1, 2, 3),
            header_color=(4, 5, 6),
            header_font_size=20,
        )
        source = "\n".join(lines)
        assert 'set background color of range "A1:C1" to {1, 2, 3}' in source
        assert 'set text color of range "A1:C1" to {4, 5, 6}' in source
        assert 'set font size of range "A1:C1" to 20' in source


def _good_chart():
    return {
        "chart_type": "bar",
        "row_names": ["r1", "r2"],
        "column_names": ["c1", "c2", "c3"],
        "data": [[1, 2, 3], [4, 5, 6]],
    }


class TestChartFragment:
    def test_unknown_chart_type_raises(self):
        with pytest.raises(ParameterError, match="Unknown chart_type"):
            chart_fragment(Argv(), "CH", **{**_good_chart(), "chart_type": "donut"})

    def test_bad_group_by_raises(self):
        with pytest.raises(ParameterError, match="group_by"):
            chart_fragment(Argv(), "CH", **_good_chart(), group_by="series")

    def test_empty_inputs_raise(self):
        with pytest.raises(ParameterError, match="needs row_names"):
            chart_fragment(Argv(), "CH", **{**_good_chart(), "data": []})

    def test_row_count_mismatch_raises(self):
        with pytest.raises(ParameterError, match="row_names"):
            chart_fragment(Argv(), "CH", **{**_good_chart(), "data": [[1, 2, 3]]})

    def test_column_count_mismatch_raises(self):
        with pytest.raises(ParameterError, match="column_names"):
            chart_fragment(Argv(), "CH", **{**_good_chart(), "data": [[1, 2], [3, 4]]})

    def test_names_via_argv_numbers_interpolated(self):
        argv = Argv()
        lines = chart_fragment(argv, "CH", **_good_chart())
        source = "\n".join(lines)
        assert "r1" in argv.values
        assert "c3" in argv.values
        assert "r1" not in source
        assert "{{1, 2, 3}, {4, 5, 6}}" in source
        assert "type vertical_bar_2d" in source
        assert "set current slide of targetDoc to targetSlide" in source


class TestSlidePropertyFragments:
    def test_transition_rejects_unknown_effect(self):
        with pytest.raises(ParameterError, match="Unknown transition effect"):
            transition_fragment(effect="teleport")

    def test_transition_emits_mapped_literal(self):
        (line,) = transition_fragment(effect="magic_move", duration=2, delay=0.5, automatic=True)
        assert "transition effect:magic move" in line
        assert "transition duration:2" in line
        assert "transition delay:0.5" in line
        assert "automatic transition:true" in line

    def test_transition_duration_bounds(self):
        with pytest.raises(ParameterError):
            transition_fragment(effect="push", duration=61)

    def test_skipped_fragment_is_a_standalone_statement(self):
        assert skipped_fragment(True) == ["set skipped of targetSlide to true"]
        assert skipped_fragment(False) == ["set skipped of targetSlide to false"]

    def test_notes_via_argv(self):
        argv = Argv()
        (line,) = notes_fragment(argv, "secret notes")
        assert "secret notes" not in line
        assert argv.values == ["secret notes"]

    def test_placeholder_fragment_title_only(self):
        argv = Argv()
        lines = placeholder_fragment(argv, "PH", title="T")
        source = "\n".join(lines)
        assert "set title showing to true" in source
        assert "default body item" not in source
        assert "placeholders-set" in source
        assert argv.values == ["T"]

    def test_placeholder_fragment_empty_emits_nothing(self):
        assert placeholder_fragment(Argv(), "PH") == []


class TestRunSingleFragment:
    def test_parses_result_token(self, runner, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "T|1|10,20|30,40"
        argv = Argv()
        argv.ref("doc name")
        lines = text_item_fragment(argv, "T", "hello")
        index, pos, size = run_single_fragment(runner, "doc name", 2, argv, lines)
        assert (index, pos, size) == ("1", "10,20", "30,40")
        script = mock_subprocess_run.call_args.kwargs["input"]
        assert "set targetSlide to slide 2 of targetDoc" in script
        assert mock_subprocess_run.call_args.args[0][2] == "doc name"

    def test_invalid_slide_number_never_runs(self, runner, mock_subprocess_run):
        with pytest.raises(ParameterError):
            run_single_fragment(runner, "", 0, Argv(), [])
        assert not mock_subprocess_run.called
