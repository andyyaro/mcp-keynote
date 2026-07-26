"""Per-tool behavior with a mocked runner: script generation, result parsing,
and error paths."""

import subprocess


def last_script(mock_run) -> str:
    return mock_run.call_args.kwargs["input"]


def last_cmd(mock_run) -> list:
    return mock_run.call_args.args[0]


def _fail_with(mock_run, stderr):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["osascript", "-"], returncode=1, stdout="", stderr=stderr
    )


NOT_FOUND = (
    "execution error: Keynote got an error: Can’t get slide 9 of document 1. Invalid index. (-1719)"
)


class TestPresentationTools:
    async def test_create_uses_document_theme_property(
        self, presentation_tools, mock_subprocess_run
    ):
        mock_subprocess_run.return_value.stdout = "Doc|theme: Slate"
        result = await presentation_tools.create_presentation("t", theme="Slate")
        script = last_script(mock_subprocess_run)
        assert "document theme:theme themeName" in script
        assert "theme: Slate" in result[0].text

    async def test_create_without_save_path_saves_to_default(
        self, presentation_tools, mock_subprocess_run, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("KEYNOTE_MCP_SAVE_DIR", str(tmp_path))
        mock_subprocess_run.return_value.stdout = "t.key|default theme"
        result = await presentation_tools.create_presentation("t")
        assert f"saved to {tmp_path}/t.key" in result[0].text

    async def test_get_slide_size_parses_and_derives_layout(
        self, presentation_tools, mock_subprocess_run
    ):
        mock_subprocess_run.return_value.stdout = "1920,1080"
        result = await presentation_tools.get_slide_size()
        text = result[0].text
        assert "1920 x 1080" in text
        assert "16:9" in text
        assert "Center: (960, 540)" in text

    async def test_get_slide_size_4_3(self, presentation_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1024,768"
        assert "4:3" in (await presentation_tools.get_slide_size())[0].text

    async def test_theme_not_found_is_helpful(self, presentation_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "theme_not_found"
        result = await presentation_tools.set_presentation_theme("Nope")
        assert "get_available_themes" in result[0].text

    async def test_error_path_returns_failed_text(self, presentation_tools, mock_subprocess_run):
        _fail_with(mock_subprocess_run, NOT_FOUND)
        result = await presentation_tools.save_presentation()
        assert result[0].text.startswith("Failed to save presentation")

    async def test_open_rejects_empty_path(self, presentation_tools, mock_subprocess_run):
        result = await presentation_tools.open_presentation("   ")
        assert "Failed" in result[0].text


class TestSlideTools:
    async def test_move_slide_uses_before_after_not_replace(self, slide_tools, mock_subprocess_run):
        await slide_tools.move_slide(2, 5)
        assert "after slide 5" in last_script(mock_subprocess_run)
        await slide_tools.move_slide(5, 2)
        assert "before slide 2" in last_script(mock_subprocess_run)

    async def test_move_slide_same_position_is_noop(self, slide_tools, mock_subprocess_run):
        result = await slide_tools.move_slide(3, 3)
        assert "already at position" in result[0].text
        assert not mock_subprocess_run.called

    async def test_add_slide_defaults_to_blank(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "2|Blank"
        result = await slide_tools.add_slide()
        assert last_cmd(mock_subprocess_run)[3] == "Blank"
        assert "Added slide #2" in result[0].text

    async def test_add_slide_at_position_inserts_before(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "2|Blank"
        await slide_tools.add_slide(position=2)
        assert "before slide 2" in last_script(mock_subprocess_run)

    async def test_duplicate_computes_new_number(self, slide_tools, mock_subprocess_run):
        result = await slide_tools.duplicate_slide(3)
        assert "new number: 4" in result[0].text
        result = await slide_tools.duplicate_slide(3, new_position=2)
        assert "new number: 2" in result[0].text
        result = await slide_tools.duplicate_slide(3, new_position=5)
        assert "new number: 6" in result[0].text

    async def test_layout_not_found_is_helpful(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "layout_not_found"
        result = await slide_tools.set_slide_layout(1, "Nope")
        assert "get_available_layouts" in result[0].text

    async def test_error_path(self, slide_tools, mock_subprocess_run):
        _fail_with(mock_subprocess_run, NOT_FOUND)
        result = await slide_tools.delete_slide(9)
        assert "Failed to delete slide" in result[0].text
        assert "get_slide_count" in result[0].text

    async def test_get_slide_info_counts_only_real_text_items(
        self, slide_tools, mock_subprocess_run
    ):
        # The raw `count of text items` includes hidden placeholder phantoms;
        # get_slide_info must apply the same identity filter get_slide_content
        # uses.
        mock_subprocess_run.return_value.stdout = "1|||Blank|||0"
        result = await slide_tools.get_slide_info(1)
        script = last_script(mock_subprocess_run)
        assert "default title item" in script
        assert "set textCount to count of text items" not in script
        assert "Text item count: 0" in result[0].text


class TestContentTools:
    async def test_large_font_keeps_autofit_box_and_restores_text(
        self, content_tools, mock_subprocess_run
    ):
        # No pre-widening and no explicit height at >48pt: Keynote's auto-fit
        # box hugs the rendered text at every size (verified live at
        # 96/150/300/500pt), and a pre-widened box would break `centered` -
        # the box centers while the left-aligned text inside lands off-center.
        # An explicit height has no lasting effect anyway (snaps back to
        # auto-fit). The text re-set stays, AFTER the font size, as insurance
        # against auto-fit truncation regressions.
        mock_subprocess_run.return_value.stdout = "T|1|100,200|672,119"
        await content_tools.add_title(1, "Big Title Here", font_size=96)
        script = last_script(mock_subprocess_run)
        assert "set width of newItem" not in script
        assert "set height of newItem" not in script
        assert "set object text of newItem to (item 2 of argv)" in script
        assert script.index("set size of object text") < script.index(
            "set object text of newItem to (item 2 of argv)"
        )

    async def test_small_font_keeps_default_box(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_title(1, "small", font_size=36)
        assert "set width of newItem" not in last_script(mock_subprocess_run)

    async def test_centered_large_font_box_is_never_prewidened(
        self, content_tools, mock_subprocess_run
    ):
        # `centered` centers the BOX; the rendered text centers with it only
        # because the box is the natural auto-fit one. Any injected width
        # would reintroduce the ~60-110pt leftward visual drift measured on
        # the old 0.58*pt/char heuristic.
        mock_subprocess_run.return_value.stdout = "T|1|624,400|672,119"
        await content_tools.add_title(1, "Hello Big World", font_size=96, centered=True)
        script = last_script(mock_subprocess_run)
        assert "set width of newItem" not in script
        assert "set height of newItem" not in script
        assert "((width of targetDoc) - (width of newItem)) div 2" in script
        # centering must see the settled box: after font size AND text restore
        assert script.index("div 2") > script.index("set size of object text")
        assert script.index("div 2") > script.index(
            "set object text of newItem to (item 2 of argv)"
        )

    async def test_explicit_width_wins_over_autosize(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_text_box(1, "text", font_size=96, width=500, height=100)
        script = last_script(mock_subprocess_run)
        assert "set width of newItem to 500" in script

    async def test_bullets_join_with_real_newlines(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_bullet_list(1, ["a", "b"])
        assert "• a\n• b" in last_cmd(mock_subprocess_run)[3]

    async def test_numbered_list_numbers(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_numbered_list(1, ["x", "y"])
        assert "1. x\n2. y" in last_cmd(mock_subprocess_run)[3]

    async def test_code_block_defaults_to_monaco(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_code_block(1, "x = 1")
        assert "Monaco" in last_cmd(mock_subprocess_run)

    async def test_quote_wrapped_in_curly_quotes(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1"
        await content_tools.add_quote(1, "wisdom")
        assert "“wisdom”" in last_cmd(mock_subprocess_run)[3]

    async def test_add_image_missing_args_validated(self, content_tools, mock_subprocess_run):
        result = await content_tools.add_image(0, "/x.png")
        assert "Failed" in result[0].text
        assert not mock_subprocess_run.called

    async def test_set_slide_content_requires_something(self, content_tools, mock_subprocess_run):
        result = await content_tools.set_slide_content(1)
        assert "Nothing to set" in result[0].text
        assert not mock_subprocess_run.called

    async def test_set_slide_content_title_only(self, content_tools, mock_subprocess_run):
        await content_tools.set_slide_content(1, title="T")
        script = last_script(mock_subprocess_run)
        assert "default title item" in script
        assert "default body item" not in script

    async def test_opacity_bounds(self, content_tools, mock_subprocess_run):
        result = await content_tools.set_element_opacity(1, "shape", 1, 101)
        assert "Failed" in result[0].text
        assert not mock_subprocess_run.called

    async def test_shape_default_size_and_opacity(self, content_tools, mock_subprocess_run):
        await content_tools.add_shape(1)
        script = last_script(mock_subprocess_run)
        assert "width:200" in script
        assert "set opacity of newShape to 100" in script

    async def test_clear_slide_preserves_placeholders(self, content_tools, mock_subprocess_run):
        # Placeholders are identified by object identity (default title/body
        # item), NOT by the old empty-text-at-0,0 heuristic: themed layouts
        # position their placeholders away from 0,0, and Keynote surfaces the
        # placeholder objects as phantom trailing "text items" whose deletion
        # would destroy them.
        await content_tools.clear_slide(2)
        script = last_script(mock_subprocess_run)
        assert "default title item" in script
        assert "default body item" in script
        assert "(item 1 of pos) is 0" not in script
        assert "delete image" not in script

    async def test_centered_title_computes_x_server_side(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "T|1|484,400|951,119"
        result = await content_tools.add_title(1, "Big", font_size=96, centered=True)
        script = last_script(mock_subprocess_run)
        assert "((width of targetDoc) - (width of newItem)) div 2" in script
        # centering must run AFTER the final box width is known (post font-size)
        assert script.index("div 2") > script.index("set size of object text")
        assert "centered" in result[0].text

    async def test_uncentered_title_has_no_centering_math(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "T|1|100,200|300,40"
        await content_tools.add_subtitle(1, "s")
        assert "div 2" not in last_script(mock_subprocess_run)

    async def test_add_returns_identity_located_index_not_count(
        self, content_tools, mock_subprocess_run
    ):
        # `count of text items` over-reports (hidden placeholders count) and
        # the new item is not last, so the returned index must come from an
        # identity search - the same space get_slide_content/move_element use.
        mock_subprocess_run.return_value.stdout = "T|2|100,200|300,40"
        result = await content_tools.add_title(1, "T")
        script = last_script(mock_subprocess_run)
        assert "if text item i of targetSlide is newItem then" in script
        assert "return count of text items" not in script
        assert "text item index 2" in result[0].text

    async def test_add_sets_position_after_font_sizing(self, content_tools, mock_subprocess_run):
        # Text items are born at the theme default font size and auto-fit
        # around their vertical CENTER when the size changes, so a position
        # set before `set size of object text` drifts by (h_before-h_after)/2.
        # Position must be applied after all font/size/text mutations.
        mock_subprocess_run.return_value.stdout = "T|1|100,300|300,40"
        await content_tools.add_text_box(1, "T", x=100, y=300, font_size=24)
        script = last_script(mock_subprocess_run)
        assert script.index("set position of newItem") > script.index("set size of object text")
        assert script.index("set position of newItem") > script.index(
            "set object text of newItem to (item 2 of argv)"
        )

    async def test_add_reports_final_geometry(self, content_tools, mock_subprocess_run):
        # Every add_* answer carries the element's settled position/size read
        # back in the SAME osascript call - callers must never need a
        # follow-up get_slide_content to learn where the element landed.
        mock_subprocess_run.return_value.stdout = "T|3|120,290|430,250"
        result = await content_tools.add_bullet_list(1, ["a", "b"], x=120, y=290)
        script = last_script(mock_subprocess_run)
        assert "position of newItem" in script
        assert "height of newItem" in script
        assert "at (120, 290), size 430x250" in result[0].text

    async def test_add_image_and_shape_report_index_and_geometry(
        self, content_tools, mock_subprocess_run, tmp_path
    ):
        img = tmp_path / "i.png"
        img.write_bytes(b"png")
        mock_subprocess_run.return_value.stdout = "I|2|800,100|64,64"
        result = await content_tools.add_image(1, str(img), x=800, y=100)
        assert "image index 2" in result[0].text
        assert "at (800, 100), size 64x64" in result[0].text
        mock_subprocess_run.return_value.stdout = "S|1|50,60|400,300"
        result = await content_tools.add_shape(1, x=50, y=60, width=400, height=300)
        assert "shape index 1" in result[0].text
        assert "at (50, 60), size 400x300" in result[0].text

    async def test_get_slide_content_filters_phantom_placeholder_entries(
        self, content_tools, mock_subprocess_run
    ):
        # count of text items includes the default title/body placeholder
        # objects even when hidden (and twice when showing); the report must
        # enumerate only the real entries while keeping their live indices.
        mock_subprocess_run.return_value.stdout = "text_items:1|images:0|shapes:0|tables:0"
        await content_tools.get_slide_content(2)
        script = last_script(mock_subprocess_run)
        assert "default title item" in script
        assert "default body item" in script
        assert "title showing" in script
        assert "count of realIndices" in script
        assert '"text_items:" & rawTextCount' not in script
        assert '"text_items:" & textCount' not in script

    async def test_build_in_selects_slide_first(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "Window"
        await content_tools.add_build_in(2, "text", 3)
        scripts = [c.kwargs["input"] for c in mock_subprocess_run.call_args_list]
        # window title lookup, separate slide-selection call, then UI script
        assert any("set current slide of front document" in s for s in scripts[:-1])
        assert "System Events" in scripts[-1]

    async def test_build_in_ui_timeout_is_extended(self, content_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "Window"
        await content_tools.add_build_in(2, "text", 3)
        # the last call is the best-effort Format-pane restore (10s); the UI
        # scripting call itself gets the extended 60s timeout
        timeouts = [c.kwargs.get("timeout") for c in mock_subprocess_run.call_args_list]
        assert 60.0 in timeouts

    async def test_builds_batch_rejects_garbage_indices(self, content_tools, mock_subprocess_run):
        result = await content_tools.add_builds_to_slide(1, "1,-2")
        assert "Invalid element index" in result[0].text

    async def test_error_path_returns_failed_text(self, content_tools, mock_subprocess_run):
        _fail_with(mock_subprocess_run, NOT_FOUND)
        result = await content_tools.edit_text_item(1, 9, "x")
        assert "Failed to edit text item" in result[0].text


class TestExportTools:
    async def test_screenshot_restores_skip_state(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        await export_tools.screenshot_slide(1, str(tmp_path / "out.png"))
        script = last_script(mock_subprocess_run)
        assert "set savedStates to skipped of every slide" in script
        assert "item i of savedStates" in script

    async def test_screenshot_moves_generated_file(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        out = tmp_path / "out.png"

        def fake_run(cmd, **kwargs):
            # Simulate Keynote writing into the temp export folder (argv item 2)
            folder = cmd[3]
            (tmp_path / "check").mkdir(exist_ok=True)
            import pathlib

            pathlib.Path(folder, "slide.001.png").write_bytes(b"x" * 10)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_subprocess_run.side_effect = fake_run
        result = await export_tools.screenshot_slide(1, str(out))
        assert "Captured screenshot" in result[0].text
        assert out.exists()

    async def test_screenshot_warns_about_omitted_placeholders(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        # Keynote's export omits unfilled placeholder boxes; a screenshot that
        # looks clean can hide placeholder boxes the editor still shows.
        out = tmp_path / "out.png"

        def fake_run(cmd, **kwargs):
            import pathlib

            script = kwargs.get("input", "")
            if "emptyCount" in script:
                return subprocess.CompletedProcess(cmd, 0, "2", "")
            pathlib.Path(cmd[3], "slide.001.png").write_bytes(b"x" * 10)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_subprocess_run.side_effect = fake_run
        result = await export_tools.screenshot_slide(1, str(out))
        assert "2 unfilled placeholder" in result[0].text
        assert "NOT rendered" in result[0].text

    async def test_screenshot_zero_placeholders_confirms_faithful(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        out = tmp_path / "out.png"

        def fake_run(cmd, **kwargs):
            import pathlib

            script = kwargs.get("input", "")
            if "emptyCount" in script:
                return subprocess.CompletedProcess(cmd, 0, "0", "")
            pathlib.Path(cmd[3], "slide.001.png").write_bytes(b"x" * 10)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_subprocess_run.side_effect = fake_run
        result = await export_tools.screenshot_slide(1, str(out))
        assert "matches the editor view" in result[0].text

    async def test_export_pdf_uses_posix_file(self, export_tools, mock_subprocess_run, tmp_path):
        await export_tools.export_pdf(str(tmp_path / "deck.pdf"))
        assert "as PDF" in last_script(mock_subprocess_run)
        assert mock_subprocess_run.call_args.kwargs["timeout"] == 120.0

    async def test_screenshot_error_path(self, export_tools, mock_subprocess_run, tmp_path):
        _fail_with(mock_subprocess_run, NOT_FOUND)
        result = await export_tools.screenshot_slide(1, str(tmp_path / "o.png"))
        assert "Failed to screenshot" in result[0].text
