"""ObjectTools behavior with a mocked runner: validation failures never reach
osascript; happy paths generate the probed script forms."""

import os


def last_script(mock_run) -> str:
    return mock_run.call_args.kwargs["input"]


def last_cmd(mock_run) -> list:
    return mock_run.call_args.args[0]


class TestAddTable:
    async def test_bad_slide_number_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.add_table(0, [["a", "b"], ["c", "d"]])
        assert "Failed to add table" in result[0].text
        assert not mock_subprocess_run.called

    async def test_too_small_table_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.add_table(1, [["only"]])
        assert "at least 2 rows" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_styles_header_range(
        self, object_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)  # keep style resolution at built-in plain
        mock_subprocess_run.return_value.stdout = "TB|1|0,0|600,300"
        result = await object_tools.add_table(2, [["Region", "Q1"], ["North", 120]], x=10, y=20)
        script = last_script(mock_subprocess_run)
        # strings via argv, numbers interpolated after validation
        assert "Region" not in script
        assert "Region" in last_cmd(mock_subprocess_run)[2:]
        assert "set value of cell 2 of row 2 to 120" in script
        # plain style: header bg #2F4B7C, header text #FFFFFF on the A1:B1 range
        assert 'set background color of range "A1:B1" to {12079, 19275, 31868}' in script
        assert 'set text color of range "A1:B1" to {65535, 65535, 65535}' in script
        assert 'set font size of range "A1:B2" to 18' in script
        assert "Added 2x2 table to slide 2 (table index 1) at (0, 0), size 600x300" in (
            result[0].text
        )


class TestAddChart:
    async def test_unknown_chart_type_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.add_chart(1, "donut", ["r"], ["c"], [[1]])
        assert "Unknown chart_type" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_sets_current_slide_and_adds_chart(
        self, object_tools, mock_subprocess_run
    ):
        mock_subprocess_run.return_value.stdout = "CH|1|10,20|800,400"
        result = await object_tools.add_chart(1, "line", ["r1"], ["c1", "c2"], [[1, 2]], width=800)
        script = last_script(mock_subprocess_run)
        assert "set current slide of targetDoc to targetSlide" in script
        assert "add chart row names" in script
        assert "type line_2d" in script
        assert "chart index 1" in result[0].text
        assert "write-once" in result[0].text


class TestAddLine:
    async def test_happy_path(self, object_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "LN|2|0,0|100,50"
        result = await object_tools.add_line(1, 0, 0, 100, 50)
        assert "line index 2" in result[0].text
        assert "make new line" in last_script(mock_subprocess_run)

    async def test_negative_coordinate_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.add_line(1, -5, 0, 10, 10)
        assert "Failed to add line" in result[0].text
        assert not mock_subprocess_run.called


class TestAddColoredPanel:
    async def test_renders_real_png_and_places_it_via_argv(
        self, object_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        mock_subprocess_run.return_value.stdout = "PN|1|10,20|300,200"
        result = await object_tools.add_colored_panel(
            1, 10, 20, 300, 200, color="#3B6ECC", radius=12
        )
        script = last_script(mock_subprocess_run)
        assert "POSIX file (item 2 of argv)" in script
        png_path = last_cmd(mock_subprocess_run)[3]
        # The filename carries the panel's parameters so describe_deck can
        # report `type: panel` with its colour instead of an anonymous image,
        # and build_deck can re-render it. See utils/rendered_assets.py.
        from keynote_mcp.utils.rendered_assets import decode_rendered_asset

        decoded = decode_rendered_asset(os.path.basename(png_path))
        assert decoded is not None, png_path
        assert decoded["type"] == "panel"
        assert decoded["color"] == "#3B6ECC"
        assert decoded["radius"] == 12
        assert open(png_path, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
        assert "not a native" in result[0].text

    async def test_invalid_opacity_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.add_colored_panel(1, 0, 0, 10, 10, opacity=101)
        assert "Failed to add colored panel" in result[0].text
        assert not mock_subprocess_run.called


class TestStyleTextRange:
    async def test_nothing_to_style_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.style_text_range(1, 1, 1, 3)
        assert "Nothing to style" in result[0].text
        assert not mock_subprocess_run.called

    async def test_end_before_start_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.style_text_range(1, 1, 5, 2, color="#000000")
        assert "must be >= start" in result[0].text
        assert not mock_subprocess_run.called

    async def test_bad_unit_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.style_text_range(1, 1, 1, 2, unit="letters", color="#000000")
        assert "Invalid unit" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_targets_range_font_via_argv(self, object_tools, mock_subprocess_run):
        result = await object_tools.style_text_range(
            1, 2, 2, 3, unit="words", color="#FF0000", font_name="Helvetica-Bold", font_size=24
        )
        script = last_script(mock_subprocess_run)
        assert "words 2 thru 3 of object text of text item 2" in script
        assert "set font of" in script
        assert "(item 2 of argv)" in script
        assert "Helvetica-Bold" not in script
        assert "Helvetica-Bold" in last_cmd(mock_subprocess_run)[2:]
        assert "to 24" in script
        assert "{65535, 0, 0}" in script
        assert "Styled words 2-3 of text item 2" in result[0].text


class TestReplaceImage:
    async def test_missing_file_never_runs(self, object_tools, mock_subprocess_run, tmp_path):
        result = await object_tools.replace_image(1, 1, str(tmp_path / "no.png"))
        assert "file does not exist" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_uses_posix_file_and_exists_guard(
        self, object_tools, mock_subprocess_run, tmp_path
    ):
        img = tmp_path / "new.png"
        img.write_bytes(b"png")
        result = await object_tools.replace_image(1, 2, str(img))
        script = last_script(mock_subprocess_run)
        assert "if not (exists image 2)" in script
        assert "set file name of image 2 to POSIX file imagePath" in script
        assert os.path.realpath(str(img)) in last_cmd(mock_subprocess_run)[2:]
        assert "Replaced image 2 on slide 1" in result[0].text
        assert "geometry preserved" in result[0].text


class TestSetElementStyle:
    async def test_nothing_to_set_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.set_element_style(1, "shape", 1)
        assert "Nothing to set" in result[0].text
        assert not mock_subprocess_run.called

    async def test_bad_element_type_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.set_element_style(1, "table", 1, rotation=45)
        assert "Invalid element type" in result[0].text
        assert not mock_subprocess_run.called

    async def test_rotation_out_of_range_never_runs(self, object_tools, mock_subprocess_run):
        result = await object_tools.set_element_style(1, "shape", 1, rotation=360)
        assert "Failed to set element style" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_sets_only_requested_props(self, object_tools, mock_subprocess_run):
        result = await object_tools.set_element_style(
            1, "text", 3, rotation=45, locked=True, reflection_showing=False
        )
        script = last_script(mock_subprocess_run)
        assert "if not (exists text item 3)" in script
        assert "set rotation of targetItem to 45" in script
        assert "set locked of targetItem to true" in script
        assert "set reflection showing of targetItem to false" in script
        assert "set reflection value" not in script
        assert "rotation=45, reflection_showing=false, locked=true" in result[0].text
