"""edit_table against a mocked runner: validation stops before osascript,
ranges are bounds-checked against the post-resize size, and user strings
travel as argv."""

import subprocess

import pytest

from keynote_mcp.tools.fragments import parse_cell, parse_range
from keynote_mcp.utils import ParameterError


def _cp(cmd, stdout):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")


def _table_run(size="4,3", reply="4,3|10,20|400x200", calls=None):
    """First call reads the table size, the second applies the edits."""

    def fake_run(cmd, **kwargs):
        script = kwargs.get("input", "")
        if calls is not None:
            calls.append((cmd, script))
        if "System Events" in script:
            return _cp(cmd, "true")
        if "return (row count as text)" in script:
            return _cp(cmd, size)
        return _cp(cmd, reply)

    return fake_run


class TestCellParsing:
    def test_cells_and_ranges(self):
        assert parse_cell("B2") == (2, 2)
        assert parse_cell("aa10") == (10, 27)
        assert parse_range("C3:A1") == (1, 1, 3, 3)
        assert parse_range("B2") == (2, 2, 2, 2)

    @pytest.mark.parametrize("bad", ["", "2B", "A0", "A1:", 'A1"; quit', 5, None])
    def test_garbage_is_rejected(self, bad):
        with pytest.raises(ParameterError):
            parse_range(bad)


class TestEditTableValidation:
    async def test_bad_slide_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.edit_table(0, 1, merge=["A1:B1"])
        assert result[0].text.startswith("Failed to edit table")
        assert not mock_subprocess_run.called

    async def test_nothing_to_edit_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.edit_table(1, 1)
        assert "Nothing to edit" in result[0].text
        assert not mock_subprocess_run.called

    async def test_shrink_below_two_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.edit_table(1, 1, row_count=1)
        assert "Failed" in result[0].text
        assert not mock_subprocess_run.called

    async def test_out_of_bounds_range_stops_after_size_read(
        self, object_tools, mock_subprocess_run
    ):
        calls = []
        mock_subprocess_run.side_effect = _table_run(calls=calls)
        result = await object_tools.edit_table(1, 1, merge=["A1:D1"], doc_name="d")
        assert "outside the 4x3 table" in result[0].text
        assert len(calls) == 1  # the size read; nothing was applied

    async def test_bounds_use_the_size_after_resizing(self, object_tools, mock_subprocess_run):
        calls = []
        mock_subprocess_run.side_effect = _table_run(calls=calls)
        result = await object_tools.edit_table(1, 1, column_count=4, merge=["A1:D1"], doc_name="d")
        assert result[0].text.startswith("Edited table 1")
        assert len(calls) == 2

    async def test_values_past_the_edge_are_rejected(self, object_tools, mock_subprocess_run):
        mock_subprocess_run.side_effect = _table_run()
        result = await object_tools.edit_table(
            1, 1, values=[["a", "b"]], start_cell="C4", doc_name="d"
        )
        assert "lands on D4 outside" in result[0].text

    @pytest.mark.parametrize(
        "style",
        [
            {"range": "A1", "alignment": "middle"},
            {"range": "A1", "fill_color": "#fff"},
            {"range": "A1"},
            {"font_size": 12},
        ],
    )
    async def test_bad_styles_are_rejected(self, object_tools, mock_subprocess_run, style):
        mock_subprocess_run.side_effect = _table_run()
        result = await object_tools.edit_table(1, 1, styles=[style], doc_name="d")
        assert result[0].text.startswith("Failed to edit table")


class TestEditTableScript:
    async def test_steps_run_in_documented_order(self, object_tools, mock_subprocess_run):
        calls = []
        mock_subprocess_run.side_effect = _table_run(calls=calls)
        result = await object_tools.edit_table(
            2,
            1,
            values=[["Name", None, ""], [1.5, True]],
            row_count=5,
            header_rows=1,
            clear=["C3"],
            sort={"column": "B", "direction": "descending", "rows": "A2:C5"},
            unmerge=["A1:C1"],
            merge=["c1:a1"],
            styles=[
                {
                    "range": "A1:C1",
                    "alignment": "center",
                    "vertical_alignment": "top",
                    "background_color": "#2F4B7C",
                    "format": "percent",
                    "wrap": False,
                    "font_size": 20,
                }
            ],
            column_widths=[120, None, 80],
            row_heights=[40],
            doc_name="d",
        )
        script = calls[-1][1]
        order = [
            "set row count to 5",
            "set header row count to 1",
            'clear range "C3:C3"',
            "set value of cell 1 of row 1 to (item 2 of argv)",
            "set value of cell 3 of row 1 to missing value",
            "set value of cell 1 of row 2 to 1.5",
            "set value of cell 2 of row 2 to true",
            'sort by column 2 direction descending in rows (range "A2:C5")',
            'unmerge range "A1:C1"',
            'merge range "A1:C1"',
            'set background color of range "A1:C1" to {12079, 19275, 31868}',
            'set alignment of range "A1:C1" to center',
            'set vertical alignment of range "A1:C1" to top',
            'set format of range "A1:C1" to percent',
            'set text wrap of range "A1:C1" to false',
            "set width of column 1 to 120",
            "set height of row 1 to 40",
        ]
        positions = [script.index(line) for line in order]
        assert positions == sorted(positions)
        assert "set value of cell 2 of row 1" not in script  # null = unchanged
        assert "set width of column 2" not in script
        assert 'set font size of range "A1:C1" to 20' in script
        assert "Now 4x3 at (10, 20), size 400x200" in result[0].text

    async def test_a_failing_step_is_named(self, object_tools, mock_subprocess_run):
        def fake_run(cmd, **kwargs):
            script = kwargs.get("input", "")
            if "return (row count as text)" in script:
                return _cp(cmd, "4,3")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="execution error: step 'merge A1:C1' failed, earlier steps "
                "stayed applied: nope (-10000)",
            )

        mock_subprocess_run.side_effect = fake_run
        result = await object_tools.edit_table(1, 1, merge=["A1:C1"], doc_name="d")
        assert "merge A1:C1" in result[0].text
